"""Extractor de ADN Musical y Generador por Cadenas de Markov (Content ID Safe).

Permite alimentar un archivo MIDI de referencia, extraer su estructura estadistica
(probabilidades de transicion de notas, densidades ritmicas y progresiones)
y generar infinitas variaciones unicas que no infringen copyright ni Content ID.
"""

from collections import defaultdict
from dataclasses import dataclass, field
import random
from typing import Dict, List, Tuple
import mido
from mido import MidiFile


@dataclass
class SongDNA:
    pitch_transitions: Dict[int, List[int]] = field(default_factory=lambda: defaultdict(list))
    rhythm_intervals: List[float] = field(default_factory=list)
    average_velocity: int = 85
    root_pitch: int = 60
    estimated_tempo: int = 120


def extract_dna_from_midi(midi_path: str) -> SongDNA:
    """Extrae el perfil probabilistico de transicion de notas y ritmos de un MIDI."""
    mid = MidiFile(midi_path)
    dna = SongDNA()
    
    ticks_per_beat = mid.ticks_per_beat
    last_note = None
    all_velocities = []
    
    # Recorrer mensajes de las pistas melódicas
    for track in mid.tracks:
        track_time_sec = 0.0
        for msg in track:
            if msg.type == "set_tempo":
                dna.estimated_tempo = int(round(mido.tempo2bpm(msg.tempo)))
                
            if msg.type == "note_on" and msg.velocity > 0:
                pitch = msg.note
                all_velocities.append(msg.velocity)
                
                if last_note is not None:
                    # Registrar transicion estocastica: Nota A -> Nota B
                    dna.pitch_transitions[last_note].append(pitch)
                last_note = pitch
                
                # Intervalo ritmico normalizado en beats
                dur_beats = msg.time / float(ticks_per_beat) if ticks_per_beat > 0 else 0.25
                if dur_beats > 0.05:
                    dna.rhythm_intervals.append(round(dur_beats, 3))
                    
    if all_velocities:
        dna.average_velocity = int(sum(all_velocities) / len(all_velocities))
    if last_note is not None and not dna.pitch_transitions:
        dna.pitch_transitions[last_note] = [last_note]
    if not dna.rhythm_intervals:
        dna.rhythm_intervals = [0.25, 0.5, 0.5, 1.0]
        
    return dna


def mutate_dna_melody(
    dna: SongDNA,
    length_notes: int = 32,
    mutation_rate: float = 0.25,
) -> List[Tuple[int, float]]:
    """Genera una nueva melodia unica guiada por la cadena de Markov con mutacion diatónica."""
    if not dna.pitch_transitions:
        return [(60, 0.5)] * length_notes
        
    current_pitch = random.choice(list(dna.pitch_transitions.keys()))
    new_melody: List[Tuple[int, float]] = []
    
    for _ in range(length_notes):
        # 1. Seleccion de duracion ritmica del ADN
        dur = random.choice(dna.rhythm_intervals) if dna.rhythm_intervals else 0.5
        
        # 2. Mutacion o salto de Markov
        if random.random() < mutation_rate or current_pitch not in dna.pitch_transitions:
            # Salto diatonico relativo (+- 2, 4, 7 semitonos)
            delta = random.choice([-7, -5, -3, -2, 2, 3, 5, 7, 12])
            current_pitch = max(36, min(96, current_pitch + delta))
        else:
            # Seguir la transicion probabilistica del tema original
            next_options = dna.pitch_transitions[current_pitch]
            current_pitch = random.choice(next_options)
            
        new_melody.append((current_pitch, dur))
        
    return new_melody
