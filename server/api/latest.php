<?php
/**
 * KomposIoT PHP Server — GET /api/latest.php
 * Kembalikan baris sensor_data terbaru untuk device_id tertentu.
 */
require_once __DIR__ . '/config.php';
require_once __DIR__ . '/db.php';

if ($_SERVER['REQUEST_METHOD'] !== 'GET')
    jsonError('Method Not Allowed', 405);

requireAuth();

$deviceId = $_GET['device_id'] ?? 'D1R32_01';
$db  = getDB();
$row = $db->prepare("
    SELECT * FROM sensor_data
    WHERE  device_id = :dev
    ORDER  BY id DESC LIMIT 1
");
$row->execute([':dev' => $deviceId]);
$data = $row->fetch();

if (!$data) jsonError('No data found for device: ' . $deviceId, 404);
jsonOut($data);
