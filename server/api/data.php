<?php
/**
 * KomposIoT PHP Server — POST /api/data.php
 *
 * Menerima JSON dari firmware D1 R32 atau simulasi Python.
 * Alur: Validate → SPRT → IKK → INSERT → Aggregate → Response 201
 *
 * Metode : POST
 * Content: application/json
 * Body   :
 *   {
 *     "device_id" : "D1R32_01",
 *     "timestamp" : "2024-03-15T14:30:00",
 *     "suhu"      : 54.30,
 *     "moisture"  : 48.20,
 *     "gas"       : 185.60,
 *     "api_key"   : "kompos2024iot"   // atau header X-API-Key
 *   }
 * Response 201:
 *   {
 *     "id": 127, "status": "ok",
 *     "analysis": { "fase_pred":1, "fase_nama":"Termofilik Aktif",
 *                   "ikk":72.4, "sprt":{...} },
 *     "alerts": []
 *   }
 */

require_once __DIR__ . '/config.php';
require_once __DIR__ . '/db.php';
require_once __DIR__ . '/sprt.php';
require_once __DIR__ . '/ikk.php';

// ── Method guard ─────────────────────────────────────────────
if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    jsonError('Method Not Allowed — use POST', 405);
}

// ── Parse body ───────────────────────────────────────────────
$body = getJsonBody();
if (!$body) {
    jsonError('Invalid JSON body or empty Content-Type');
}

// ── Auth ─────────────────────────────────────────────────────
requireAuth($body);

// ── Required field validation ────────────────────────────────
foreach (['suhu', 'moisture', 'gas'] as $f) {
    if (!array_key_exists($f, $body)) {
        jsonError("Missing required field: '$f'");
    }
    if (!is_numeric($body[$f])) {
        jsonError("Field '$f' must be numeric");
    }
}

$suhu     = (float)$body['suhu'];
$moisture = (float)$body['moisture'];
$gas      = (float)$body['gas'];
$deviceId = isset($body['device_id']) ? trim($body['device_id']) : 'D1R32_01';
$ts       = isset($body['timestamp'])
            ? trim($body['timestamp'])
            : date('Y-m-d\TH:i:s');

// ── Range validation ─────────────────────────────────────────
validateRange($suhu,     0,   100, 'suhu');
validateRange($moisture, 0,   100, 'moisture');
validateRange($gas,      0,  1000, 'gas');

// ── SPRT Phase Detection ─────────────────────────────────────
[$fasePred, $faseNama, $ct, $cm, $cg, ] = detectPhase($suhu, $moisture, $gas);

// ── IKK Calculation ──────────────────────────────────────────
$ikkResult = computeIKK($suhu, $moisture, $gas, $fasePred);
$ikk       = $ikkResult['ikk'];

// ── Alerts ───────────────────────────────────────────────────
$alerts     = computeAlerts($suhu, $moisture, $gas, $ikk);
$recommend  = buildRecommendation($alerts);

// ── Database INSERT ───────────────────────────────────────────
$db  = getDB();
$raw = json_encode($body);
$stmt = $db->prepare("
    INSERT INTO sensor_data
        (device_id, timestamp, suhu, moisture, gas,
         fase_pred, fase_nama, ikk,
         sprt_cusum_t, sprt_cusum_m, sprt_cusum_g,
         raw_payload)
    VALUES
        (:dev, :ts, :su, :mo, :ga,
         :fp, :fn, :ik,
         :ct, :cm, :cg,
         :raw)
");
$stmt->execute([
    ':dev' => $deviceId,  ':ts'  => $ts,
    ':su'  => $suhu,      ':mo'  => $moisture,  ':ga' => $gas,
    ':fp'  => $fasePred,  ':fn'  => $faseNama,  ':ik' => $ikk,
    ':ct'  => $ct,        ':cm'  => $cm,         ':cg' => $cg,
    ':raw' => $raw,
]);
$rowId = (int)$db->lastInsertId();

// ── Hourly Aggregation Update ────────────────────────────────
// hour_bucket = "2024-03-15 14" (tanggal + jam)
$hourBucket = substr(str_replace('T', ' ', $ts), 0, 13);
updateHourlyAggregation($db, $deviceId, $hourBucket);

// ── Response ─────────────────────────────────────────────────
jsonOut([
    'id'        => $rowId,
    'status'    => 'ok',
    'timestamp' => $ts,
    'device_id' => $deviceId,
    'sensors'   => [
        'suhu'     => $suhu,
        'moisture' => $moisture,
        'gas'      => $gas,
    ],
    'analysis'  => [
        'fase_pred' => $fasePred,
        'fase_nama' => $faseNama,
        'ikk'       => $ikk,
        'scores'    => [
            's_t' => $ikkResult['s_t'],
            's_m' => $ikkResult['s_m'],
            's_g' => $ikkResult['s_g'],
        ],
        'sprt'      => [
            'cusum_t' => $ct,
            'cusum_m' => $cm,
            'cusum_g' => $cg,
        ],
    ],
    'alerts'        => $alerts,
    'recommendation'=> $recommend,
], 201);
