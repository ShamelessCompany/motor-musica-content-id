"""Checks de Publicacion: Content ID, Sonoridad y Similitud con las Fuentes.

Antes de publicar un tema inspirado en links de YouTube hay que demostrar dos cosas
a la vez:

1. Que *se parece* a la fuente en lo que no es protegible (tempo, tonalidad, color
   armonico global). Se mide con la correlacion del perfil 12-croma y el tempo.
2. Que *no contiene* audio ni melodia de la fuente. Se mide con una huella acustica
   por constelaciones de picos espectrales (el mismo principio que usan Content ID /
   Shazam): si el tema generado compartiera grabacion con la fuente, muchos hashes
   coincidirian con el mismo desfase temporal.

Ademas se verifican los invariantes del proyecto: -14 LUFS, True Peak <= -1.0 dBFS,
cero muestras clipeadas y composicion 100% a partir de eventos sintetizados.
"""

from dataclasses import asdict, dataclass
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .synth_renderer import AudioMetrics
from .theory import Key, circle_distance

TARGET_LUFS = -14.0
LUFS_TOLERANCE = 2.0
TRUE_PEAK_CEILING_DBFS = -1.0
# Fraccion de hashes del tema que coinciden con la fuente en un mismo desfase.
# Calibrado: la misma grabacion desplazada unos segundos da ~0.5-0.9; temas
# distintos (aun en la misma tonalidad y con los mismos sintes) quedan ~0.04.
FINGERPRINT_MAX_MATCH = 0.15
MIN_TONAL_AFFINITY = 0.45  # calibrado: secciones en la tonalidad de su fuente dan 0.47-0.97
MAX_KEY_STEPS = 1  # misma tonalidad, relativa o vecina en el circulo de quintas (o misma tonica)
MAX_TEMPO_DIFF_PCT = 8.0

_FP_SR = 11025
_FP_NFFT = 1024
_FP_HOP = 512
_FP_BANDS = [(6, 24), (24, 48), (48, 96), (96, 192), (192, 400)]  # bins de frecuencia
_FP_FAN_OUT = 3
_FP_MAX_DT = 24


@dataclass
class CheckResult:
    check: str
    passed: bool
    value: Optional[float]
    detail: str


def _to_mono(audio: np.ndarray) -> np.ndarray:
    return np.mean(audio, axis=1) if audio.ndim > 1 else audio


def _resample_linear(mono: np.ndarray, sr: int, target_sr: int) -> np.ndarray:
    if sr == target_sr or len(mono) == 0:
        return mono.astype(np.float32)
    n_out = int(len(mono) * target_sr / sr)
    x_old = np.arange(len(mono)) / sr
    x_new = np.arange(n_out) / target_sr
    return np.interp(x_new, x_old, mono).astype(np.float32)


def landmark_hashes(audio: np.ndarray, sr: int) -> List[Tuple[Tuple[int, int, int], int]]:
    """Huella por constelacion de picos: lista de (hash, frame)."""
    mono = _resample_linear(_to_mono(audio), sr, _FP_SR)
    if len(mono) < _FP_NFFT:
        return []
    window = np.hanning(_FP_NFFT)
    n_frames = 1 + (len(mono) - _FP_NFFT) // _FP_HOP
    frames = np.lib.stride_tricks.as_strided(
        mono,
        shape=(n_frames, _FP_NFFT),
        strides=(mono.strides[0] * _FP_HOP, mono.strides[0]),
    )
    spec = np.log1p(np.abs(np.fft.rfft(frames * window, axis=1)))

    peaks: List[Tuple[int, int]] = []
    for t_idx in range(n_frames):
        row = spec[t_idx]
        floor = float(np.median(row)) + 0.5
        for lo, hi in _FP_BANDS:
            band = row[lo:hi]
            f_rel = int(np.argmax(band))
            if band[f_rel] > floor:
                peaks.append((t_idx, lo + f_rel))

    hashes: List[Tuple[Tuple[int, int, int], int]] = []
    for i, (t1, f1) in enumerate(peaks):
        paired = 0
        for t2, f2 in peaks[i + 1:]:
            dt = t2 - t1
            if dt <= 0:
                continue
            if dt > _FP_MAX_DT:
                break
            hashes.append(((f1, f2, dt), t1))
            paired += 1
            if paired >= _FP_FAN_OUT:
                break
    return hashes


def fingerprint_match_ratio(
    generated: np.ndarray,
    generated_sr: int,
    reference: np.ndarray,
    reference_sr: int,
) -> float:
    """Fraccion de hashes del tema generado que coinciden con la referencia en el mismo desfase."""
    return hash_match_ratio(landmark_hashes(generated, generated_sr), landmark_hashes(reference, reference_sr))


def hash_match_ratio(
    gen_hashes: Sequence[Tuple[Tuple[int, int, int], int]],
    ref_hashes: Sequence[Tuple[Tuple[int, int, int], int]],
) -> float:
    """Igual que fingerprint_match_ratio pero con huellas ya calculadas (p. ej. guardadas en JSON)."""
    gen_hashes = [(tuple(h), int(t)) for h, t in gen_hashes]
    ref_hashes = [(tuple(h), int(t)) for h, t in ref_hashes]
    if not gen_hashes or not ref_hashes:
        return 0.0
    index: Dict[Tuple[int, int, int], List[int]] = defaultdict(list)
    for h, t in ref_hashes:
        index[h].append(t)
    offsets: Counter = Counter()
    for h, t in gen_hashes:
        for t_ref in index.get(h, ()):
            offsets[t_ref - t] += 1
    if not offsets:
        return 0.0
    best = offsets.most_common(1)[0][1]
    return min(1.0, best / float(min(len(gen_hashes), len(ref_hashes))))


def _pearson(a: np.ndarray, b: np.ndarray) -> float:
    if np.std(a) < 1e-9 or np.std(b) < 1e-9:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def key_vector(chroma: Sequence[float]) -> np.ndarray:
    """Correlacion del croma con las 24 tonalidades (Krumhansl-Schmuckler): 12 mayores + 12 menores."""
    from .youtube_dna import MAJOR_PROFILE, MINOR_PROFILE

    c = np.asarray(chroma, dtype=np.float64)
    return np.array([
        _pearson(c, np.roll(profile, i)) for profile in (MAJOR_PROFILE, MINOR_PROFILE) for i in range(12)
    ])


def detect_key(chroma: Sequence[float]) -> Key:
    idx = int(np.argmax(key_vector(chroma)))
    return Key(idx % 12, "major" if idx < 12 else "minor")


def tonal_affinity(chroma_a: Sequence[float], chroma_b: Sequence[float]) -> float:
    """Parecido de 'color tonal' (1.0 = mismas tensiones hacia las mismas tonalidades).

    Se comparan los vectores de 24 tonalidades y no los cromas crudos: asi un tema
    en La menor se parece mas a otro en La menor que a uno en Re menor aunque
    compartan casi todas las notas.
    """
    return _pearson(key_vector(chroma_a), key_vector(chroma_b))


def tempo_diff_pct(bpm_a: float, bpm_b: float) -> float:
    """Diferencia de tempo en %, tolerando medio tiempo / doble tiempo."""
    from .theory import fold_bpm

    a, b = fold_bpm(bpm_a), fold_bpm(bpm_b)
    return abs(a - b) / b * 100.0


def check_master(metrics: AudioMetrics) -> List[CheckResult]:
    lufs_ok = abs(metrics.estimated_lufs - TARGET_LUFS) <= LUFS_TOLERANCE
    return [
        CheckResult(
            "sonoridad_lufs",
            lufs_ok,
            round(metrics.estimated_lufs, 2),
            f"Objetivo {TARGET_LUFS} LUFS (+/-{LUFS_TOLERANCE} LU, sonoridad integrada ITU-R BS.1770)",
        ),
        CheckResult(
            "true_peak",
            metrics.peak_dbfs <= TRUE_PEAK_CEILING_DBFS + 0.05,
            round(metrics.peak_dbfs, 2),
            f"Techo {TRUE_PEAK_CEILING_DBFS} dBFS",
        ),
        CheckResult(
            "sin_clipping",
            metrics.clipped_samples == 0,
            float(metrics.clipped_samples),
            "Cero muestras a escala completa",
        ),
    ]


def check_no_samples(events_only: bool) -> CheckResult:
    return CheckResult(
        "cero_samples",
        events_only,
        None,
        "Todas las notas salen de eventos MIDI sintetizados; el audio de los links solo se mide y se descarta",
    )


def check_fingerprint(label: str, ratio: float) -> CheckResult:
    return CheckResult(
        f"huella_content_id[{label}]",
        ratio < FINGERPRINT_MAX_MATCH,
        round(ratio, 4),
        f"Coincidencia de huella < {FINGERPRINT_MAX_MATCH:.0%} (audio identico ~100%)",
    )


def check_similarity(
    label: str,
    affinity: float,
    generated_key: Key,
    source_key: Key,
    tempo_pct: float,
    enforce_tempo: bool = True,
) -> CheckResult:
    """El tema debe sonar en la tonalidad de la fuente (o vecina) con color tonal parecido."""
    steps = circle_distance(generated_key, source_key)
    # Misma tonica (A menor / A mayor) cuenta como el mismo centro tonal: en secciones
    # cortas la dominante con sensible empuja la medicion hacia la paralela mayor.
    same_center = steps <= MAX_KEY_STEPS or generated_key.pitch_class == source_key.pitch_class
    passed = affinity >= MIN_TONAL_AFFINITY and same_center
    tempo_txt = f"tempo a {tempo_pct:.1f}%"
    if enforce_tempo:
        passed = passed and tempo_pct <= MAX_TEMPO_DIFF_PCT
        tempo_txt += f" (max {MAX_TEMPO_DIFF_PCT:.0f}%)"
    else:
        tempo_txt += " (fusion: tempo unificado, informativo)"
    return CheckResult(
        f"similitud_fuente[{label}]",
        passed,
        round(affinity, 3),
        f"Medido {generated_key.name} vs fuente {source_key.name} ({steps} paso(s) en el circulo); "
        f"afinidad tonal >= {MIN_TONAL_AFFINITY}; {tempo_txt}",
    )


def summarize(checks: List[CheckResult]) -> Dict[str, object]:
    return {
        "aprobado": all(c.passed for c in checks),
        "checks": [asdict(c) for c in checks],
    }
