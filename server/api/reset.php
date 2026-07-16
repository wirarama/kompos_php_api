<?php
/**
 * KomposIoT PHP API — DELETE /api/reset.php
 * Menghapus semua data sensor dan mereset SPRT state.
 * HANYA untuk development/testing!
 */
require_once __DIR__ . '/config.php';
require_once __DIR__ . '/db.php';
require_once __DIR__ . '/sprt.php';

if ($_SERVER['REQUEST_METHOD'] !== 'DELETE') {
    jsonError('Method Not Allowed — use DELETE', 405);
}
requireAuth();

$db = getDB();

// Hitung records yang akan dihapus
$count = (int)$db->query("SELECT COUNT(*) FROM sensor_data")->fetchColumn();

// Hapus semua data
$db->exec("DELETE FROM sensor_data");
$db->exec("DELETE FROM aggregation_hourly");
$db->exec("DELETE FROM sqlite_sequence
           WHERE name IN ('sensor_data','aggregation_hourly')");

// Reset SPRT state
resetSprtState();

jsonOut([
    'status'          => 'ok',
    'message'         => 'Database cleared and SPRT state reset',
    'records_deleted' => $count,
    'time'            => date('Y-m-d\TH:i:s'),
]);
