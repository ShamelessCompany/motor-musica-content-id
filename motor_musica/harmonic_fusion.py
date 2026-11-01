"""Fusion Armonica Multi-Link: de uno o varios links a un tema original y coherente.

Flujo:
1. Cada link se analiza (tempo, tonalidad, perfil 12-croma). El audio solo se mide;
   nunca se copia, recorta ni re-sintetiza (regla de oro de Content ID).
2. Se planifica la forma: una seccion por fuente en SU tonalidad, unidas por puentes
   que avanzan por el circulo de quintas con dominantes encadenadas (V7 -> I sube una
   cuarta: la "ley de cuartas").
3. Se compone un motivo propio (leitmotiv) que viaja por todas las secciones, para que
   la mezcla suene a una sola cancion y no a un collage.
4. Se renderiza a -14 LUFS y se corren los checks de publicacion (huella, sonoridad,
   similitud con cada fuente).

El estilo "pvz_gotico_swing" aplica los principios que Laura Shigihara describio
sobre la banda sonora de Plants vs. Zombies: tono macabro (menor, semitonos), lado
tierno (melodia pegadiza de pocas notas, estilo NES/SNES) y humor (swing de big band
con percusion "rara"). Ver docs/FUSION_ARMONICA.md.
"""

from dataclasses import asdict, dataclass, field
import hashlib
from pathlib import Path
import random
import statistics
from typing import Dict, List, Optional, Sequence, Tuple
import wave

import numpy as np

from .content_id_checks import (
    CheckResult,
    check_fingerprint,
    check_master,
    check_no_samples,
    check_similarity,
    detect_key,
    fingerprint_match_ratio,
    summarize,
    tempo_diff_pct,
    tonal_affinity,
)
from .instruments import TimbreProfile, gm_programs, resolve_rack, suggest_instruments
from .metadata_manager import TrackMetadata, generate_track_metadata
from .midi_generator import MidiTrackBundle, NoteEvent, build_bundle_from_events
from .synth_renderer import AudioMetrics, SynthConfig, render_midi_to_wav
from .theory import (
    CIRCLE_PROGRESSIONS,
    Key,
    MusicalProfile,
    ScaleType,
    diatonic_chord_pcs,
    dominant_seventh_pcs,
    fourths_path,
    key_center,
    key_scale_intervals,
    parse_key_name,
)
from .youtube_dna import (
    ExtractedYouTubeDNA,
    analyze_loaded_audio,
    compute_chroma,
    load_source_audio,
)

STYLES = {
    "pvz_gotico_swing": "Gotico + tierno + humor (swing big band, pizzicato, percusion rara)",
    "seguir_fuente": "Groove recto que sigue el tempo de la fuente (trap / boom bap / 4x4)",
}
MAX_SOURCES = 5
FUSION_GENRE = "harmonic_fusion"

# Celdas ritmicas de 8 corcheas (un compas), cortas y repetibles: la base de un
# motivo pegadizo al estilo de las melodias de 8/16 bits.
RHYTHM_CELLS: List[List[int]] = [
    [2, 1, 1, 2, 2],
    [1, 1, 2, 1, 1, 2],
    [3, 1, 2, 2],
    [2, 2, 1, 1, 2],
    [1, 1, 1, 1, 2, 2],
    [2, 1, 1, 1, 1, 2],
]


@dataclass
class MotifNote:
    step: int  # corchea 0-15 dentro de la frase de 2 compases
    length: int  # en corcheas
    offset: int  # grados de escala sobre la fundamental del acorde
    chromatic_approach: bool = False  # semitono por debajo de la nota siguiente


@dataclass
class FusionSection:
    kind: str  # intro | tema | puente | cierre
    key: str
    bars: int
    chords: List[List[int]]  # clases de altura por compas
    chord_degrees: List[int]  # grado diatonico por compas (-1 = dominante de paso)
    source_index: Optional[int] = None
    label: str = ""


@dataclass
class FusionPlan:
    home_key: str
    bpm: int
    style: str
    seed: int
    motif: List[MotifNote]
    sections: List[FusionSection]
    source_keys: List[str] = field(default_factory=list)
    source_bpms: List[int] = field(default_factory=list)
    circle_route: List[str] = field(default_factory=list)
    instruments: Dict[str, str] = field(default_factory=dict)  # rol -> id del rack
    instrument_reasons: Dict[str, str] = field(default_factory=dict)

    @property
    def total_bars(self) -> int:
        return sum(s.bars for s in self.sections)

    def to_dict(self) -> Dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict) -> "FusionPlan":
        data = dict(data)
        data["motif"] = [MotifNote(**m) for m in data["motif"]]
        data["sections"] = [FusionSection(**s) for s in data["sections"]]
        return FusionPlan(**data)


@dataclass
class SourceAudio:
    dna: ExtractedYouTubeDNA
    mono: np.ndarray
    sr: int


@dataclass
class FusionResult:
    plan: FusionPlan
    bundle: MidiTrackBundle
    metrics: AudioMetrics
    metadata: TrackMetadata
    report: Dict[str, object]
    section_spans: List[Tuple[float, float, Optional[int]]]


# ---------------------------------------------------------------------------
# 1. Analisis
# ---------------------------------------------------------------------------

def analyze_sources(sources: Sequence[str], labels: Optional[Sequence[Optional[str]]] = None) -> List[SourceAudio]:
    """Analiza cada link o archivo de audio. Conserva solo un mono en memoria para la huella."""
    if not sources:
        raise ValueError("Se requiere al menos un link o archivo")
    if len(sources) > MAX_SOURCES:
        raise ValueError(f"Maximo {MAX_SOURCES} fuentes por fusion")
    labels = list(labels) if labels else [None] * len(sources)
    analyzed: List[SourceAudio] = []
    for src, name in zip(sources, labels):
        samples, sr, label = load_source_audio(src, label=name)
        dna = analyze_loaded_audio(samples, sr, label)
        mono = np.mean(samples, axis=1) if samples.ndim > 1 else samples
        analyzed.append(SourceAudio(dna=dna, mono=mono.astype(np.float32), sr=sr))
    return analyzed


# ---------------------------------------------------------------------------
# 2. Planificacion armonica (circulo de quintas)
# ---------------------------------------------------------------------------

def _seed_for(dnas: Sequence[ExtractedYouTubeDNA], variation: int) -> int:
    raw = "|".join(f"{d.source_url}:{d.detected_key}:{d.detected_bpm}" for d in dnas)
    return int(hashlib.sha1(f"{raw}#{variation}".encode()).hexdigest()[:8], 16)


def blend_tempo(bpms: Sequence[int]) -> int:
    """Tempo comun: cada fuente se pliega (medio/doble tiempo) cerca de la primera y se toma la mediana."""
    ref = float(bpms[0])
    folded = []
    for b in bpms:
        b = float(b)
        while b < ref / 1.414:
            b *= 2.0
        while b >= ref * 1.414:
            b /= 2.0
        folded.append(b)
    return int(round(statistics.median(folded)))


def generate_motif(rng: random.Random, style: str) -> List[MotifNote]:
    """Motivo de 2 compases: pregunta (compas 1) y respuesta (compas 2, mismo ritmo, cierre estable)."""
    cell = rng.choice(RHYTHM_CELLS)
    answer = cell[:-2] + [cell[-2] + cell[-1]]  # misma celda, ultima nota alargada
    notes: List[MotifNote] = []
    offset = rng.choice([0, 2, 4])
    for bar, rhythm in enumerate((cell, answer)):
        step = bar * 8
        for i, length in enumerate(rhythm):
            if notes:
                if rng.random() < 0.7:
                    offset += rng.choice([-1, 1])
                else:
                    offset += rng.choice([-3, -2, 2, 3])
            on_beat = step % 2 == 0
            if on_beat:
                # En tiempo fuerte: nota del acorde (fundamental, 3a, 5a, octava)
                offset = min((0, 2, 4, 7), key=lambda c: abs(c - offset))
            offset = max(-3, min(offset, 7))
            is_last = bar == 1 and i == len(rhythm) - 1
            if is_last:
                offset = rng.choice([0, 2])
            notes.append(MotifNote(step=step, length=length, offset=offset))
            step += length
    # Bordaduras cromaticas (semitonos goticos): nota debil que cae en tiempo fuerte siguiente
    approach_prob = 0.45 if style == "pvz_gotico_swing" else 0.2
    for i in range(len(notes) - 1):
        nxt = notes[i + 1]
        if notes[i].step % 2 == 1 and nxt.step % 2 == 0 and rng.random() < approach_prob:
            notes[i].chromatic_approach = True
    return notes


def _section_progression(key: Key, bars: int, rng: random.Random) -> List[int]:
    pattern = rng.choice(CIRCLE_PROGRESSIONS[key.mode])
    if bars <= 4:
        pattern = pattern[4:] if pattern[4:][-1] == 0 else pattern[:4]
    return [pattern[i % len(pattern)] for i in range(bars)]


def _diatonic_section(
    kind: str, key: Key, degrees: List[int], source_index: Optional[int], label: str, leading_tone: bool = True
) -> FusionSection:
    # Con sensible (gotico / clasico) el V es dominante 7; sin ella (trap, synthwave,
    # lofi) el v menor modal conserva el color de la fuente.
    chords = [
        dominant_seventh_pcs(key) if d == 4 and (leading_tone or key.mode == "major")
        else diatonic_chord_pcs(key, d, seventh=False)
        for d in degrees
    ]
    return FusionSection(kind, key.name, len(degrees), chords, list(degrees), source_index, label)


def _bridge(from_key: Key, to_key: Key) -> Optional[FusionSection]:
    """Puente de dominantes encadenadas por el circulo de quintas hasta to_key."""
    path = fourths_path(from_key, to_key)
    if not path:
        return None
    chords = [dominant_seventh_pcs(k) for k in path]
    route = " > ".join(k.name.split()[0] for k in [from_key] + path)
    return FusionSection("puente", to_key.name, len(chords), chords, [-1] * len(chords), None, f"Puente {route}")


def plan_fusion(
    dnas: Sequence[ExtractedYouTubeDNA],
    bars_per_section: int = 8,
    style: str = "pvz_gotico_swing",
    variation: int = 0,
    instruments: Optional[Dict[str, str]] = None,
) -> FusionPlan:
    """instruments: rack {rol: id}; roles ausentes o 'auto' se eligen por el timbre de las fuentes."""
    if not dnas:
        raise ValueError("Se requiere al menos una fuente analizada")
    if style not in STYLES:
        style = "pvz_gotico_swing"
    bars_per_section = max(4, min(int(bars_per_section), 16))
    seed = _seed_for(dnas, variation)
    rng = random.Random(seed)

    keys = [parse_key_name(d.detected_key) for d in dnas]
    home = key_center(keys)
    bpm = blend_tempo([d.detected_bpm for d in dnas])

    # Con una sola fuente: forma A - A' en la misma tonalidad
    order = list(range(len(keys))) if len(keys) > 1 else [0, 0]

    sections: List[FusionSection] = []
    # Intro: tonica y dominante de la tonalidad hogar (sin melodia)
    sections.append(FusionSection(
        "intro", home.name, 2,
        [diatonic_chord_pcs(home, 0), dominant_seventh_pcs(home)], [0, 4], None, "Intro",
    ))
    current = home
    for pos, idx in enumerate(order):
        key = keys[idx]
        bridge = _bridge(current, key)
        if bridge:
            sections.append(bridge)
        elif current == key and sections[-1].chord_degrees[-1] != 4:
            # Misma tonalidad: un compas de V7 para re-preparar la entrada del tema
            sections.append(FusionSection("puente", key.name, 1, [dominant_seventh_pcs(key)], [-1], None, "Dominante"))
        degrees = _section_progression(key, bars_per_section, rng)
        label = f"Tema {chr(65 + pos)} ({key.name}, fuente {idx + 1})"
        sections.append(_diatonic_section("tema", key, degrees, idx, label, leading_tone=style == "pvz_gotico_swing"))
        current = key

    back = _bridge(current, home)
    if back:
        sections.append(back)
    # Cierre: iv - V7 - i (plagal + autentica)
    sections.append(_diatonic_section("cierre", home, [3, 4, 0], None, "Cierre"))

    timbres = [
        TimbreProfile(d.brightness_hz, d.bass_ratio, d.percussiveness)
        for d in dnas if d.brightness_hz is not None
    ]
    suggested, reasons = suggest_instruments(timbres, bpm, home.mode == "minor", style)
    rack = resolve_rack(instruments, fallback=suggested)
    reasons = {
        role: (reasons[role] if rack[role] == suggested[role] else "elegido a mano en el rack")
        for role in rack
    }

    route: List[str] = []
    for s in sections:
        tonic = s.key.split()[0]
        if not route or route[-1] != tonic:
            route.append(tonic)

    return FusionPlan(
        home_key=home.name,
        bpm=bpm,
        style=style,
        seed=seed,
        motif=generate_motif(rng, style),
        sections=sections,
        source_keys=[k.name for k in keys],
        source_bpms=[d.detected_bpm for d in dnas],
        circle_route=route,
        instruments=rack,
        instrument_reasons=reasons,
    )


# ---------------------------------------------------------------------------
# 3. Composicion (eventos MIDI)
# ---------------------------------------------------------------------------

def _voice_chord(pcs: List[int], low: int = 52) -> List[int]:
    root = low + ((pcs[0] - low) % 12)
    voiced = [root]
    for pc in pcs[1:]:
        p = voiced[-1] + ((pc - voiced[-1]) % 12 or 12)
        voiced.append(p)
    return voiced


def _bass_pitch(pc: int, low: int = 33) -> int:
    """Fundamental del bajo: A1..G#2 para 808 / sub, A2..G#3 para walking bass de contrabajo/tuba."""
    return low + ((pc - low) % 12)


def _melody_scale(key: Key, harmonic: bool) -> List[int]:
    intervals = key_scale_intervals(key, harmonic=harmonic)
    base = 48 + key.pitch_class
    if base < 52:
        base += 12
    return [base + o * 12 + iv for o in range(4) for iv in intervals]


class _Grid:
    """Convierte corcheas a segundos aplicando swing (2:1) o rejilla recta."""

    def __init__(self, bpm: int, swing: bool):
        self.spb = 60.0 / bpm
        self.ratio = 2.0 / 3.0 if swing else 0.5

    def eighth(self, bar_start: float, idx: float) -> float:
        whole = int(idx)
        beat, off = divmod(whole, 2)
        frac = idx - whole
        base = bar_start + beat * self.spb + (self.ratio * self.spb if off else 0.0)
        if frac:
            nxt = bar_start + ((whole + 1) // 2) * self.spb + (self.ratio * self.spb if (whole + 1) % 2 else 0.0)
            base += (nxt - base) * frac
        return base

    def sixteenth(self, bar_start: float, idx: int) -> float:
        return bar_start + idx * self.spb * 0.25


def _motif_variant(motif: List[MotifNote], variant: str) -> List[MotifNote]:
    if variant == "B":  # inversion del contorno en la pregunta, respuesta original
        return [MotifNote(m.step, m.length, -m.offset if m.step < 8 else m.offset, m.chromatic_approach) for m in motif]
    if variant == "C":  # cadencia: respuesta termina en la fundamental
        out = [MotifNote(**asdict(m)) for m in motif]
        out[-1].offset = 0
        return out
    return motif


def _add(events: List[NoteEvent], pitch: int, vel: int, start: float, dur: float, track: str, ch: int) -> None:
    events.append(NoteEvent(pitch=int(pitch), velocity=int(max(1, min(vel, 127))), start_sec=max(0.0, start),
                            duration_sec=max(0.02, dur), track_name=track, channel=ch))


def compose_fusion_events(plan: FusionPlan) -> Tuple[List[NoteEvent], float, List[Tuple[float, float, Optional[int]]]]:
    """Genera todos los NoteEvent del plan. Determinista para un mismo plan."""
    rng = random.Random(plan.seed ^ 0x5A17)
    pvz = plan.style == "pvz_gotico_swing"
    grid = _Grid(plan.bpm, swing=pvz)
    spb = grid.spb
    spbar = spb * 4.0
    events: List[NoteEvent] = []
    spans: List[Tuple[float, float, Optional[int]]] = []

    flat_bars: List[Tuple[FusionSection, int]] = [(s, i) for s in plan.sections for i in range(s.bars)]
    bar_t = 0.0
    for gbar, (sec, i_in_sec) in enumerate(flat_bars):
        if i_in_sec == 0:
            spans.append((bar_t, bar_t + sec.bars * spbar, sec.source_index))
        key = parse_key_name(sec.key)
        chord = sec.chords[i_in_sec]
        degree = sec.chord_degrees[i_in_sec]
        next_chord = flat_bars[gbar + 1][0].chords[flat_bars[gbar + 1][1]] if gbar + 1 < len(flat_bars) else None
        intensity = 0.85 if sec.kind in ("intro", "cierre") else 1.0

        # --- Armonia (Canal 0) ---
        voiced = _voice_chord(chord)
        if pvz:
            # Organo/cuerdas suaves de fondo + pizzicato en 2 y 4 (guino a Danny Elfman)
            for p in voiced:
                _add(events, p, 46, bar_t, spbar * 0.96, "chords", 0)
            for beat in (1, 3):
                for p in voiced:
                    _add(events, p + 12, int(78 * intensity), bar_t + beat * spb, spb * 0.3, "chords", 0)
        else:
            vel = int(rng.randint(76, 86) * intensity)
            for p in voiced:
                _add(events, p, vel, bar_t, spbar * 0.96, "chords", 0)

        # --- Bajo (Canal 2) ---
        bass_low = 45 if pvz else 33
        root = _bass_pitch(chord[0], bass_low)
        if pvz:
            # Walking bass: fundamental, notas del acorde y aproximacion cromatica al siguiente acorde
            third = root + ((chord[1] - chord[0]) % 12)
            fifth = root + ((chord[2] - chord[0]) % 12)
            line = [root, rng.choice([third, fifth]), fifth if rng.random() < 0.6 else root + 12]
            if next_chord is not None:
                target = _bass_pitch(next_chord[0], bass_low)
                line.append(target + rng.choice([-1, 1]))
            else:
                line.append(fifth)
            for beat, p in enumerate(line):
                _add(events, p, int(rng.randint(92, 104) * intensity), bar_t + beat * spb, spb * 0.85, "bass", 2)
        else:
            if plan.bpm >= 130:
                for s16, beats in ((0, 1.5), (6, 1.0), (10, 1.2)):
                    _add(events, root, rng.randint(112, 124), grid.sixteenth(bar_t, s16), beats * spb, "bass", 2)
            else:
                for step in range(8):
                    p = root + (12 if step % 2 == 1 and plan.bpm > 100 else 0)
                    _add(events, p, rng.randint(92, 106), grid.eighth(bar_t, step), spb * 0.45, "bass", 2)

        # --- Melodia (Canal 1): el leitmotiv recorre todas las secciones ---
        if sec.kind != "intro":
            if sec.kind == "puente":
                # Secuencia: primera mitad del motivo sobre cada dominante del puente
                target_root_pc = (chord[0] + 5) % 12
                tgt = Key(target_root_pc, key.mode)
                scale = _melody_scale(tgt, harmonic=(tgt.mode == "minor"))
                notes = [m for m in plan.motif if m.step < 8]
                deg = 4
                phrase_bar = 0
            else:
                phrase_idx = i_in_sec // 2
                # Forma de frase A A B A; las 2 ultimas barras cierran en la fundamental
                variant = "C" if (sec.kind == "cierre" or i_in_sec >= sec.bars - 2) else "AABA"[phrase_idx % 4]
                motif = _motif_variant(plan.motif, variant)
                phrase_bar = i_in_sec % 2
                notes = [m for m in motif if (m.step // 8) == phrase_bar]
                deg = degree if degree >= 0 else 4
                harmonic = key.mode == "minor" and deg == 4 and (pvz or sec.kind == "cierre")
                scale = _melody_scale(key, harmonic=harmonic)
            pitches: List[int] = []
            for m in notes:
                idx = max(0, min(7 + deg + m.offset, len(scale) - 1))
                pitches.append(scale[idx])
            for n_i, m in enumerate(notes):
                p = pitches[n_i]
                if m.chromatic_approach and n_i + 1 < len(pitches):
                    p = pitches[n_i + 1] - 1
                start_e = m.step - phrase_bar * 8
                t0 = grid.eighth(bar_t, start_e)
                end_e = start_e + m.length
                t1 = bar_t + spbar if end_e >= 8 else grid.eighth(bar_t, end_e)
                vel = (104 if start_e % 2 == 0 else 92) * intensity
                _add(events, p, vel + rng.randint(-4, 4), t0, (t1 - t0) * 0.88, "melody", 1)

        # --- Bateria (Canal 9) ---
        is_section_start = i_in_sec == 0
        if is_section_start and sec.kind in ("tema", "cierre"):
            _add(events, 49, 112, bar_t, 0.8, "drums", 9)
        if pvz:
            # Swing de big band: ride "ding, ding-da-ding", charles en 2 y 4
            for e8 in (0, 2, 3, 4, 6, 7):
                _add(events, 51, (88 if e8 % 2 == 0 else 72) + rng.randint(-5, 5), grid.eighth(bar_t, e8), 0.3, "drums", 9)
            for beat in (1, 3):
                _add(events, 42, 70, bar_t + beat * spb, 0.05, "drums", 9)
                _add(events, 38, int(84 * intensity) + rng.randint(-6, 6), bar_t + beat * spb, 0.18, "drums", 9)
            for beat in (0, 2):
                _add(events, 36, int(100 * intensity), bar_t + beat * spb, 0.15, "drums", 9)
            # Humor: percusion "rara" (wood block / cencerro / claves) en el ultimo contratiempo
            if gbar % 2 == 1:
                _add(events, rng.choice([76, 77, 56, 75]), rng.randint(90, 110), grid.eighth(bar_t, 7), 0.08, "drums", 9)
            # Redoble de banda de marcha antes de cada cambio de seccion
            if i_in_sec == sec.bars - 1 and gbar + 1 < len(flat_bars):
                for e8 in (6, 6.5, 7, 7.5):
                    _add(events, 38, 70 + int(e8 * 5), grid.eighth(bar_t, e8), 0.1, "drums", 9)
        else:
            for s16 in range(16):
                t = grid.sixteenth(bar_t, s16)
                if plan.bpm >= 130:
                    _add(events, 42, 88 if s16 % 4 == 0 else 68, t, 0.04, "drums", 9)
                    kick, snare = s16 in (0, 6, 11), s16 == 8
                elif plan.bpm <= 95:
                    if s16 % 2 == 0:
                        _add(events, 42, 80, t + (0.02 if s16 % 4 == 2 else 0.0), 0.06, "drums", 9)
                    kick, snare = s16 in (0, 5, 10), s16 in (4, 12)
                else:
                    if s16 % 4 == 2:
                        _add(events, 46, 78, t, 0.1, "drums", 9)
                    kick, snare = s16 % 4 == 0, s16 in (4, 12)
                if kick:
                    _add(events, 36, 112, t, 0.15, "drums", 9)
                if snare:
                    _add(events, 38, 106, t, 0.18, "drums", 9)

        bar_t += spbar

    return events, bar_t, spans


def plan_profile(plan: FusionPlan) -> MusicalProfile:
    home = parse_key_name(plan.home_key)
    return MusicalProfile(
        name=f"Fusion Armonica {plan.home_key}",
        scale_type=ScaleType.HARMONIC_MINOR if home.mode == "minor" else ScaleType.DORIAN,
        root_note=48 + home.pitch_class,
        bpm=plan.bpm,
        progressions=[s.chord_degrees for s in plan.sections if s.kind == "tema"],
        drum_style="swing" if plan.style == "pvz_gotico_swing" else "straight",
        melody_style="leitmotiv",
    )


def build_fusion_bundle(plan: FusionPlan, output_mid_path: Optional[str] = None) -> Tuple[MidiTrackBundle, List[Tuple[float, float, Optional[int]]]]:
    events, duration, spans = compose_fusion_events(plan)
    programs = gm_programs(resolve_rack(plan.instruments)) if plan.instruments else None
    bundle = build_bundle_from_events(
        events, plan_profile(plan), plan.bpm, plan.total_bars, duration,
        output_mid_path=output_mid_path, programs=programs,
    )
    return bundle, spans


# ---------------------------------------------------------------------------
# 4. Render + checks
# ---------------------------------------------------------------------------

def _read_wav_mono(path: str) -> Tuple[np.ndarray, int]:
    with wave.open(path, "rb") as wf:
        sr = wf.getframerate()
        n_ch = wf.getnchannels()
        data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    if n_ch == 2:
        data = data.reshape(-1, 2).mean(axis=1)
    return data, sr


def run_fusion_checks(
    plan: FusionPlan,
    metrics: AudioMetrics,
    generated_wav: str,
    spans: List[Tuple[float, float, Optional[int]]],
    sources: Sequence[SourceAudio],
) -> Dict[str, object]:
    gen_mono, gen_sr = _read_wav_mono(generated_wav)
    checks: List[CheckResult] = check_master(metrics) + [check_no_samples(True)]
    multi = len(sources) > 1
    for i, src in enumerate(sources):
        label = f"fuente {i + 1}"
        segs = [gen_mono[int(a * gen_sr):int(b * gen_sr)] for a, b, idx in spans if idx == i]
        segment = np.concatenate(segs) if segs else gen_mono
        gen_chroma = compute_chroma(segment, gen_sr, max_sec=120.0)
        src_chroma = src.dna.chroma or list(compute_chroma(src.mono, src.sr))
        checks.append(check_similarity(
            label,
            tonal_affinity(gen_chroma, src_chroma),
            detect_key(gen_chroma),
            parse_key_name(src.dna.detected_key),
            tempo_diff_pct(plan.bpm, src.dna.detected_bpm),
            enforce_tempo=not multi,
        ))
        checks.append(check_fingerprint(label, fingerprint_match_ratio(gen_mono, gen_sr, src.mono, src.sr)))
    return summarize(checks)


def create_harmonic_fusion(
    sources: Sequence[SourceAudio],
    output_mid_path: str,
    output_wav_path: str,
    bars_per_section: int = 8,
    style: str = "pvz_gotico_swing",
    variation: int = 0,
    custom_title: Optional[str] = None,
    track_number: int = 1,
    sample_rate: int = 44100,
    instruments: Optional[Dict[str, str]] = None,
) -> FusionResult:
    """Pipeline completo: plan -> MIDI -> WAV -14 LUFS -> checks -> metadatos ISRC."""
    plan = plan_fusion([s.dna for s in sources], bars_per_section, style, variation, instruments)
    bundle, spans = build_fusion_bundle(plan, output_mid_path)
    cfg = SynthConfig(sample_rate=sample_rate, target_lufs=-14.0, bit_depth=16)
    metrics = render_midi_to_wav(bundle, output_wav_path, config=cfg, instruments=plan.instruments)
    report = run_fusion_checks(plan, metrics, output_wav_path, spans, sources)

    n = len(sources)
    title = custom_title or (
        f"Fusion {plan.home_key} x{n}" if n > 1 else f"Inspirado en {plan.home_key} [{plan.bpm} BPM]"
    )
    meta = generate_track_metadata(
        genre=FUSION_GENRE,
        bpm=plan.bpm,
        scale=plan.home_key,
        duration_sec=metrics.duration_sec,
        track_number=track_number,
        midi_filename=Path(output_mid_path).name,
        audio_filename=Path(output_wav_path).name,
        peak_dbfs=metrics.peak_dbfs,
        estimated_lufs=metrics.estimated_lufs,
        custom_title=title,
    )
    return FusionResult(plan, bundle, metrics, meta, report, spans)
