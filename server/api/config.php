<?php
/**
 * KomposIoT PHP Server — Konfigurasi Global
 * File: /kompos/api/config.php
 */

// ── Database ─────────────────────────────────────────────────
// Folder data/ harus writable: chmod 775 /var/www/html/kompos/data/
define('DB_PATH',        __DIR__ . '/../data/kompos.sqlite');
define('SPRT_STATE_FILE',__DIR__ . '/../data/sprt_state.json');

// ── API Security ──────────────────────────────────────────────
define('API_KEY',        'kompos2024iot');
define('AUTH_ENABLED',   true);

// ── SPRT Parameters ───────────────────────────────────────────
define('SPRT_ALPHA', 0.05);
define('SPRT_BETA',  0.10);
define('SPRT_A',     log((1 - SPRT_BETA)  / SPRT_ALPHA));  // +2.9444
define('SPRT_B',     log(SPRT_BETA / (1 - SPRT_ALPHA)));   // -1.9459

// ── IKK Weights ───────────────────────────────────────────────
define('IKK_W_T', 0.40);
define('IKK_W_M', 0.35);
define('IKK_W_G', 0.25);

// ── Phase Definitions ────────────────────────────────────────
const FASE_DEF = [
    0 => ['nama'=>'Mesophilik Awal',    'warna'=>'#52B788','emoji'=>'🌱'],
    1 => ['nama'=>'Termofilik Aktif',   'warna'=>'#E76F51','emoji'=>'🔥'],
    2 => ['nama'=>'Puncak Dekomposisi', 'warna'=>'#9B2226','emoji'=>'⚡'],
    3 => ['nama'=>'Pendinginan',        'warna'=>'#219EBC','emoji'=>'❄️'],
    4 => ['nama'=>'Maturasi',           'warna'=>'#8B5E3C','emoji'=>'🌾'],
    5 => ['nama'=>'Kompos Matang',      'warna'=>'#6B7280','emoji'=>'✅'],
];

// ── Phase Optimal Ranges ──────────────────────────────────────
const FASE_RANGES = [
    0 => ['suhu'=>[18,40],  'moisture'=>[60,85], 'gas'=>[30,110] ],
    1 => ['suhu'=>[38,68],  'moisture'=>[42,72], 'gas'=>[80,290] ],
    2 => ['suhu'=>[50,72],  'moisture'=>[32,56], 'gas'=>[250,620]],
    3 => ['suhu'=>[26,60],  'moisture'=>[36,56], 'gas'=>[100,510]],
    4 => ['suhu'=>[23,37],  'moisture'=>[36,55], 'gas'=>[45,170] ],
    5 => ['suhu'=>[18,30],  'moisture'=>[33,52], 'gas'=>[18,95]  ],
];

// ── SPRT Hypotheses: [sensor, mu0, mu1, sigma, target_fase] ──
const SPRT_HYPOTHESES = [
    ['suhu',     22, 35,  5, 0], ['suhu',    35, 55,  8, 1],
    ['suhu',     55, 65,  6, 2], ['suhu',    65, 38,  9, 3],
    ['suhu',     38, 29,  5, 4], ['suhu',    29, 23,  3, 5],
    ['moisture', 68, 58,  6, 0], ['moisture',58, 44,  7, 1],
    ['moisture', 44, 38,  5, 2], ['moisture',38, 44,  5, 3],
    ['moisture', 44, 42,  4, 4], ['moisture',42, 38,  3, 5],
    ['gas',      55,120, 30, 0], ['gas',    120,250, 50, 1],
    ['gas',     250,450, 70, 2], ['gas',    450,200, 80, 3],
    ['gas',     200, 90, 45, 4], ['gas',     90, 50, 22, 5],
];

// ── Limits ────────────────────────────────────────────────────
define('HISTORY_MAX',      5000);
define('AGGREGATE_MAX_DAYS', 90);

// ── Timezone ──────────────────────────────────────────────────
date_default_timezone_set('Asia/Makassar'); // WITA UTC+8

// ════════════════════════════════════════════════════════════
// GLOBAL HELPER FUNCTIONS
// ════════════════════════════════════════════════════════════

/** Send JSON response and exit. */
function jsonOut(array $data, int $code = 200): void {
    http_response_code($code);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}

/** Send JSON error and exit. */
function jsonError(string $msg, int $code = 400): void {
    jsonOut(['error' => $msg, 'status' => $code], $code);
}

/** Validate API key (header or JSON body field). */
function requireAuth(?array $body = null): void {
    if (!AUTH_ENABLED) return;
    $key = $_SERVER['HTTP_X_API_KEY']
        ?? $_SERVER['HTTP_X_API_KEY']
        ?? $body['api_key']
        ?? $_GET['api_key']
        ?? '';
    if (trim($key) !== API_KEY) {
        jsonError('Unauthorized: invalid or missing api_key', 401);
    }
}

/** Clamp float to [lo, hi]. */
function fclamp(float $v, float $lo, float $hi): float {
    return max($lo, min($hi, $v));
}

/** Soft membership: 1.0 in range, linear decay outside. */
function softMembership(float $val, float $lo, float $hi,
                        float $margin = 8.0): float {
    if ($val >= $lo && $val <= $hi) return 1.0;
    if ($val < $lo) return max(0.0, 1.0 - ($lo - $val) / $margin);
    return max(0.0, 1.0 - ($val - $hi) / $margin);
}

/** Get JSON body from request. Returns decoded array or null. */
function getJsonBody(): ?array {
    $raw = file_get_contents('php://input');
    if (!$raw) return null;
    $decoded = json_decode($raw, true);
    return is_array($decoded) ? $decoded : null;
}

/** Validate sensor value range. */
function validateRange(float $v, float $lo, float $hi,
                       string $name): void {
    if ($v < $lo || $v > $hi) {
        jsonError("Field '$name' out of range [$lo, $hi]: $v");
    }
}
