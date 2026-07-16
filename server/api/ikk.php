<?php
/**
 * KomposIoT PHP Server — Indeks Kesehatan Kompos (IKK)
 * File: /kompos/api/ikk.php
 *
 * IKK = 0.40 × S_T + 0.35 × S_M + 0.25 × S_G  (× 100)
 * Setiap skor dievaluasi terhadap rentang optimal fase saat ini.
 */
require_once __DIR__ . '/config.php';

/**
 * Hitung satu skor komponen (0.0–1.0) dengan soft decay di luar range.
 */
function scoreComponent(float $val, float $lo, float $hi,
                        float $margin = 0.25): float {
    $span = $hi - $lo;
    if ($val >= $lo && $val <= $hi) return 1.0;
    if ($val < $lo) return max(0.0, 1.0 - ($lo - $val) / ($span * $margin + 1));
    return max(0.0, 1.0 - ($val - $hi) / ($span * $margin + 1));
}

/**
 * Hitung IKK (0–100) berdasarkan nilai sensor dan fase yang terdeteksi.
 * Kembalikan ['ikk'=>float, 's_t'=>float, 's_m'=>float, 's_g'=>float]
 */
function computeIKK(float $suhu, float $moisture, float $gas,
                    int $fase): array {
    $r   = FASE_RANGES[$fase];
    $s_t = scoreComponent($suhu,     $r['suhu'][0],     $r['suhu'][1]);
    $s_m = scoreComponent($moisture, $r['moisture'][0], $r['moisture'][1]);
    $s_g = scoreComponent($gas,      $r['gas'][0],      $r['gas'][1]);

    $ikk = (IKK_W_T * $s_t + IKK_W_M * $s_m + IKK_W_G * $s_g) * 100.0;
    return [
        'ikk' => round(min(100.0, max(0.0, $ikk)), 2),
        's_t' => round($s_t, 4),
        's_m' => round($s_m, 4),
        's_g' => round($s_g, 4),
    ];
}

/**
 * Hasilkan daftar alert berdasarkan nilai sensor.
 */
function computeAlerts(float $suhu, float $moisture,
                       float $gas,  float $ikk): array {
    $alerts = [];
    if ($moisture < 38)  $alerts[] = 'MOISTURE_LOW';
    if ($moisture > 72)  $alerts[] = 'MOISTURE_HIGH';
    if ($gas      > 500) $alerts[] = 'GAS_CRITICAL';
    if ($suhu     > 70)  $alerts[] = 'TEMP_CRITICAL';
    if ($ikk      < 40)  $alerts[] = 'IKK_CRITICAL';
    return $alerts;
}

/**
 * Teks rekomendasi berbasis kondisi terakhir.
 */
function buildRecommendation(array $alerts): string {
    if (empty($alerts)) return 'Semua parameter dalam kondisi normal.';
    $msgs = [
        'MOISTURE_LOW'  => 'Kelembapan rendah — segera lakukan penyiraman.',
        'MOISTURE_HIGH' => 'Kelembapan tinggi — kurangi penyiraman dan tingkatkan aerasi.',
        'GAS_CRITICAL'  => 'Konsentrasi gas berbahaya — lakukan pembalikan segera.',
        'TEMP_CRITICAL' => 'Suhu terlalu tinggi (>70°C) — turunkan dengan penyiraman.',
        'IKK_CRITICAL'  => 'IKK kritis — periksa semua parameter dan lakukan intervensi.',
    ];
    $out = [];
    foreach ($alerts as $a) {
        if (isset($msgs[$a])) $out[] = $msgs[$a];
    }
    return implode(' ', $out);
}
