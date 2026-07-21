<?php
/**
 * KomposIoT PHP API — Security Middleware
 * File: /kompos/api/security.php
 *
 * Layer keamanan komprehensif:
 *   1. Rate Limiting      — batas request per IP per menit/jam
 *   2. IP Whitelist/Block — blokir IP berbahaya, izinkan perangkat IoT
 *   3. Request Validation — ukuran body, Content-Type, User-Agent
 *   4. Honeypot Detection — deteksi scanner & bot otomatis
 *   5. Security Headers   — HSTS, CSP, X-Frame-Options, dll.
 *   6. Audit Log          — catat setiap request (sukses & gagal)
 *   7. Brute-force Guard  — blokir IP setelah N kali gagal auth
 *
 * Dipanggil di awal index.php sebelum routing.
 */

require_once __DIR__ . '/config.php';

// ════════════════════════════════════════════════════════════
// SECURITY CONFIGURATION
// ════════════════════════════════════════════════════════════

// Rate limiting
define('RATE_LIMIT_PER_MIN',    30);   // max request per IP per menit
define('RATE_LIMIT_PER_HOUR',  200);   // max request per IP per jam
define('RATE_POST_PER_MIN',     10);   // max POST per IP per menit (lebih ketat)

// Brute-force protection
define('BRUTE_MAX_FAILS',        5);   // max gagal auth sebelum blokir
define('BRUTE_BLOCK_MINUTES',   30);   // durasi blokir (menit)

// Request size limits
define('MAX_BODY_BYTES',      8192);   // max 8 KB per request body
define('MAX_JSON_DEPTH',         5);   // max nesting depth JSON

// File paths untuk data keamanan (di luar web root = lebih aman)
define('SEC_DIR',       __DIR__ . '/../data/security/');
define('RATE_FILE',     SEC_DIR . 'rate_limits.json');
define('BLOCK_FILE',    SEC_DIR . 'blocked_ips.json');
define('BRUTE_FILE',    SEC_DIR . 'brute_fails.json');
define('AUDIT_FILE',    SEC_DIR . 'audit.log');
define('HONEYPOT_FILE', SEC_DIR . 'honeypot.json');

// IP Whitelist (opsional — kosong = semua IP boleh mencoba auth)
// Isi dengan IP statis ESP32/router Anda untuk keamanan maksimal
define('IP_WHITELIST', [
    // '192.168.1.0/24',   // Contoh: izinkan seluruh subnet lokal
    // '203.0.113.42',     // Contoh: IP publik statis
]);

// IP Blacklist manual (tambah jika ada IP bermasalah)
define('IP_BLACKLIST', [
    // '185.220.101.0/24', // Contoh: blokir range Tor exit nodes
]);

// User-Agent yang DIIZINKAN (ESP32, script Python, curl)
define('ALLOWED_UA_PATTERNS', [
    'ESP32', 'ESP8266', 'D1R32',    // firmware mikrokontroler
    'python-requests',               // simulasi Python
    'curl', 'HTTPie', 'Insomnia',   // testing tools
    'KomposIoT',                     // custom UA
    '',                              // izinkan UA kosong (firmware lama)
]);

// Endpoint yang boleh diakses tanpa auth
define('PUBLIC_ENDPOINTS', ['health']);

// Honeypot paths — jika ada yang mengakses ini, pasti scanner/bot
define('HONEYPOT_PATHS', [
    '/wp-admin', '/wp-login', '/admin', '/phpMyAdmin',
    '/.env', '/config.ini', '/backup', '/.git',
    '/shell', '/cmd', '/xmlrpc.php', '/api/v1',
]);

// ════════════════════════════════════════════════════════════
// HELPER: FILE-BASED ATOMIC READ/WRITE
// ════════════════════════════════════════════════════════════

function secEnsureDir(): void {
    if (!is_dir(SEC_DIR)) {
        mkdir(SEC_DIR, 0750, true);
        // Proteksi direktori security dari web
        file_put_contents(SEC_DIR . '.htaccess', "Deny from all\n");
    }
}

function secReadJson(string $file): array {
    if (!file_exists($file)) return [];
    $fp  = fopen($file, 'r+');
    if (!$fp) return [];
    flock($fp, LOCK_SH);
    $raw = stream_get_contents($fp);
    flock($fp, LOCK_UN);
    fclose($fp);
    $data = json_decode($raw ?: '{}', true);
    return is_array($data) ? $data : [];
}

function secWriteJson(string $file, array $data): void {
    $fp = fopen($file, 'c+');
    if (!$fp) return;
    flock($fp, LOCK_EX);
    ftruncate($fp, 0);
    fseek($fp, 0);
    fwrite($fp, json_encode($data));
    flock($fp, LOCK_UN);
    fclose($fp);
}

function auditLog(string $event, array $ctx = []): void {
    secEnsureDir();
    $line = date('Y-m-d H:i:s') . ' | '
          . str_pad($event, 22)
          . ' | IP=' . getClientIp()
          . ' | ' . json_encode($ctx, JSON_UNESCAPED_UNICODE) . "\n";
    file_put_contents(AUDIT_FILE, $line, FILE_APPEND | LOCK_EX);

    // Rotasi log jika > 5 MB
    if (file_exists(AUDIT_FILE) && filesize(AUDIT_FILE) > 5 * 1024 * 1024) {
        rename(AUDIT_FILE, AUDIT_FILE . '.' . date('Ymd'));
    }
}

// ════════════════════════════════════════════════════════════
// 1. GET CLIENT IP (support proxy)
// ════════════════════════════════════════════════════════════

function getClientIp(): string {
    // Trusted proxy headers (hanya percaya jika server di balik proxy terpercaya)
    $headers = [
        'HTTP_CF_CONNECTING_IP',    // Cloudflare
        'HTTP_X_REAL_IP',           // Nginx proxy
        'HTTP_X_FORWARDED_FOR',
        'REMOTE_ADDR',
    ];
    foreach ($headers as $h) {
        if (!empty($_SERVER[$h])) {
            // X-Forwarded-For bisa berisi daftar — ambil IP pertama
            $ip = trim(explode(',', $_SERVER[$h])[0]);
            if (filter_var($ip, FILTER_VALIDATE_IP,
                           FILTER_FLAG_NO_PRIV_RANGE |
                           FILTER_FLAG_NO_RES_RANGE)) {
                return $ip;
            }
            // Izinkan IP private (untuk jaringan lokal ESP32)
            if (filter_var($ip, FILTER_VALIDATE_IP)) return $ip;
        }
    }
    return $_SERVER['REMOTE_ADDR'] ?? '0.0.0.0';
}

// ════════════════════════════════════════════════════════════
// 2. CIDR / RANGE MATCHING
// ════════════════════════════════════════════════════════════

function ipMatchesCidr(string $ip, string $cidr): bool {
    if (!str_contains($cidr, '/')) return $ip === $cidr;

    [$net, $bits] = explode('/', $cidr, 2);
    $ipLong  = ip2long($ip);
    $netLong = ip2long($net);
    if ($ipLong === false || $netLong === false) return false;
    $mask = $bits >= 32 ? -1 : ~((1 << (32 - (int)$bits)) - 1);
    return ($ipLong & $mask) === ($netLong & $mask);
}

function ipInList(string $ip, array $list): bool {
    foreach ($list as $entry) {
        if (ipMatchesCidr($ip, trim($entry))) return true;
    }
    return false;
}

// ════════════════════════════════════════════════════════════
// 3. IP WHITELIST / BLACKLIST CHECK
// ════════════════════════════════════════════════════════════

function checkIpAccess(string $ip): void {
    // Blacklist manual
    if (ipInList($ip, IP_BLACKLIST)) {
        auditLog('BLOCKED_BLACKLIST', ['ip' => $ip]);
        secDeny(403, 'IP address blocked');
    }

    // Cek file IP yang diblokir otomatis
    $blocked = secReadJson(BLOCK_FILE);
    if (isset($blocked[$ip])) {
        if ($blocked[$ip]['until'] > time()) {
            $rem = ceil(($blocked[$ip]['until'] - time()) / 60);
            auditLog('BLOCKED_DYNAMIC', ['ip'=>$ip,'reason'=>$blocked[$ip]['reason']]);
            secDeny(429, "IP blocked for $rem more minute(s). Reason: " . $blocked[$ip]['reason']);
        }
        // Unblock kalau sudah lewat waktu
        unset($blocked[$ip]);
        secWriteJson(BLOCK_FILE, $blocked);
    }

    // Whitelist: jika ada whitelist dan IP tidak ada di dalamnya → tolak
    if (!empty(IP_WHITELIST) && !ipInList($ip, IP_WHITELIST)) {
        auditLog('BLOCKED_NOT_WHITELISTED', ['ip' => $ip]);
        secDeny(403, 'IP not in whitelist');
    }
}

function blockIp(string $ip, string $reason, int $minutes): void {
    $blocked = secReadJson(BLOCK_FILE);
    $blocked[$ip] = [
        'reason'    => $reason,
        'until'     => time() + $minutes * 60,
        'blocked_at'=> date('Y-m-d H:i:s'),
    ];
    secWriteJson(BLOCK_FILE, $blocked);
    auditLog('IP_BLOCKED', ['ip'=>$ip,'reason'=>$reason,'minutes'=>$minutes]);
}

// ════════════════════════════════════════════════════════════
// 4. RATE LIMITING
// ════════════════════════════════════════════════════════════

function checkRateLimit(string $ip, string $method): void {
    $now    = time();
    $minute = (int)($now / 60);
    $hour   = (int)($now / 3600);

    $data   = secReadJson(RATE_FILE);
    $key    = md5($ip);   // hash IP untuk sedikit privasi

    if (!isset($data[$key])) {
        $data[$key] = ['min'=>$minute, 'min_cnt'=>0,
                       'hr'=>$hour,   'hr_cnt'=>0,
                       'post_min'=>$minute, 'post_cnt'=>0];
    }

    $r = &$data[$key];

    // Reset counter jika bucket berubah
    if ($r['min'] !== $minute) { $r['min'] = $minute; $r['min_cnt'] = 0; }
    if ($r['hr']  !== $hour)   { $r['hr']  = $hour;   $r['hr_cnt']  = 0; }
    if (($r['post_min'] ?? $minute) !== $minute) {
        $r['post_min'] = $minute; $r['post_cnt'] = 0;
    }

    $r['min_cnt']++;
    $r['hr_cnt']++;
    if ($method === 'POST') $r['post_cnt'] = ($r['post_cnt'] ?? 0) + 1;

    // Check limits
    if ($r['min_cnt'] > RATE_LIMIT_PER_MIN) {
        secWriteJson(RATE_FILE, $data);
        if ($r['min_cnt'] > RATE_LIMIT_PER_MIN * 3) {
            blockIp($ip, 'rate_limit_abuse', BRUTE_BLOCK_MINUTES);
        }
        auditLog('RATE_LIMIT_MIN', ['ip'=>$ip,'cnt'=>$r['min_cnt']]);
        secDeny(429, 'Rate limit exceeded: ' . RATE_LIMIT_PER_MIN . ' req/min');
    }
    if ($r['hr_cnt'] > RATE_LIMIT_PER_HOUR) {
        secWriteJson(RATE_FILE, $data);
        auditLog('RATE_LIMIT_HOUR', ['ip'=>$ip,'cnt'=>$r['hr_cnt']]);
        secDeny(429, 'Rate limit exceeded: ' . RATE_LIMIT_PER_HOUR . ' req/hour');
    }
    if ($method === 'POST' && ($r['post_cnt'] ?? 0) > RATE_POST_PER_MIN) {
        secWriteJson(RATE_FILE, $data);
        auditLog('RATE_LIMIT_POST', ['ip'=>$ip,'cnt'=>$r['post_cnt']]);
        secDeny(429, 'POST rate limit exceeded: ' . RATE_POST_PER_MIN . ' POST/min');
    }

    // Bersihkan entri lama (setiap ~100 request)
    if (rand(0, 100) === 0) {
        $cutoff = $hour - 2;
        foreach ($data as $k => $v) {
            if (($v['hr'] ?? 0) < $cutoff) unset($data[$k]);
        }
    }

    secWriteJson(RATE_FILE, $data);
}

// ════════════════════════════════════════════════════════════
// 5. BRUTE-FORCE PROTECTION (auth failures)
// ════════════════════════════════════════════════════════════

function recordAuthFailure(string $ip): void {
    $data = secReadJson(BRUTE_FILE);
    $data[$ip] = [
        'count'   => ($data[$ip]['count'] ?? 0) + 1,
        'last_at' => time(),
    ];

    if ($data[$ip]['count'] >= BRUTE_MAX_FAILS) {
        blockIp($ip, 'brute_force_auth', BRUTE_BLOCK_MINUTES);
        unset($data[$ip]);
        auditLog('BRUTE_FORCE_BLOCKED', ['ip'=>$ip]);
    } else {
        auditLog('AUTH_FAIL', ['ip'=>$ip,'count'=>$data[$ip]['count']]);
    }
    secWriteJson(BRUTE_FILE, $data);
}

function clearAuthFailures(string $ip): void {
    $data = secReadJson(BRUTE_FILE);
    if (isset($data[$ip])) {
        unset($data[$ip]);
        secWriteJson(BRUTE_FILE, $data);
    }
}

// Override requireAuth dari config.php untuk tambah brute-force tracking
function requireAuthSecure(?array $body = null): void {
    if (!AUTH_ENABLED) return;
    $ip  = getClientIp();
    $key = $_SERVER['HTTP_X_API_KEY']
        ?? $body['api_key']
        ?? $_GET['api_key']
        ?? '';

    if (trim($key) !== API_KEY) {
        recordAuthFailure($ip);
        secDeny(401, 'Unauthorized: invalid or missing api_key');
    }
    clearAuthFailures($ip);  // reset counter setelah sukses
}

// ════════════════════════════════════════════════════════════
// 6. REQUEST VALIDATION
// ════════════════════════════════════════════════════════════

function checkRequestIntegrity(string $method): void {
    // Content-Type wajib untuk POST
    if ($method === 'POST') {
        $ct = $_SERVER['CONTENT_TYPE'] ?? '';
        if (!str_contains(strtolower($ct), 'application/json')) {
            auditLog('BAD_CONTENT_TYPE', ['ct'=>$ct]);
            secDeny(415, 'Content-Type must be application/json');
        }
    }

    // Ukuran body maksimal
    $len = (int)($_SERVER['CONTENT_LENGTH'] ?? 0);
    if ($len > MAX_BODY_BYTES) {
        auditLog('BODY_TOO_LARGE', ['bytes'=>$len]);
        secDeny(413, 'Request body too large (max ' . MAX_BODY_BYTES . ' bytes)');
    }

    // User-Agent check (opsional tapi efektif melawan scraper massal)
    $ua = $_SERVER['HTTP_USER_AGENT'] ?? '';
    if (!empty(ALLOWED_UA_PATTERNS) && !empty($ua)) {
        $allowed = false;
        foreach (ALLOWED_UA_PATTERNS as $pattern) {
            if ($pattern === '' || stripos($ua, $pattern) !== false) {
                $allowed = true; break;
            }
        }
        if (!$allowed) {
            auditLog('BLOCKED_USER_AGENT', ['ua'=>substr($ua,0,100)]);
            secDeny(403, 'User-Agent not allowed');
        }
    }

    // Blokir method yang tidak diizinkan
    $allowed_methods = ['GET','POST','DELETE','OPTIONS','HEAD'];
    if (!in_array($method, $allowed_methods, true)) {
        secDeny(405, 'Method Not Allowed');
    }
}

// ════════════════════════════════════════════════════════════
// 7. HONEYPOT — DETEKSI SCANNER & BOT
// ════════════════════════════════════════════════════════════

function checkHoneypot(string $uri): void {
    foreach (HONEYPOT_PATHS as $trap) {
        if (stripos($uri, $trap) !== false) {
            $ip = getClientIp();
            auditLog('HONEYPOT_HIT', ['ip'=>$ip,'uri'=>$uri]);
            // Blokir langsung — hanya bot/scanner yang mencari path ini
            blockIp($ip, 'honeypot_hit', 60 * 24);   // blokir 24 jam
            secDeny(404, 'Not Found');
        }
    }
}

// ════════════════════════════════════════════════════════════
// 8. SECURITY RESPONSE HEADERS
// ════════════════════════════════════════════════════════════

function sendSecurityHeaders(): void {
    // Strict Transport Security (aktifkan hanya jika pakai HTTPS)
    // header('Strict-Transport-Security: max-age=31536000; includeSubDomains');

    header('X-Content-Type-Options: nosniff');
    header('X-Frame-Options: DENY');
    header('X-XSS-Protection: 1; mode=block');
    header('Referrer-Policy: no-referrer');
    header('Content-Security-Policy: default-src \'none\'');
    header('Cache-Control: no-store, no-cache, must-revalidate');
    header('Pragma: no-cache');
    header('X-Powered-By: KomposIoT');   // hapus versi PHP dari header

    // Rate limit info headers (seperti GitHub API)
    header('X-RateLimit-Limit-Minute: ' . RATE_LIMIT_PER_MIN);
    header('X-RateLimit-Limit-Hour: '   . RATE_LIMIT_PER_HOUR);
}

// ════════════════════════════════════════════════════════════
// 9. INPUT SANITIZATION
// ════════════════════════════════════════════════════════════

function sanitizeJsonBody(array $body): array {
    $clean = [];
    $allowed_keys = [
        'device_id','device_loc','timestamp','suhu','moisture',
        'gas','api_key','firmware','chip','uptime','wifi_rssi',
        'free_heap','device_id','limit','hours','days','level',
    ];
    foreach ($allowed_keys as $k) {
        if (!array_key_exists($k, $body)) continue;
        $v = $body[$k];
        if (is_string($v)) {
            // Strip HTML, null bytes, kontrol karakter berbahaya
            $v = strip_tags($v);
            $v = str_replace(["\0","\r"], '', $v);
            $v = substr($v, 0, 256);   // maksimal 256 karakter per field string
        } elseif (is_numeric($v)) {
            $v = $v + 0;   // cast ke number
        } elseif (is_bool($v)) {
            $v = (bool)$v;
        } else {
            continue;   // skip tipe lain (array nested, dll.)
        }
        $clean[$k] = $v;
    }
    return $clean;
}

function sanitizeQueryParam(string $key, string $default = '',
                            int $max_len = 64): string {
    $v = $_GET[$key] ?? $default;
    $v = strip_tags((string)$v);
    $v = str_replace(["\0","\r","\n"], '', $v);
    return substr(trim($v), 0, $max_len);
}

function sanitizeInt(string $key, int $default, int $min, int $max): int {
    $v = filter_input(INPUT_GET, $key, FILTER_VALIDATE_INT,
                      ['options'=>['min_range'=>$min,'max_range'=>$max]]);
    return $v === false || $v === null ? $default : $v;
}

// ════════════════════════════════════════════════════════════
// 10. DENY HELPER
// ════════════════════════════════════════════════════════════

function secDeny(int $code, string $msg): never {
    http_response_code($code);
    header('Content-Type: application/json; charset=utf-8');
    // Tambahkan retry-after untuk 429
    if ($code === 429) header('Retry-After: 60');
    echo json_encode([
        'error'   => $msg,
        'code'    => $code,
        'ts'      => date('Y-m-d\TH:i:s'),
    ]);
    exit;
}

// ════════════════════════════════════════════════════════════
// 11. ENTRY POINT — panggil dari index.php
// ════════════════════════════════════════════════════════════

function runSecurityMiddleware(string $uri, string $method,
                               string $route): void {
    secEnsureDir();
    sendSecurityHeaders();

    $ip = getClientIp();

    // Honeypot — cek sebelum apapun
    checkHoneypot($uri);

    // IP check
    checkIpAccess($ip);

    // Rate limiting
    checkRateLimit($ip, $method);

    // Request integrity
    checkRequestIntegrity($method);

    // Log request normal
    auditLog('REQUEST', [
        'method' => $method,
        'route'  => $route,
        'ua'     => substr($_SERVER['HTTP_USER_AGENT'] ?? '', 0, 80),
    ]);
}

// ════════════════════════════════════════════════════════════
// UTILITY: Admin helpers (untuk maintenance)
// ════════════════════════════════════════════════════════════

/** Hapus semua IP yang diblokir (panggil via CLI). */
function clearAllBlocks(): void {
    secWriteJson(BLOCK_FILE, []);
    secWriteJson(BRUTE_FILE, []);
    echo "All blocks cleared.\n";
}

/** Tampilkan daftar IP yang diblokir. */
function listBlockedIps(): array {
    $blocked = secReadJson(BLOCK_FILE);
    $now     = time();
    $active  = [];
    foreach ($blocked as $ip => $info) {
        if ($info['until'] > $now) {
            $active[$ip] = $info;
            $active[$ip]['remaining_min'] = ceil(($info['until'] - $now) / 60);
        }
    }
    return $active;
}

/** Tampilkan statistik rate dari satu IP. */
function getIpStats(string $ip): array {
    $data = secReadJson(RATE_FILE);
    $key  = md5($ip);
    return $data[$key] ?? ['not_found' => true];
}
