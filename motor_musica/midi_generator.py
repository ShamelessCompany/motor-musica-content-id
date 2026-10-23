"""Generador de Archivos MIDI Multipista Algoritmicos (Sin Loops Externos).

Produce pistas MIDI limpias y estructuradas compatibles con FL Studio, Reaper,
y con el motor de sintesis procedural de audio integrado.
"""

from dataclasses import dataclass, field
import random
from typing import Dict, List, Optional
import mido
from mido import MidiFile, MidiTrack, Message, MetaMessage

from .theory import (
    GENRES,
    MusicalProfile,
    ScaleType,
    build_scale_notes,
    get_chord_notes,
    get_bass_note,
)


@dataclass
class NoteEvent:
    pitch: int
    velocity: int
    start_sec: float
    duration_sec: float
    track_name: str
    channel: int


@dataclass
class MidiTrackBundle:
    profile: MusicalProfile
    bars: int
    bpm: int
    duration_sec: float
    midi_file: MidiFile
    events: List[NoteEvent] = field(default_factory=list)


def _delta_to_ticks(delta_sec: float, bpm: int, ticks_per_beat: int) -> int:
    beats = delta_sec * (bpm / 60.0)
    return max(0, int(round(beats * ticks_per_beat)))


def generate_track_midi(
    genre: str = "epic_cinematic",
    bars: int = 16,
    seed: Optional[int] = None,
    output_mid_path: Optional[str] = None,
) -> MidiTrackBundle:
    """Genera una composición multipista algorítmica completa en formato MIDI."""
    if seed is not None:
        random.seed(seed)
        
    profile = GENRES.get(genre, GENRES["epic_cinematic"])
    bpm = profile.bpm
    progression = random.choice(profile.progressions)
    
    seconds_per_beat = 60.0 / bpm
    seconds_per_bar = seconds_per_beat * 4.0
    total_duration_sec = seconds_per_bar * bars
    
    mid = MidiFile(type=1)
    ticks_per_beat = mid.ticks_per_beat  # Default 480
    
    # 0. Pista Conductora (Tempo y Metadatos)
    track_tempo = MidiTrack()
    track_tempo.append(MetaMessage("track_name", name=f"{profile.name} - Conductor", time=0))
    tempo_val = mido.bpm2tempo(bpm)
    track_tempo.append(MetaMessage("set_tempo", tempo=tempo_val, time=0))
    track_tempo.append(MetaMessage("time_signature", numerator=4, denominator=4, time=0))
    track_tempo.append(MetaMessage("end_of_track", time=0))
    mid.tracks.append(track_tempo)
    
    # 1. Armonia (Chords / Pads) - Canal 0
    track_chords = MidiTrack()
    track_chords.append(MetaMessage("track_name", name="Chords & Pads", time=0))
    track_chords.append(Message("program_change", channel=0, program=89, time=0))  # Warm Pad
    
    # 2. Melodia / Lead - Canal 1
    track_melody = MidiTrack()
    track_melody.append(MetaMessage("track_name", name="Lead & Arp", time=0))
    track_melody.append(Message("program_change", channel=1, program=81, time=0))  # Lead Synth
    
    # 3. Bajo - Canal 2
    track_bass = MidiTrack()
    track_bass.append(MetaMessage("track_name", name="Bassline", time=0))
    track_bass.append(Message("program_change", channel=2, program=38, time=0))  # Synth Bass
    
    # 4. Bateria (Percussion GM) - Canal 9 (MIDI 10)
    track_drums = MidiTrack()
    track_drums.append(MetaMessage("track_name", name="Drums", time=0))
    
    mid.tracks.extend([track_chords, track_melody, track_bass, track_drums])
    
    all_events: List[NoteEvent] = []
    scale_palette = build_scale_notes(profile.root_note, profile.scale_type, octaves=4)
    
    # Generar compás por compás
    for bar_idx in range(bars):
        bar_start_sec = bar_idx * seconds_per_bar
        degree_idx = progression[bar_idx % len(progression)]
        
        # A. Acordes (Chords)
        chord_pitches = get_chord_notes(
            profile.root_note,
            profile.scale_type,
            degree_idx,
            extended=(profile.drum_style == "lofi"),
        )
        chord_dur = seconds_per_bar * 0.96  # Dejar micro respiro antes del próximo acorde
        chord_vel = random.randint(78, 88)
        for p in chord_pitches:
            all_events.append(
                NoteEvent(
                    pitch=p,
                    velocity=chord_vel,
                    start_sec=bar_start_sec,
                    duration_sec=chord_dur,
                    track_name="chords",
                    channel=0,
                )
            )
            
        # B. Bajo (Bassline)
        bass_pitch = get_bass_note(profile.root_note, profile.scale_type, degree_idx)
        if profile.drum_style == "epic":
            # 8 corcheas motrices
            sub_dur = seconds_per_beat * 0.5
            for step in range(8):
                p = bass_pitch if step % 2 == 0 else (bass_pitch + 12 if random.random() > 0.6 else bass_pitch)
                all_events.append(
                    NoteEvent(
                        pitch=p,
                        velocity=random.randint(90, 105),
                        start_sec=bar_start_sec + (step * sub_dur),
                        duration_sec=sub_dur * 0.85,
                        track_name="bass",
                        channel=2,
                    )
                )
        elif profile.drum_style == "synthwave":
            # 8 corcheas sincopadas (octavas)
            sub_dur = seconds_per_beat * 0.5
            for step in range(8):
                p = bass_pitch + (12 if step % 2 == 1 else 0)
                all_events.append(
                    NoteEvent(
                        pitch=p,
                        velocity=random.randint(95, 110),
                        start_sec=bar_start_sec + (step * sub_dur),
                        duration_sec=sub_dur * 0.9,
                        track_name="bass",
                        channel=2,
                    )
                )
        elif profile.drum_style == "rock":
            # Bajo Rock: corcheas continuas potentes marcando la raiz
            sub_dur = seconds_per_beat * 0.5
            for step in range(8):
                p = bass_pitch if (step % 4 != 3) else (bass_pitch + 7 if random.random() < 0.4 else bass_pitch)
                all_events.append(
                    NoteEvent(
                        pitch=p,
                        velocity=random.randint(100, 118),
                        start_sec=bar_start_sec + (step * sub_dur),
                        duration_sec=sub_dur * 0.92,
                        track_name="bass",
                        channel=2,
                    )
                )
        elif profile.drum_style == "trap":
            # 808 Sub Bass: Golpes largos y potentes con micro variaciones
            trap_hits = [(0, 1.5), (6, 1.0), (10, 1.2)]
            sub_16 = seconds_per_beat * 0.25
            for s16, dur_beats in trap_hits:
                p = bass_pitch if s16 == 0 else (bass_pitch + 1 if random.random() < 0.4 else bass_pitch)
                while p > 45:
                    p -= 12
                while p < 33:
                    p += 12
                all_events.append(
                    NoteEvent(
                        pitch=p,
                        velocity=random.randint(115, 127),
                        start_sec=bar_start_sec + (s16 * sub_16),
                        duration_sec=dur_beats * seconds_per_beat,
                        track_name="bass",
                        channel=2,
                    )
                )
        elif profile.drum_style == "boombap":
            # Walking bassline boombap en tiempos sincopados
            sub_dur = seconds_per_beat * 0.5
            for step in [0, 3, 4, 6]:
                p = bass_pitch if step == 0 else bass_pitch + random.choice([0, 3, 5, 7])
                while p > 46:
                    p -= 12
                all_events.append(
                    NoteEvent(
                        pitch=p,
                        velocity=random.randint(90, 105),
                        start_sec=bar_start_sec + (step * sub_dur),
                        duration_sec=sub_dur * 0.88,
                        track_name="bass",
                        channel=2,
                    )
                )
        else:  # lofi
            # 2 notas largas en tiempos 1 y 3
            sub_dur = seconds_per_bar * 0.45
            for step in range(2):
                p = bass_pitch if step == 0 else (bass_pitch + 7)
                all_events.append(
                    NoteEvent(
                        pitch=p,
                        velocity=random.randint(80, 92),
                        start_sec=bar_start_sec + (step * seconds_per_beat * 2),
                        duration_sec=sub_dur,
                        track_name="bass",
                        channel=2,
                    )
                )
                
        # C. Melodía / Arpegio
        if profile.melody_style == "arp":
            # Semicorcheas arpegiadas sobre notas del acorde + octava alta
            sub_dur = seconds_per_beat * 0.25
            arp_pool = chord_pitches + [chord_pitches[0] + 12, chord_pitches[1] + 12]
            for step in range(16):
                # Variar patrón
                p = arp_pool[step % len(arp_pool)]
                vel = 100 if step % 4 == 0 else random.randint(80, 92)
                all_events.append(
                    NoteEvent(
                        pitch=p,
                        velocity=vel,
                        start_sec=bar_start_sec + (step * sub_dur),
                        duration_sec=sub_dur * 0.85,
                        track_name="melody",
                        channel=1,
                    )
                )
        elif profile.melody_style == "lead":
            # Fraseo melódico con preguntas y respuestas
            sub_dur = seconds_per_beat * 0.5
            melody_notes = [p for p in scale_palette if 65 <= p <= 84]
            for step in range(8):
                if random.random() < 0.25:
                    continue  # Silencio para dar dinamismo
                p = random.choice(chord_pitches) if random.random() < 0.6 else random.choice(melody_notes)
                all_events.append(
                    NoteEvent(
                        pitch=p + 12,
                        velocity=random.randint(90, 108),
                        start_sec=bar_start_sec + (step * sub_dur),
                        duration_sec=sub_dur * 0.9,
                        track_name="melody",
                        channel=1,
                    )
                )
        elif profile.melody_style == "rock_solo":
            # Riffs y solos de guitarra blues/rock con bending y notas de paso
            sub_dur = seconds_per_beat * 0.25
            solo_pool = [p for p in scale_palette if 52 <= p <= 76]
            step = 0
            while step < 16:
                note_len = random.choice([1, 2, 4])  # semicorchea, corchea, negra
                if step + note_len > 16:
                    note_len = 16 - step
                p = random.choice(solo_pool) if solo_pool else chord_pitches[0] + 12
                # Posibilidad de subir octava para climax
                if random.random() < 0.3:
                    p += 12
                all_events.append(
                    NoteEvent(
                        pitch=min(96, p),
                        velocity=random.randint(95, 122),
                        start_sec=bar_start_sec + (step * sub_dur),
                        duration_sec=(sub_dur * note_len) * 0.92,
                        track_name="melody",
                        channel=1,
                    )
                )
                step += note_len
        elif profile.melody_style == "trap_bells":
            # Melodia oscura de campanas/plucks tipo Metro Boomin con espacio vocal
            sub_dur = seconds_per_beat * 0.5
            for step in range(8):
                if step in [1, 3, 6] and random.random() < 0.4:
                    continue
                p = random.choice(chord_pitches) + 24
                all_events.append(
                    NoteEvent(
                        pitch=min(96, p),
                        velocity=random.randint(85, 105),
                        start_sec=bar_start_sec + (step * sub_dur),
                        duration_sec=sub_dur * 0.85,
                        track_name="melody",
                        channel=1,
                    )
                )
        else:  # jazz lofi
            sub_dur = seconds_per_beat
            for step in range(4):
                if step == 2 and random.random() < 0.4:
                    continue
                p = chord_pitches[(step + degree_idx) % len(chord_pitches)] + 12
                hit_time = max(0.0, bar_start_sec + (step * sub_dur) + random.uniform(-0.015, 0.015))
                all_events.append(
                    NoteEvent(
                        pitch=p,
                        velocity=random.randint(70, 85),
                        start_sec=hit_time,
                        duration_sec=sub_dur * 0.8,
                        track_name="melody",
                        channel=1,
                    )
                )

        # D. Batería Procedural (Canal 9)
        # GM Drum pitches: Kick=36, Snare=38, ClosedHat=42, OpenHat=46
        sub_16 = seconds_per_beat * 0.25
        for s16 in range(16):
            t_hit = bar_start_sec + (s16 * sub_16)
            # Hi-Hats: cada semicorchea o corchea
            if profile.drum_style == "trap":
                # Trap Hi-Hats: semicorcheas con velocity variable y rolls de 32avos
                all_events.append(
                    NoteEvent(
                        pitch=42,
                        velocity=random.randint(85, 105) if s16 % 4 == 0 else random.randint(65, 85),
                        start_sec=t_hit,
                        duration_sec=0.04,
                        track_name="drums",
                        channel=9,
                    )
                )
                if s16 in (6, 14):  # Roll de 32avo
                    all_events.append(
                        NoteEvent(
                            pitch=42,
                            velocity=random.randint(70, 90),
                            start_sec=t_hit + (sub_16 * 0.5),
                            duration_sec=0.03,
                            track_name="drums",
                            channel=9,
                        )
                    )
            elif profile.drum_style in ("synthwave", "epic", "rock"):
                # Crash en el primer compas o transiciones
                if profile.drum_style == "rock" and s16 == 0 and (bar_idx % 4 == 0):
                    all_events.append(
                        NoteEvent(
                            pitch=49,  # Crash Cymbal
                            velocity=random.randint(110, 125),
                            start_sec=t_hit,
                            duration_sec=0.75,
                            track_name="drums",
                            channel=9,
                        )
                    )
                if s16 % 2 == 0:
                    hat_pitch = 46 if (profile.drum_style == "rock" or (s16 == 14 and random.random() < 0.5)) else 42
                    all_events.append(
                        NoteEvent(
                            pitch=hat_pitch,
                            velocity=random.randint(85, 105) if s16 % 4 == 0 else random.randint(70, 85),
                            start_sec=t_hit,
                            duration_sec=0.08,
                            track_name="drums",
                            channel=9,
                        )
                    )
            else:  # Lofi y boombap swung hats
                if s16 % 2 == 0:
                    swing = 0.02 if s16 % 4 == 2 else 0.0
                    all_events.append(
                        NoteEvent(
                            pitch=42,
                            velocity=random.randint(75, 90) if profile.drum_style == "boombap" else random.randint(65, 80),
                            start_sec=t_hit + swing,
                            duration_sec=0.06,
                            track_name="drums",
                            channel=9,
                        )
                    )

            # Kick
            is_kick = False
            if profile.drum_style == "synthwave":
                # 4 on the floor (tiempos 0, 4, 8, 12)
                is_kick = (s16 % 4 == 0)
            elif profile.drum_style == "trap":
                # Trap Kick: síncopa dura con el 808
                is_kick = s16 in [0, 6, 11]
            elif profile.drum_style == "boombap":
                is_kick = s16 in [0, 5, 10]
            elif profile.drum_style == "rock":
                # Rock Beat: bombo en 1, 2-and, 3
                is_kick = s16 in [0, 6, 8, 10] or (s16 == 0)
            elif profile.drum_style == "epic":
                is_kick = s16 in [0, 6, 8, 14] or (s16 % 4 == 0)
            else:  # lofi boom-bap
                is_kick = s16 in [0, 6, 10]
                
            if is_kick:
                all_events.append(
                    NoteEvent(
                        pitch=36,
                        velocity=random.randint(105, 120),
                        start_sec=t_hit,
                        duration_sec=0.15,
                        track_name="drums",
                        channel=9,
                    )
                )
                
            # Snare / Clap
            is_snare = False
            if profile.drum_style == "trap":
                # En Trap a 140 BPM (Half-time), la caja/clap va en el tiempo 3 (s16 == 8)
                is_snare = (s16 == 8)
            else:
                is_snare = (s16 in [4, 12])  # Beats 2 and 4
                if (bar_idx + 1) % 4 == 0 and s16 >= 12:
                    is_snare = True
                
            if is_snare:
                all_events.append(
                    NoteEvent(
                        pitch=38,
                        velocity=random.randint(100, 120),
                        start_sec=t_hit,
                        duration_sec=0.18,
                        track_name="drums",
                        channel=9,
                    )
                )

    # Construir pistas MIDI secuenciales a partir de los NoteEvents
    _populate_midi_tracks(mid, all_events, bpm, ticks_per_beat)
    
    if output_mid_path:
        mid.save(output_mid_path)
        
    return MidiTrackBundle(
        profile=profile,
        bars=bars,
        bpm=bpm,
        duration_sec=total_duration_sec,
        midi_file=mid,
        events=all_events,
    )


def _populate_midi_tracks(
    mid: MidiFile,
    events: List[NoteEvent],
    bpm: int,
    ticks_per_beat: int,
) -> None:
    """Convierte eventos con timestamp absoluto a mensajes MIDI delta-time para cada pista."""
    track_map: Dict[str, MidiTrack] = {
        "chords": mid.tracks[1],
        "melody": mid.tracks[2],
        "bass": mid.tracks[3],
        "drums": mid.tracks[4],
    }
    
    # Agrupar eventos por track
    by_track: Dict[str, List[Tuple[float, str, int, int, int]]] = {
        "chords": [],
        "melody": [],
        "bass": [],
        "drums": [],
    }
    
    for ev in events:
        if ev.track_name in by_track:
            # (time_sec, type, pitch, velocity, channel)
            by_track[ev.track_name].append((ev.start_sec, "note_on", ev.pitch, ev.velocity, ev.channel))
            by_track[ev.track_name].append((ev.start_sec + ev.duration_sec, "note_off", ev.pitch, 0, ev.channel))
            
    for t_name, raw_msgs in by_track.items():
        # Ordenar por tiempo
        raw_msgs.sort(key=lambda x: (x[0], 0 if x[1] == "note_off" else 1))
        current_time_sec = 0.0
        track = track_map[t_name]
        
        for msg_sec, m_type, pitch, vel, ch in raw_msgs:
            delta_sec = max(0.0, msg_sec - current_time_sec)
            ticks = _delta_to_ticks(delta_sec, bpm, ticks_per_beat)
            current_time_sec = msg_sec
            track.append(Message(m_type, note=pitch, velocity=vel, time=ticks, channel=ch))
        track.append(MetaMessage("end_of_track", time=0))
