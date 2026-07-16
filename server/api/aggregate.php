<?php
/**
 * KomposIoT PHP Server — GET /api/aggregate.php
 *
 * Query params:
 *   device_id  (default: D1R32_01)
 *   level      hourly | daily | fase  (default: hourly)
 *   days       (default: 7, max: 90)
 */
require_once __DIR__ . '/config.php';
require_once __DIR__ . '/db.php';

if ($_SERVER['REQUEST_METHOD'] !== 'GET')
    jsonError('Method Not Allowed', 405);

requireAuth();

$deviceId = $_GET['device_id'] ?? 'D1R32_01';
$level    = $_GET['level']     ?? 'hourly';
$days     = max(1, min(AGGREGATE_MAX_DAYS, (int)($_GET['days'] ?? 7)));
$since    = date('Y-m-d\TH:i:s', strtotime("-{$days} days"));

$db = getDB();

switch ($level) {
    case 'hourly':
        $stmt = $db->prepare("
            SELECT hour_bucket, suhu_mean, suhu_min, suhu_max, suhu_std,
                   moisture_mean, moisture_min, moisture_max, moisture_std,
                   gas_mean, gas_min, gas_max, gas_std,
                   ikk_mean, ikk_min, ikk_max,
                   fase_mode, sample_count
            FROM   aggregation_hourly
            WHERE  device_id = :dev
              AND  hour_bucket >= :since
            ORDER  BY hour_bucket ASC
        ");
        $stmt->execute([':dev' => $deviceId,
                        ':since' => substr($since, 0, 13)]);
        break;

    case 'daily':
        $stmt = $db->prepare("
            SELECT date(timestamp) AS day,
                   round(avg(suhu),3)     AS suhu_mean,
                   round(min(suhu),3)     AS suhu_min,
                   round(max(suhu),3)     AS suhu_max,
                   round(avg(moisture),3) AS moisture_mean,
                   round(min(moisture),3) AS moisture_min,
                   round(max(moisture),3) AS moisture_max,
                   round(avg(gas),3)      AS gas_mean,
                   round(max(gas),3)      AS gas_max,
                   round(avg(ikk),3)      AS ikk_mean,
                   round(min(ikk),3)      AS ikk_min,
                   count(*)               AS sample_count
            FROM   sensor_data
            WHERE  device_id = :dev
              AND  timestamp >= :since
            GROUP  BY date(timestamp)
            ORDER  BY day ASC
        ");
        $stmt->execute([':dev' => $deviceId, ':since' => $since]);
        break;

    case 'fase':
        $stmt = $db->prepare("
            SELECT fase_pred, fase_nama,
                   round(avg(suhu),3)     AS suhu_mean,
                   round(min(suhu),3)     AS suhu_min,
                   round(max(suhu),3)     AS suhu_max,
                   round(avg(moisture),3) AS moisture_mean,
                   round(avg(gas),3)      AS gas_mean,
                   round(max(gas),3)      AS gas_max,
                   round(avg(ikk),3)      AS ikk_mean,
                   count(*)               AS sample_count,
                   min(timestamp)         AS first_seen,
                   max(timestamp)         AS last_seen
            FROM   sensor_data
            WHERE  device_id = :dev
              AND  timestamp >= :since
            GROUP  BY fase_pred
            ORDER  BY fase_pred ASC
        ");
        $stmt->execute([':dev' => $deviceId, ':since' => $since]);
        break;

    default:
        jsonError("Unknown level '$level'. Use: hourly | daily | fase");
}

$rows = $stmt->fetchAll();

jsonOut([
    'device_id' => $deviceId,
    'level'     => $level,
    'days'      => $days,
    'count'     => count($rows),
    'data'      => $rows,
]);
