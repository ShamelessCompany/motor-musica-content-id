"""Importar Playlist: clasificar temas por genero y componer temas originales parecidos.

Flujo:
1. Se listan los videos de una playlist de YouTube (publica o no listada) con yt-dlp,
   sin descargar nada todavia.
2. De cada tema se descargan ~30 s, se miden rasgos ABSTRACTOS y el audio se borra:
   tempo, tonalidad/modo, brillo, peso de graves, percusividad, densidad ritmica,
   energia y una huella acustica (hashes, no audio) para el check de Content ID.
3. Cada tema se clasifica por genero comparando esos rasgos con un prototipo por
   genero del motor (reglas explicables, no una red neuronal).
4. Por tema (o por grupo de genero) se compone un tema 100% nuevo con el compositor
   del genero, llevado al tempo y la tonalidad medidos.

Lo que NO se hace, a proposito: transcribir la melodia, la letra, el riff ni la
partitura de la fuente. Eso seria una obra derivada (no monetizable) y Content ID la
reclamaria. Solo se toma lo que no es protegible: tempo, tonalidad y "color" sonoro.
"""

from dataclasses import asdict, dataclass, field
import random
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .content_id_checks import (
    MAX_KEY_STEPS,
    CheckResult,
    check_fingerprint,
    check_similarity,
    detect_key,
    hash_match_ratio,
    landmark_hashes,
    tempo_diff_pct,
    tonal_affinity,
)
from .harmonic_fusion import _read_wav_mono
from .instruments import SOUND_PACKS, resolve_rack
from .midi_generator import generate_track_midi
from .song_editor import MAX_BPM, MIN_BPM, SongProject, project_for_generated, render_project
from .theory import GENRES, circle_distance, parse_key_name
from .youtube_dna import analyze_loaded_audio, compute_chroma, load_source_audio

MAX_PLAYLIST_ITEMS = 25
DEFAULT_PLAYLIST_ITEMS = 10
# Al elegir al azar se listan como maximo estos videos (listar es rapido: no baja audio)
SHUFFLE_POOL = 500
# Intentos (semillas) por tema antes de entregar uno que no pasa los checks
COMPOSE_ATTEMPTS = 3
# Si el 1er y 2do genero quedan a menos de esto, la clasificacion se marca como dudosa
AMBIGUOUS_MARGIN = 0.08

LIMITATION_NOTE = (
    "Se extraen solo rasgos abstractos (tempo, tonalidad, modo, brillo, graves, percusion, "
    "densidad ritmica, energia). No se transcribe la melodia, la letra ni la partitura de "
    "ningun tema: copiarla haria una obra derivada que Content ID reclamaria. Cada tema "
    "nuevo se compone desde cero y se verifica con la huella acustica."
)


@dataclass(frozen=True)
class GenrePrototype:
    """Rasgos tipicos de cada genero del motor (valores medidos en musica comercial)."""
    bpm: float
    minor: float  # 1.0 = casi siempre menor
    brightness_hz: float
    bass_ratio: float
    percussiveness: float
    onset_rate: float  # golpes / notas por segundo


GENRE_PROTOTYPES: Dict[str, GenrePrototype] = {
    "dark_trap": GenrePrototype(140, 0.9, 1700, 0.62, 0.50, 4.5),
    "boom_bap": GenrePrototype(90, 0.7, 1600, 0.45, 0.55, 3.0),
    "hard_rock": GenrePrototype(136, 0.5, 2700, 0.22, 0.48, 5.0),
    "epic_cinematic": GenrePrototype(120, 0.8, 1900, 0.30, 0.32, 3.5),
    "synthwave": GenrePrototype(122, 0.6, 2300, 0.35, 0.45, 4.0),
    "lofi_chill": GenrePrototype(80, 0.6, 1250, 0.35, 0.40, 2.2),
}

# Cuanto pesa cada rasgo y que diferencia se considera "lejos" (sigma)
_WEIGHTS = {"bpm": 4.0, "minor": 0.8, "brightness_hz": 1.5, "bass_ratio": 1.5, "percussiveness": 1.0, "onset_rate": 1.0}
_SIGMAS = {"bpm": 10.0, "minor": 0.5, "brightness_hz": 450.0, "bass_ratio": 0.15, "percussiveness": 0.12, "onset_rate": 1.5}
# Sonido por defecto (AUTO) de cada genero: los paquetes del rack que mejor lo representan
GENRE_RACKS: Dict[str, Dict[str, str]] = {
    "lofi_chill": SOUND_PACKS["lofi"].rack,
    "dark_trap": SOUND_PACKS["trap"].rack,
    "hard_rock": SOUND_PACKS["rock"].rack,
    "synthwave": SOUND_PACKS["synthwave"].rack,
    "epic_cinematic": SOUND_PACKS["orquestal"].rack,
    "boom_bap": {"lead": "piano", "pad": "brass_section", "bass": "upright_pluck", "drums": "lofi_kit"},
}
_FEATURE_NAMES = {
    "bpm": "tempo", "minor": "modo", "brightness_hz": "brillo", "bass_ratio": "graves",
    "percussiveness": "percusion", "onset_rate": "densidad ritmica",
}


@dataclass
class PlaylistEntry:
    index: int
    url: str
    title: str
    duration_sec: Optional[float] = None


@dataclass
class StyleFeatures:
    """Ficha de estilo de un tema: solo numeros, nada de audio ni notas."""
    bpm: int
    key: str
    mode: str
    confidence: float
    brightness_hz: float
    bass_ratio: float
    percussiveness: float
    onset_rate: float
    energy_db: float
    chroma: List[float] = field(default_factory=list)


@dataclass
class PlaylistTrack:
    index: int
    url: str
    title: str
    duration_sec: Optional[float] = None
    features: Optional[StyleFeatures] = None
    genre: Optional[str] = None
    genre_confidence: float = 0.0
    genre_ranking: List[Dict[str, object]] = field(default_factory=list)
    genre_reason: str = ""
    ambiguous: bool = False
    genre_overridden: bool = False
    error: Optional[str] = None
    # Huella acustica (hashes de picos espectrales). No permite reconstruir el audio.
    fingerprint: List = field(default_factory=list)

    def to_dict(self, with_fingerprint: bool = True) -> Dict:
        data = asdict(self)
        if not with_fingerprint:
            data.pop("fingerprint", None)
        return data

    @staticmethod
    def from_dict(data: Dict) -> "PlaylistTrack":
        data = dict(data)
        if data.get("features"):
            data["features"] = StyleFeatures(**data["features"])
        known = PlaylistTrack.__dataclass_fields__.keys()
        return PlaylistTrack(**{k: v for k, v in data.items() if k in known})


# ---------------------------------------------------------------------------
# 1. Listar la playlist
# ---------------------------------------------------------------------------

def _entry_url(entry: Dict) -> Optional[str]:
    url = entry.get("webpage_url") or entry.get("url")
    if url and url.startswith("http"):
        return url
    vid = entry.get("id") or url
    return f"https://www.youtube.com/watch?v={vid}" if vid else None


def list_playlist_entries(
    url: str,
    limit: int = DEFAULT_PLAYLIST_ITEMS,
    shuffle: bool = False,
    rng: Optional[random.Random] = None,
) -> Tuple[str, List[PlaylistEntry]]:
    """Titulo de la playlist y `limit` videos (sin descargar audio): los primeros, o al azar.

    Funciona con playlists no listadas: basta con tener el link. Un link de un solo
    video devuelve una lista de 1. Con `shuffle` se lista hasta SHUFFLE_POOL videos y se
    eligen `limit` al azar (en el orden de la playlist).
    """
    import yt_dlp

    limit = max(1, min(int(limit), MAX_PLAYLIST_ITEMS))
    opts = {"quiet": True, "no_warnings": True, "extract_flat": "in_playlist",
            "playlistend": SHUFFLE_POOL if shuffle else limit, "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        raise ValueError("No se pudo leer la playlist")
    raw = info.get("entries")
    if raw is None:  # link de un solo video
        raw = [info]
    items = [item for item in raw if item and _entry_url(item)]
    if shuffle and len(items) > limit:
        picked = sorted((rng or random).sample(range(len(items)), limit))
        items = [items[i] for i in picked]
    entries: List[PlaylistEntry] = []
    for item in items[:limit]:
        link = _entry_url(item)
        entries.append(PlaylistEntry(len(entries), link, item.get("title") or link, item.get("duration")))
    if not entries:
        raise ValueError("La playlist no tiene videos accesibles (privados o borrados)")
    return info.get("title") or "Playlist", entries


# ---------------------------------------------------------------------------
# 2. Rasgos abstractos
# ---------------------------------------------------------------------------

def measure_onset_rate(mono: np.ndarray, sr: int) -> float:
    """Golpes / ataques por segundo (picos del flujo espectral). Mide densidad ritmica."""
    n_fft, hop = 1024, 512
    if len(mono) < n_fft * 4:
        return 0.0
    window = np.hanning(n_fft)
    frames = np.array([mono[s:s + n_fft] * window for s in range(0, len(mono) - n_fft, hop)])
    mag = np.log1p(np.abs(np.fft.rfft(frames, axis=1)) * 10.0)
    flux = np.maximum(0.0, np.diff(mag, axis=0)).sum(axis=1)
    if not np.any(flux):
        return 0.0
    # Umbral adaptativo: media local + fraccion de la desviacion
    local = np.convolve(flux, np.ones(16) / 16.0, mode="same")
    thresh = local + 0.5 * np.std(flux)
    peaks = (flux[1:-1] > flux[:-2]) & (flux[1:-1] >= flux[2:]) & (flux[1:-1] > thresh[1:-1])
    # Ignorar picos a menos de ~50 ms entre si
    idx = np.flatnonzero(peaks) + 1
    min_gap = max(1, int(0.05 * sr / hop))
    kept = []
    for i in idx:
        if not kept or i - kept[-1] >= min_gap:
            kept.append(i)
    return round(len(kept) / (len(mono) / float(sr)), 2)


def extract_style_features(samples: np.ndarray, sr: int, label: str) -> Tuple[StyleFeatures, List]:
    """Ficha de estilo + huella de un buffer de audio (el buffer se descarta despues)."""
    dna = analyze_loaded_audio(samples, sr, label)
    mono = np.mean(samples, axis=1) if samples.ndim > 1 else samples
    rms = float(np.sqrt(np.mean(np.square(mono, dtype=np.float64)))) if len(mono) else 0.0
    features = StyleFeatures(
        bpm=dna.detected_bpm,
        key=dna.detected_key,
        mode="minor" if "minor" in dna.detected_key else "major",
        confidence=dna.confidence,
        brightness_hz=float(dna.brightness_hz or 2000.0),
        bass_ratio=float(dna.bass_ratio or 0.2),
        percussiveness=float(dna.percussiveness or 0.3),
        onset_rate=measure_onset_rate(mono, sr),
        energy_db=round(20.0 * np.log10(max(rms, 1e-9)), 1),
        chroma=list(dna.chroma or []),
    )
    fingerprint = [[list(h), int(t)] for h, t in landmark_hashes(mono, sr)]
    return features, fingerprint


# ---------------------------------------------------------------------------
# 3. Clasificacion por genero
# ---------------------------------------------------------------------------

def _gauss(diff: float, sigma: float) -> float:
    return float(np.exp(-0.5 * (diff / sigma) ** 2))


def _feature_scores(f: StyleFeatures, proto: GenrePrototype) -> Dict[str, float]:
    # Tempo: se acepta medio/doble tiempo (un trap a 140 se mide a veces a 70), con castigo
    raw = _gauss(f.bpm - proto.bpm, _SIGMAS["bpm"])
    folded = _gauss(tempo_diff_pct(f.bpm, proto.bpm) / 100.0 * proto.bpm, _SIGMAS["bpm"])
    return {
        "bpm": max(raw, 0.7 * folded),
        "minor": _gauss((1.0 if f.mode == "minor" else 0.0) - proto.minor, _SIGMAS["minor"]),
        "brightness_hz": _gauss(f.brightness_hz - proto.brightness_hz, _SIGMAS["brightness_hz"]),
        "bass_ratio": _gauss(f.bass_ratio - proto.bass_ratio, _SIGMAS["bass_ratio"]),
        "percussiveness": _gauss(f.percussiveness - proto.percussiveness, _SIGMAS["percussiveness"]),
        "onset_rate": _gauss(f.onset_rate - proto.onset_rate, _SIGMAS["onset_rate"]),
    }


def classify_genre(features: StyleFeatures) -> Tuple[str, float, List[Dict[str, object]], str, bool]:
    """Genero mas parecido entre los del motor.

    Devuelve (genero, confianza 0-1, ranking, razon legible, dudoso).
    """
    total_w = sum(_WEIGHTS.values())
    ranking = []
    for gid, proto in GENRE_PROTOTYPES.items():
        scores = _feature_scores(features, proto)
        score = sum(_WEIGHTS[k] * v for k, v in scores.items()) / total_w
        ranking.append({"genre": gid, "name": GENRES[gid].name, "score": round(score, 3), "_detail": scores})
    ranking.sort(key=lambda r: r["score"], reverse=True)
    best, second = ranking[0], ranking[1]
    ambiguous = best["score"] - second["score"] < AMBIGUOUS_MARGIN
    detail = best.pop("_detail")
    for r in ranking[1:]:
        r.pop("_detail", None)
    strong = sorted(detail, key=lambda k: _WEIGHTS[k] * detail[k], reverse=True)[:3]
    reason = (
        f"{', '.join(_FEATURE_NAMES[k] for k in strong)} parecidos a {best['name']} "
        f"({features.bpm} BPM, {features.key}, brillo {features.brightness_hz:.0f} Hz, "
        f"graves {features.bass_ratio:.0%}, percusion {features.percussiveness:.0%})"
    )
    if ambiguous:
        reason += f"; tambien podria ser {second['name']}"
    return best["genre"], float(best["score"]), ranking, reason, ambiguous


def apply_classification(track: PlaylistTrack) -> PlaylistTrack:
    genre, conf, ranking, reason, ambiguous = classify_genre(track.features)
    track.genre, track.genre_confidence, track.genre_ranking = genre, round(conf, 3), ranking
    track.genre_reason, track.ambiguous, track.genre_overridden = reason, ambiguous, False
    return track


def analyze_entry(entry: PlaylistEntry, loader: Callable = load_source_audio) -> PlaylistTrack:
    """Descarga ~30 s, mide, clasifica y descarta el audio. Los errores no frenan la playlist."""
    track = PlaylistTrack(entry.index, entry.url, entry.title, entry.duration_sec)
    try:
        samples, sr, _ = loader(entry.url, label=entry.title)
        track.features, track.fingerprint = extract_style_features(samples, sr, entry.title)
        apply_classification(track)
    except Exception as exc:  # video privado, borrado, bloqueado por region...
        track.error = (str(exc).splitlines() or ["error desconocido"])[0][:140]
    return track


def analyze_playlist_entries(
    entries: Sequence[PlaylistEntry],
    progress: Optional[Callable[[int, int, PlaylistTrack], None]] = None,
    loader: Callable = load_source_audio,
) -> List[PlaylistTrack]:
    tracks = []
    for i, entry in enumerate(entries):
        track = analyze_entry(entry, loader)
        tracks.append(track)
        if progress:
            progress(i + 1, len(entries), track)
    return tracks


def group_by_genre(tracks: Sequence[PlaylistTrack]) -> Dict[str, List[int]]:
    groups: Dict[str, List[int]] = {}
    for t in tracks:
        if t.genre and not t.error:
            groups.setdefault(t.genre, []).append(t.index)
    return dict(sorted(groups.items(), key=lambda kv: -len(kv[1])))


# ---------------------------------------------------------------------------
# 4. Componer temas originales parecidos
# ---------------------------------------------------------------------------

def target_bpm_for(genre: str, measured_bpm: float) -> int:
    """Tempo medido llevado a la octava de tempo del genero (70 medido -> 140 en trap)."""
    base = GENRES[genre].bpm
    options = [measured_bpm * f for f in (0.5, 1.0, 2.0)]
    best = min(options, key=lambda b: abs(b - base))
    return int(round(max(MIN_BPM, min(best, MAX_BPM))))


def transpose_for(genre: str, key_name: str) -> int:
    """Semitonos para llevar la tonica del genero a la tonalidad medida (por el camino corto).

    Los generos del motor son menores; una fuente mayor se lleva a su relativa menor
    (mismas notas, otro centro), asi el color armonico queda cerca.
    """
    key = parse_key_name(key_name)
    target_pc = key.pitch_class if key.mode == "minor" else (key.pitch_class + 9) % 12
    diff = (target_pc - GENRES[genre].root_note % 12) % 12
    return diff - 12 if diff > 6 else diff


@dataclass
class StyleTarget:
    """Lo que se le pide al compositor: genero + rasgos promedio de una o varias fuentes."""
    genre: str
    bpm: int
    key: str
    chroma: List[float]
    sources: List[PlaylistTrack]


def target_from_tracks(genre: str, tracks: Sequence[PlaylistTrack]) -> StyleTarget:
    """Promedia los rasgos de un grupo (o de un solo tema)."""
    feats = [t.features for t in tracks if t.features]
    if not feats:
        raise ValueError("Ningun tema del grupo tiene rasgos medidos")
    chroma = np.sum([np.asarray(f.chroma) for f in feats if f.chroma], axis=0) if any(f.chroma for f in feats) else np.zeros(12)
    key = feats[0].key if len(feats) == 1 or not np.any(chroma) else detect_key(chroma).name
    bpm = float(np.median([target_bpm_for(genre, f.bpm) for f in feats]))
    norm = float(np.max(chroma)) or 1.0
    return StyleTarget(genre, int(round(bpm)), key, [round(float(c) / norm, 4) for c in chroma], list(tracks))


def note_chroma(genre: str, seed: int, bars: int) -> np.ndarray:
    """Croma de las notas que escribe el compositor (duracion x velocidad, sin bateria)."""
    hist = np.zeros(12)
    for e in generate_track_midi(genre=genre, bars=bars, seed=seed).events:
        if e.channel != 9:
            hist[e.pitch % 12] += e.duration_sec * e.velocity
    return hist


def fitted_transpose(genre: str, seed: int, bars: int, target: "StyleTarget") -> int:
    """Semitonos que llevan lo que el compositor realmente toca a la tonalidad medida.

    Los compositores modales (dorico, pentatonica blues) no suenan en la tonica de su
    perfil: un dorico se oye como la mayor un tono abajo. Por eso se prueba cada
    transposicion sobre el croma de las notas y se queda la que cae en la tonalidad de la
    fuente (o vecina) con mayor afinidad tonal; si empatan, la mas cercana al calculo por
    la tonica.
    """
    naive = transpose_for(genre, target.key)
    if not any(target.chroma):
        return naive
    hist = note_chroma(genre, seed, bars)
    source_key = parse_key_name(target.key)

    def score(t: int):
        rolled = np.roll(hist, t)
        key = detect_key(rolled)
        in_key = circle_distance(key, source_key) <= MAX_KEY_STEPS or key.pitch_class == source_key.pitch_class
        return (in_key, round(tonal_affinity(rolled, target.chroma), 3), -abs(t - naive))

    return max(range(-6, 6), key=score)


def project_for_target(target: StyleTarget, seed: int, bars: int, rack: Optional[Dict[str, str]] = None) -> Tuple[SongProject, Dict[str, str]]:
    """Proyecto editable (Editar Tema) del genero, al tempo y la tonalidad medidos."""
    auto_rack = GENRE_RACKS[target.genre]
    chosen = resolve_rack(rack or {}, fallback=auto_rack)
    project = project_for_generated("", "", target.genre, seed, bars, chosen)
    project.target_bpm = target.bpm
    project.transpose = fitted_transpose(target.genre, seed, bars, target)
    typical = f"sonido tipico de {GENRES[target.genre].name}"
    return project, {r: (typical if chosen[r] == auto_rack[r] else "elegido a mano") for r in chosen}


def source_checks(
    target: StyleTarget,
    generated_wav: str,
    bpm: int,
) -> List[CheckResult]:
    """Parecido (tonalidad/tempo) con el grupo y huella < 15 % contra cada fuente."""
    gen_mono, gen_sr = _read_wav_mono(generated_wav)
    gen_chroma = compute_chroma(gen_mono, gen_sr, max_sec=120.0)
    checks = [check_similarity(
        "playlist" if len(target.sources) > 1 else "fuente",
        tonal_affinity(gen_chroma, target.chroma),
        detect_key(gen_chroma),
        parse_key_name(target.key),
        tempo_diff_pct(bpm, target.bpm),
    )]
    gen_hashes = landmark_hashes(gen_mono, gen_sr)
    for src in target.sources:
        ratio = hash_match_ratio(gen_hashes, src.fingerprint) if src.fingerprint else 0.0
        checks.append(check_fingerprint(f"#{src.index + 1}", ratio))
    return checks


def compose_from_target(
    target: StyleTarget,
    output_mid_path: str,
    output_wav_path: str,
    seed: Optional[int] = None,
    bars: int = 16,
    rack: Optional[Dict[str, str]] = None,
    sample_rate: int = 44100,
):
    """Compone, renderiza (-14 LUFS) y verifica. Devuelve (proyecto, bundle, metrics, reporte, razones del rack).

    Sin semilla fija, si un intento no pasa los checks se recompone con otra semilla
    (hasta COMPOSE_ATTEMPTS) y se devuelve el primero aprobado, o el ultimo intento.
    """
    seeds = [seed] if seed is not None else [random.randrange(1, 2**31) for _ in range(COMPOSE_ATTEMPTS)]
    for attempt in seeds:
        project, reasons = project_for_target(target, attempt, bars, rack)
        bundle, metrics, report = render_project(project, output_mid_path, output_wav_path, sample_rate=sample_rate)
        for c in report["checks"]:
            if c["check"] == "tonalidad_editada":
                c["detail"] = f"Compositor {GENRES[target.genre].name} llevado a la tonalidad medida ({target.key}); informativo"
        checks = report["checks"] + [asdict(c) for c in source_checks(target, output_wav_path, bundle.bpm)]
        report = {"aprobado": all(c["passed"] for c in checks), "checks": checks}
        if report["aprobado"]:
            break
    return project, bundle, metrics, report, reasons
