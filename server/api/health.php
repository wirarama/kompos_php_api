<?php
/**
 * KomposIoT PHP API — GET /api/health.php
 * Health check — tidak memerlukan auth
 */
require_once __DIR__ . '/config.php';

if ($_SERVER['REQUEST_METHOD'] !== 'GET') {
    jsonError('Method Not Allowed', 405);
}

jsonOut([
    'status'  => 'ok',
    'server'  => 'KomposIoT PHP API v2.0',
    'php'     => PHP_VERSION,
    'time'    => date('Y-m-d\TH:i:s'),
    'db_path' => file_exists(DB_PATH) ? 'exists' : 'not_created_yet',
]);
