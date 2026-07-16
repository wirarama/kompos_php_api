<?php
/**
 * KomposIoT PHP Server — Database Helper (PDO SQLite)
 * File: /kompos/api/db.php
 */
require_once __DIR__ . '/config.php';

function getDB(): PDO {
    static $pdo = null;
    if ($pdo !== null) return $pdo;

    $dir = dirname(DB_PATH);
    if (!is_dir($dir)) mkdir($dir, 0775, true);

    $pdo = new PDO('sqlite:' . DB_PATH);
    $pdo->setAttribute(PDO::ATTR_ERRMODE,            PDO::ERRMODE_EXCEPTION);
    $pdo->setAttribute(PDO::ATTR_DEFAULT_FETCH_MODE, PDO::FETCH_ASSOC);
    $pdo->exec('PRAGMA journal_mode=WAL');
    $pdo->exec('PRAGMA synchronous=NORMAL');

    initSchema($pdo);
    return $pdo;
}

function initSchema(PDO $db): void {
    $db->exec("
      CREATE TABLE IF NOT EXISTS sensor_data (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id      TEXT NOT NULL DEFAULT 'D1R32_01',
        timestamp      TEXT NOT NULL,
        suhu           REAL NOT NULL,
        moisture       REAL NOT NULL,
        gas            REAL NOT NULL,
        fase_pred      INTEGER NOT NULL DEFAULT 0,
        fase_nama      TEXT    NOT NULL DEFAULT 'Mesophilik Awal',
        ikk            REAL    NOT NULL DEFAULT 0.0,
        sprt_cusum_t   REAL DEFAULT 0.0,
        sprt_cusum_m   REAL DEFAULT 0.0,
        sprt_cusum_g   REAL DEFAULT 0.0,
        raw_payload    TEXT,
        created_at     TEXT DEFAULT (datetime('now','localtime'))
      )");
    $db->exec("CREATE INDEX IF NOT EXISTS idx_ts  ON sensor_data(timestamp)");
    $db->exec("CREATE INDEX IF NOT EXISTS idx_dev ON sensor_data(device_id)");

    $db->exec("
      CREATE TABLE IF NOT EXISTS aggregation_hourly (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        hour_bucket    TEXT NOT NULL,
        device_id      TEXT NOT NULL DEFAULT 'D1R32_01',
        suhu_mean      REAL, suhu_min  REAL, suhu_max  REAL, suhu_std  REAL,
        moisture_mean  REAL, moisture_min REAL, moisture_max REAL, moisture_std REAL,
        gas_mean       REAL, gas_min   REAL, gas_max   REAL, gas_std   REAL,
        ikk_mean       REAL, ikk_min   REAL, ikk_max   REAL,
        fase_mode      INTEGER,
        sample_count   INTEGER,
        updated_at     TEXT DEFAULT (datetime('now','localtime')),
        UNIQUE(hour_bucket, device_id)
      )");
}

function updateHourlyAggregation(PDO $db,
                                  string $deviceId,
                                  string $hourBucket): void {
    $rows = $db->prepare("
        SELECT suhu, moisture, gas, ikk, fase_pred
        FROM   sensor_data
        WHERE  device_id = :dev
          AND  strftime('%Y-%m-%d %H', timestamp) = :bkt");
    $rows->execute([':dev' => $deviceId, ':bkt' => $hourBucket]);
    $data = $rows->fetchAll();
    if (empty($data)) return;

    $S = $M = $G = $K = $F = [];
    foreach ($data as $r) {
        $S[] = (float)$r['suhu'];
        $M[] = (float)$r['moisture'];
        $G[] = (float)$r['gas'];
        $K[] = (float)$r['ikk'];
        $F[] = (int)$r['fase_pred'];
    }

    $fc = array_count_values($F);
    arsort($fc);
    $fm = (int)array_key_first($fc);

    function _stats(array $a): array {
        $n = count($a); $mu = array_sum($a) / $n;
        $v = 0; foreach ($a as $x) $v += ($x - $mu) ** 2;
        return [round($mu,3), round(min($a),3),
                round(max($a),3), round($n > 1 ? sqrt($v/$n) : 0, 3)];
    }
    [$sm,$sn,$sx,$ss] = _stats($S);
    [$mm,$mn,$mx,$ms] = _stats($M);
    [$gm,$gn,$gx,$gs] = _stats($G);
    [$im,$in,$ix,]    = _stats($K);

    $db->prepare("
        INSERT INTO aggregation_hourly
          (hour_bucket,device_id,
           suhu_mean,suhu_min,suhu_max,suhu_std,
           moisture_mean,moisture_min,moisture_max,moisture_std,
           gas_mean,gas_min,gas_max,gas_std,
           ikk_mean,ikk_min,ikk_max,fase_mode,sample_count,updated_at)
        VALUES
          (:bkt,:dev, :sm,:sn,:sx,:ss, :mm,:mn,:mx,:ms,
           :gm,:gn,:gx,:gs, :im,:in,:ix, :fm,:cnt,
           datetime('now','localtime'))
        ON CONFLICT(hour_bucket,device_id) DO UPDATE SET
          suhu_mean=excluded.suhu_mean, suhu_min=excluded.suhu_min,
          suhu_max=excluded.suhu_max,   suhu_std=excluded.suhu_std,
          moisture_mean=excluded.moisture_mean, moisture_min=excluded.moisture_min,
          moisture_max=excluded.moisture_max,   moisture_std=excluded.moisture_std,
          gas_mean=excluded.gas_mean,   gas_min=excluded.gas_min,
          gas_max=excluded.gas_max,     gas_std=excluded.gas_std,
          ikk_mean=excluded.ikk_mean,   ikk_min=excluded.ikk_min,
          ikk_max=excluded.ikk_max,     fase_mode=excluded.fase_mode,
          sample_count=excluded.sample_count,
          updated_at=excluded.updated_at
    ")->execute([
        ':bkt'=>$hourBucket, ':dev'=>$deviceId,
        ':sm'=>$sm,':sn'=>$sn,':sx'=>$sx,':ss'=>$ss,
        ':mm'=>$mm,':mn'=>$mn,':mx'=>$mx,':ms'=>$ms,
        ':gm'=>$gm,':gn'=>$gn,':gx'=>$gx,':gs'=>$gs,
        ':im'=>$im,':in'=>$in,':ix'=>$ix,
        ':fm'=>$fm,':cnt'=>count($data),
    ]);
}
