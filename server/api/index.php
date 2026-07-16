<?php
/**
 * KomposIoT PHP API — Router / index.php
 *
 * Deploy seluruh folder api/ ke web server Anda.
 * File ini otomatis mengarahkan request ke endpoint yang tepat.
 *
 * ── Apache: aktifkan .htaccess (sudah disertakan) ──────────
 * ── Nginx : tambahkan ke server block:
 *      location /kompos/api/ {
 *          try_files $uri $uri/ /kompos/api/index.php?$query_string;
 *      }
 */
require_once __DIR__ . '/config.php';

header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, DELETE, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type, X-API-Key, Accept');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200); exit;
}

// Parse last URI segment as route name
$uri   = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
$parts = array_values(array_filter(explode('/', $uri)));
$route = end($parts);
// Strip .php if present
$route = str_replace('.php', '', $route);

$allowed = ['data','latest','history','aggregate','status','health','reset'];

if (in_array($route, $allowed, true)) {
    require_once __DIR__ . "/{$route}.php";
} else {
    // API info / root
    jsonOut([
        'name'      => 'KomposIoT REST API',
        'version'   => '2.0',
        'php'       => PHP_VERSION,
        'endpoints' => [
            'POST   /api/data.php'       => 'Kirim data sensor dari D1 R32',
            'GET    /api/latest.php'     => 'Data terbaru per device',
            'GET    /api/history.php'    => 'Riwayat N jam terakhir',
            'GET    /api/aggregate.php'  => 'Agregasi hourly/daily/fase',
            'GET    /api/status.php'     => 'Status server + SPRT state',
            'GET    /api/health.php'     => 'Health check (tanpa auth)',
            'DELETE /api/reset.php'      => 'Reset database (dev only)',
        ],
        'docs' => 'Set X-API-Key header atau tambahkan api_key ke JSON body',
    ]);
}
