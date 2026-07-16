<?php
/**
 * KomposIoT PHP Server — SPRT-CUSUM Engine + Bayesian Fusion
 * File: /kompos/api/sprt.php
 *
 * PHP tidak menyimpan state antar request, sehingga SPRT accumulator
 * disimpan ke file JSON dan dibaca ulang setiap request POST.
 */
require_once __DIR__ . '/config.php';

/** Load SPRT state dari file JSON, atau inisialisasi baru. */
function loadSprtState(): array {
    $dir = dirname(SPRT_STATE_FILE);
    if (!is_dir($dir)) mkdir($dir, 0775, true);

    if (file_exists(SPRT_STATE_FILE)) {
        $raw = file_get_contents(SPRT_STATE_FILE);
        $st  = json_decode($raw, true);
        if (is_array($st)) return $st;
    }
    return initSprtState();
}

/** Inisialisasi state kosong untuk 18 hipotesis. */
function initSprtState(): array {
    $state = [];
    foreach (SPRT_HYPOTHESES as $h) {
        $key          = "{$h[0]}_f{$h[4]}";
        $state[$key]  = ['cusum' => 0.0, 'detections' => 0];
    }
    return $state;
}

/** Simpan SPRT state ke file JSON. */
function saveSprtState(array $state): void {
    file_put_contents(
        SPRT_STATE_FILE,
        json_encode($state),
        LOCK_EX
    );
}

/**
 * Update satu SPRT-CUSUM accumulator.
 * Mengembalikan [cusum_baru, detected] di mana detected: 1=H1, -1=H0, 0=continue
 */
function sprtUpdate(array &$state, string $key, float $val,
                    float $mu0, float $mu1, float $sigma): array {
    // Log-likelihood ratio inkremental (Wald, 1947)
    $llr = (($val - $mu0) * ($mu1 - $mu0) / ($sigma ** 2))
         - (($mu1 - $mu0) ** 2 / (2 * $sigma ** 2));

    $state[$key]['cusum'] += $llr;
    $detected = 0;

    if ($state[$key]['cusum'] >= SPRT_A) {
        $detected = 1;
        $state[$key]['cusum'] = 0.0;   // reset setelah deteksi H1
        $state[$key]['detections']++;
    } elseif ($state[$key]['cusum'] <= SPRT_B) {
        $detected = -1;
        $state[$key]['cusum'] = 0.0;   // reset setelah konfirmasi H0
    }

    return [$state[$key]['cusum'], $detected];
}

/**
 * Sigmoid: konversi CUSUM → probabilitas [0,1]
 */
function sigmoid(float $x, float $scale = 1.0): float {
    return 1.0 / (1.0 + exp(-$x / max(abs($scale), 0.01)));
}

/**
 * Jalankan semua 18 hipotesis SPRT dan hitung skor per fase.
 * Kembalikan [fase_pred, fase_nama, cusum_t, cusum_m, cusum_g, $state]
 */
function detectPhase(float $suhu, float $moisture, float $gas): array {
    // Load state dari file (persisten antar request)
    $state = loadSprtState();

    // Prior scores per fase
    $scores = array_fill(0, 6, 0.3);
    $cusum_t = $cusum_m = $cusum_g = 0.0;

    foreach (SPRT_HYPOTHESES as [$sensor, $mu0, $mu1, $sigma, $ftgt]) {
        $key = "{$sensor}_f{$ftgt}";
        $val = match($sensor) {
            'suhu'     => $suhu,
            'moisture' => $moisture,
            'gas'      => $gas,
            default    => 0.0,
        };

        // Pastikan key ada di state
        if (!isset($state[$key])) {
            $state[$key] = ['cusum' => 0.0, 'detections' => 0];
        }

        [$cusum, ] = sprtUpdate($state, $key, $val, $mu0, $mu1, $sigma);
        $prob = sigmoid($cusum, SPRT_A);
        $scores[$ftgt] += $prob * 1.2;

        // Track representative cusum per sensor
        if ($sensor === 'suhu'     && $ftgt === 1) $cusum_t = $cusum;
        if ($sensor === 'moisture' && $ftgt === 1) $cusum_m = $cusum;
        if ($sensor === 'gas'      && $ftgt === 2) $cusum_g = $cusum;
    }

    // ── Bayesian Threshold Fusion ──────────────────────────
    $fused = [];
    $totalPrior = array_sum($scores);
    foreach (range(0, 5) as $f) {
        $r  = FASE_RANGES[$f];
        $lk = softMembership($suhu,     $r['suhu'][0],     $r['suhu'][1],     8.0)
            * softMembership($moisture, $r['moisture'][0], $r['moisture'][1], 10.0)
            * softMembership($gas,      $r['gas'][0],      $r['gas'][1],      40.0);
        $prior      = $scores[$f] / max($totalPrior, 1e-9);
        $fused[$f]  = $prior * ($lk + 0.05);
    }

    $totalFused = array_sum($fused);
    if ($totalFused > 0) {
        foreach ($fused as &$v) $v /= $totalFused;
    }

    // argmax
    $fasePred = (int)array_keys($fused, max($fused))[0];

    // Simpan state yang sudah diupdate
    saveSprtState($state);

    return [
        $fasePred,
        FASE_DEF[$fasePred]['nama'],
        round($cusum_t, 4),
        round($cusum_m, 4),
        round($cusum_g, 4),
        $state,
    ];
}

/** Reset semua SPRT state ke nol. */
function resetSprtState(): void {
    saveSprtState(initSprtState());
}

/** Ambil state saat ini tanpa modifikasi. */
function getSprtStateSummary(): array {
    $state = loadSprtState();
    $summary = [];
    foreach ($state as $key => $val) {
        $summary[$key] = [
            'cusum'      => round($val['cusum'], 4),
            'detections' => (int)$val['detections'],
        ];
    }
    return $summary;
}
