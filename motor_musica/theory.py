"""Teoria Musical Algoritmica para Generacion Procedural (Content ID Compliant).

Garantiza composicion matematica pura sin melodias pregrabadas ni loops externos.
"""

from dataclasses import dataclass
from enum import Enum
import random
from typing import Dict, List, Tuple


class ScaleType(str, Enum):
    NATURAL_MINOR = "natural_minor"
    HARMONIC_MINOR = "harmonic_minor"
    DORIAN = "dorian"
    PHRYGIAN = "phrygian"
    LOFI_MINOR = "lofi_minor"
    ROCK_PENTATONIC = "rock_pentatonic"


SCALE_INTERVALS: Dict[ScaleType, List[int]] = {
    ScaleType.NATURAL_MINOR: [0, 2, 3, 5, 7, 8, 10],
    ScaleType.HARMONIC_MINOR: [0, 2, 3, 5, 7, 8, 11],
    ScaleType.DORIAN: [0, 2, 3, 5, 7, 9, 10],
    ScaleType.PHRYGIAN: [0, 1, 3, 5, 7, 8, 10],
    ScaleType.LOFI_MINOR: [0, 2, 3, 5, 7, 8, 10],
    ScaleType.ROCK_PENTATONIC: [0, 3, 5, 6, 7, 10],  # Blues / Hard Rock con nota blue (b5)
}


@dataclass
class MusicalProfile:
    name: str
    scale_type: ScaleType
    root_note: int  # MIDI number (e.g., 57 = A3, 50 = D3)
    bpm: int
    progressions: List[List[int]]  # Scale degree indices (0 = i, 5 = VI, etc.)
    drum_style: str  # "epic", "synthwave", "lofi"
    melody_style: str  # "arp", "lead", "jazz"


GENRES: Dict[str, MusicalProfile] = {
    "epic_cinematic": MusicalProfile(
        name="Epic Cinematic",
        scale_type=ScaleType.HARMONIC_MINOR,
        root_note=57,  # A3
        bpm=120,
        progressions=[
            [0, 5, 2, 6],  # i - VI - III - VII
            [0, 3, 5, 4],  # i - iv - VI - v
            [0, 5, 6, 4],  # i - VI - VII - v
        ],
        drum_style="epic",
        melody_style="arp",
    ),
    "synthwave": MusicalProfile(
        name="Synthwave 80s",
        scale_type=ScaleType.DORIAN,
        root_note=50,  # D3
        bpm=124,
        progressions=[
            [0, 5, 3, 6],  # i - VI - iv - VII
            [0, 6, 5, 4],  # i - VII - VI - v
        ],
        drum_style="synthwave",
        melody_style="lead",
    ),
    "lofi_chill": MusicalProfile(
        name="Lofi Chillhop",
        scale_type=ScaleType.NATURAL_MINOR,
        root_note=48,  # C3
        bpm=82,
        progressions=[
            [0, 3, 6, 4],  # i7 - iv7 - VII7 - v7
            [0, 5, 2, 4],  # i9 - VImaj7 - IIImaj7 - v7
        ],
        drum_style="lofi",
        melody_style="jazz",
    ),
    "hard_rock": MusicalProfile(
        name="Hard Rock & Heavy Riffs",
        scale_type=ScaleType.ROCK_PENTATONIC,
        root_note=40,  # E2 / Guitar low E
        bpm=136,
        progressions=[
            [0, 5, 4, 5],  # i - bVII - bVI - bVII (E - D - C - D)
            [0, 1, 2, 0],  # i - bIII - IV - i (E - G - A - E blues riff)
            [0, 4, 1, 5],  # i - bVI - bIII - bVII (E - C - G - D)
        ],
        drum_style="rock",
        melody_style="rock_solo",
    ),
    "dark_trap": MusicalProfile(
        name="Dark Trap & 808 Beat",
        scale_type=ScaleType.PHRYGIAN,
        root_note=50,  # D3 (Rango optimo para 808 sub)
        bpm=140,
        progressions=[
            [0, 1, 0, 5],  # i - bII - i - bVI (Metro Boomin / Southside dark tension)
            [0, 5, 4, 1],  # i - bVI - v - bII
            [0, 1, 0, 1],  # i - bII - i - bII (Puro suspenso)
        ],
        drum_style="trap",
        melody_style="trap_bells",
    ),
    "boom_bap": MusicalProfile(
        name="90s Boom Bap Golden Era",
        scale_type=ScaleType.DORIAN,
        root_note=53,  # F3
        bpm=92,
        progressions=[
            [0, 3, 6, 4],  # i7 - iv7 - VII7 - v7 (Groove clasico de NYC)
            [0, 5, 2, 4],  # i9 - VImaj7 - IIImaj7 - v7
        ],
        drum_style="boombap",
        melody_style="jazz",
    ),
}


def build_scale_notes(root: int, scale_type: ScaleType, octaves: int = 3) -> List[int]:
    """Genera lista ordenada de notas MIDI para la escala en multiples octavas."""
    intervals = SCALE_INTERVALS[scale_type]
    notes: List[int] = []
    for oct_offset in range(octaves):
        base = root + (oct_offset * 12)
        for interval in intervals:
            note = base + interval
            if 0 <= note <= 127:
                notes.append(note)
    return sorted(list(set(notes)))


def get_chord_notes(root_note: int, scale_type: ScaleType, degree_index: int, extended: bool = False) -> List[int]:
    """Calcula las notas de un acorde diatónico (tríada o séptima/novena o power chord rock)."""
    scale = build_scale_notes(root_note, scale_type, octaves=4)
    base_idx = degree_index % len(SCALE_INTERVALS[scale_type])
    root_pitch = scale[base_idx]
    
    if scale_type == ScaleType.ROCK_PENTATONIC:
        # Power Chord (Raiz + Quinta + Octava)
        return [root_pitch, root_pitch + 7, root_pitch + 12]
    
    third_pitch = scale[base_idx + 2]
    fifth_pitch = scale[base_idx + 4]
    
    notes = [root_pitch, third_pitch, fifth_pitch]
    if extended and (base_idx + 6) < len(scale):
        seventh_pitch = scale[base_idx + 6]
        notes.append(seventh_pitch)
    return notes


def get_bass_note(root_note: int, scale_type: ScaleType, degree_index: int) -> int:
    """Devuelve la fundamental del bajo transportada a rango grave (C1 - B2, MIDI 24 - 47)."""
    scale = build_scale_notes(root_note, scale_type, octaves=2)
    deg_note = scale[degree_index % len(SCALE_INTERVALS[scale_type])]
    # Transportar hacia abajo hasta el rango 28-50
    while deg_note > 48:
        deg_note -= 12
    while deg_note < 28:
        deg_note += 12
    return deg_note


# ---------------------------------------------------------------------------
# Circulo de Quintas / Ley de Cuartas
# ---------------------------------------------------------------------------
# Subir una cuarta justa (5 semitonos) equivale a bajar una quinta: es el
# movimiento de fundamental mas fuerte de la armonia tonal (V -> I, ii -> V,
# vi -> ii ...). El motor de fusion lo usa para encadenar acordes dentro de
# una seccion y para modular entre las tonalidades de varios links.

MAJOR_INTERVALS: List[int] = [0, 2, 4, 5, 7, 9, 11]
MINOR_INTERVALS: List[int] = SCALE_INTERVALS[ScaleType.NATURAL_MINOR]
HARMONIC_MINOR_INTERVALS: List[int] = SCALE_INTERVALS[ScaleType.HARMONIC_MINOR]


@dataclass(frozen=True)
class Key:
    pitch_class: int  # 0 = C ... 11 = B
    mode: str  # "major" | "minor"

    @property
    def name(self) -> str:
        return f"{PITCH_CLASS_NAMES[self.pitch_class]} {self.mode}"

    @property
    def relative_major_pc(self) -> int:
        """Tonica de la relativa mayor (A minor -> C major) para ubicar en el circulo."""
        return self.pitch_class if self.mode == "major" else (self.pitch_class + 3) % 12


PITCH_CLASS_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Progresiones diatonicas por cuartas (grado de la escala, 0 = tonica).
# Cada flecha sube una cuarta diatonica: i -> iv -> VII -> III -> VI -> ii -> V -> i
CIRCLE_PROGRESSIONS: Dict[str, List[List[int]]] = {
    "minor": [
        [0, 3, 6, 2, 5, 1, 4, 0],  # Ciclo diatonico completo (estilo barroco / gotico)
        [0, 3, 4, 0, 5, 1, 4, 0],  # i - iv - V - i | VI - ii - V - i
        [0, 3, 6, 2, 0, 3, 4, 0],  # i - iv - VII - III | i - iv - V - i
    ],
    "major": [
        [0, 3, 6, 2, 5, 1, 4, 0],  # I - IV - vii - iii - vi - ii - V - I
        [0, 5, 1, 4, 0, 5, 1, 4],  # I - vi - ii - V (turnaround)
        [2, 5, 1, 4, 0, 3, 4, 0],  # iii - vi - ii - V | I - IV - V - I
    ],
}


def parse_key_name(key_name: str) -> Key:
    """Convierte 'A minor' / 'C# major' en un Key."""
    parts = key_name.strip().split()
    pc = PITCH_CLASS_NAMES.index(parts[0])
    mode = parts[1].lower() if len(parts) > 1 else "minor"
    return Key(pc, "major" if mode.startswith("maj") else "minor")


def circle_position(key: Key) -> int:
    """Posicion 0-11 en el circulo de quintas (C=0, G=1, D=2 ... F=11)."""
    return (key.relative_major_pc * 7) % 12


def circle_distance(a: Key, b: Key) -> int:
    """Pasos en el circulo de quintas entre dos tonalidades (0 = misma armadura, 6 = tritono)."""
    diff = abs(circle_position(a) - circle_position(b))
    return min(diff, 12 - diff)


def key_center(keys: List[Key]) -> Key:
    """Tonalidad 'hogar' que minimiza la distancia total en el circulo a todas las fuentes.

    El modo se decide por mayoria (empate -> menor). Ante empate de costo gana
    la tonalidad de la primera fuente.
    """
    if not keys:
        return Key(9, "minor")
    minor_votes = sum(1 for k in keys if k.mode == "minor")
    mode = "minor" if minor_votes * 2 >= len(keys) else "major"
    best, best_cost = None, None
    candidates = [keys[0]] + [Key(pc, mode) for pc in range(12)]
    for cand in candidates:
        cost = sum(circle_distance(cand, k) + (0.5 if k.mode != cand.mode else 0.0) for k in keys)
        if best_cost is None or cost < best_cost:
            best, best_cost = cand, cost
    return best


def fourths_path(start: Key, end: Key) -> List[Key]:
    """Camino de tonalidades intermedias entre start y end avanzando por el circulo.

    Se elige el sentido mas corto: hacia las cuartas (bemoles) o hacia las
    quintas (sostenidos). No incluye start, si incluye end.
    """
    if start == end:
        return []
    pos_s, pos_e = circle_position(start), circle_position(end)
    forward = (pos_e - pos_s) % 12  # pasos hacia las quintas
    step = 7 if forward <= 6 else 5  # quinta arriba o cuarta arriba
    n_steps = forward if forward <= 6 else 12 - forward
    path: List[Key] = []
    pc = start.pitch_class
    for _ in range(max(0, n_steps - 1)):
        pc = (pc + step) % 12
        path.append(Key(pc, start.mode))
    path.append(end)
    return path


def key_scale_intervals(key: Key, harmonic: bool = False) -> List[int]:
    if key.mode == "major":
        return MAJOR_INTERVALS
    return HARMONIC_MINOR_INTERVALS if harmonic else MINOR_INTERVALS


def diatonic_chord_pcs(key: Key, degree: int, seventh: bool = False) -> List[int]:
    """Clases de altura de un acorde diatonico por terceras.

    En menor, el V usa la menor armonica (sensible elevada) para que la
    cadencia V -> i resuelva con fuerza.
    """
    degree %= 7
    intervals = key_scale_intervals(key, harmonic=(key.mode == "minor" and degree == 4))
    size = 4 if seventh else 3
    return [(key.pitch_class + intervals[(degree + 2 * i) % 7]) % 12 for i in range(size)]


def dominant_seventh_pcs(target: Key) -> List[int]:
    """Acorde V7 de la tonalidad destino (raiz una quinta arriba = cuarta abajo de la tonica)."""
    root = (target.pitch_class + 7) % 12
    return [root, (root + 4) % 12, (root + 7) % 12, (root + 10) % 12]


def fold_bpm(bpm: float, low: float = 75.0) -> float:
    """Lleva un tempo a la banda [low, 2*low) para comparar medio tiempo / doble tiempo."""
    while bpm < low:
        bpm *= 2.0
    while bpm >= low * 2.0:
        bpm /= 2.0
    return bpm
