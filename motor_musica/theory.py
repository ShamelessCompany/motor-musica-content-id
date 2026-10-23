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
