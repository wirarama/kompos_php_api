<?php
/**
 * KomposIoT PHP Server — GET /api/history.php
 *
 * Query params:
 *   device_id  (default: D1R32_01)
 *   hours      (default: 24)
 *   limit      (default: 500, max: 5000)
 */
require_once __DIR__ . '/config.php';
require_once __DIR__ . '/db.php';

if ($_SERVER['REQUEST_METHOD'] !== 'GET')
    jsonError('Method Not Allowed', 405);

requireAuth();

$deviceId = $_GET['device_id'] ?? 'D1R32_01';
$hours    = max(1, min(8760, (int)($_GET['hours'] ?? 24)));
$limit    = max(1, min(HISTORY_MAX, (int)($_GET['limit'] ?? 500)));
$since    = date('Y-m-d\TH:i:s', strtotime("-{$hours} hours"));

$db   = getDB();
$stmt = $db->prepare("
    SELECT id, device_id, timestamp,
           suhu, moisture, gas,
           fase_pred, fase_nama, ikk,
           sprt_cusum_t, sprt_cusum_m, sprt_cusum_g
    FROM   sensor_data
    WHERE  device_id = :dev
      AND  timestamp >= :since
    ORDER  BY timestamp ASC
    LIMIT  :lim
");
$stmt->bindValue(':dev',   $deviceId);
$stmt->bindValue(':since', $since);
$stmt->bindValue(':lim',   $limit, PDO::PARAM_INT);
$stmt->execute();

$rows = $stmt->fetchAll();

jsonOut([
    'device_id' => $deviceId,
    'hours'     => $hours,
    'limit'     => $limit,
    'count'     => count($rows),
    'since'     => $since,
    'data'      => $rows,
]);
