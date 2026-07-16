<?php
/**
 * KomposIoT PHP API — GET /api/status.php
 * Menampilkan statistik server, DB, dan SPRT state.
 */
require_once __DIR__ . '/config.php';
require_once __DIR__ . '/db.php';
require_once __DIR__ . '/sprt.php';

if ($_SERVER['REQUEST_METHOD'] !== 'GET') {
    jsonError('Method Not Allowed', 405);
}
requireAuth();

$db = getDB();

// Total records
$total = (int)$db->query("SELECT COUNT(*) FROM sensor_data")
                  ->fetchColumn();

// Distinct devices
$devices = $db->query("SELECT DISTINCT device_id FROM sensor_data")
               ->fetchAll(PDO::FETCH_COLUMN);

// Latest reading
$latest = $db->query("
    SELECT device_id, timestamp, suhu, moisture, gas, fase_nama, ikk
    FROM   sensor_data
    ORDER  BY id DESC LIMIT 1
")->fetch();

// SPRT state summary
$sprtSummary = getSprtStateSummary();

jsonOut([
    'server'          => 'KomposIoT PHP API v2.0',
    'php_version'     => PHP_VERSION,
    'db_path'         => DB_PATH,
    'total_records'   => $total,
    'devices'         => $devices,
    'latest'          => $latest ?: null,
    'sprt_params'     => [
        'A'     => round(SPRT_A, 4),
        'B'     => round(SPRT_B, 4),
        'alpha' => SPRT_ALPHA,
        'beta'  => SPRT_BETA,
    ],
    'sprt_state'      => $sprtSummary,
    'time'            => date('Y-m-d\TH:i:s'),
]);
