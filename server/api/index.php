<?php
/**
 * KomposIoT PHP API — Secure Router
 * File: /kompos/api/index.php
 */

// Matikan error output ke client
ini_set('display_errors', 0);
error_reporting(E_ALL);

require_once __DIR__ . '/config.php';
require_once __DIR__ . '/security.php';

// ── CORS Headers ────────────────────────────────────────────
header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, DELETE, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type, X-API-Key, Accept');

// Preflight
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200); exit;
}

// ── Parse route ─────────────────────────────────────────────
$method = $_SERVER['REQUEST_METHOD'];
$uri    = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
$parts  = array_values(array_filter(explode('/', $uri)));
$route  = str_replace('.php', '', end($parts) ?: '');

$allowed = ['data','latest','history','aggregate','status','health','reset'];

// ── Run security middleware ──────────────────────────────────
// health endpoint dilewati dari auth tapi tetap kena rate limit & IP check
runSecurityMiddleware($uri, $method, $route);

// ── Dispatch ────────────────────────────────────────────────
if (in_array($route, $allowed, true)) {
    require_once __DIR__ . "/{$route}.php";
} else {
    // API info root
    jsonOut([
        'name'      => 'KomposIoT REST API',
        'version'   => '2.0',
        'security'  => 'rate-limiting, IP-block, brute-force-guard, honeypot',
        'endpoints' => [
            'POST   /api/data.php'       => 'Kirim data sensor dari D1 R32',
            'GET    /api/latest.php'     => 'Data terbaru per device',
            'GET    /api/history.php'    => 'Riwayat N jam terakhir',
            'GET    /api/aggregate.php'  => 'Agregasi hourly/daily/fase',
            'GET    /api/status.php'     => 'Status server + SPRT state',
            'GET    /api/health.php'     => 'Health check (tanpa auth)',
            'DELETE /api/reset.php'      => 'Reset database (dev only)',
        ],
        'auth' => 'Set header X-API-Key atau field api_key di JSON body',
        'docs' => 'Lihat README.md untuk panduan lengkap',
    ]);
}
