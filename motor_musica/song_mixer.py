"""Modulo de Mezcla Multipista, Mashups y Crossfade entre Canciones.

Permite fusionar dos o mas pistas del catalogo:
1. Crossfade DJ continuo (transicion suave entre temas).
2. Mashup Hibrido de Stems (Bateria y Bajo de Pista A + Armonia y Melodia de Pista B).
3. Mezcla en Paralelo (Dual Deck Blend con balance de ganancia).
"""

from dataclasses import dataclass
import math
import os
from pathlib import Path
from typing import List, Optional, Tuple
import wave

import numpy as np
import mido
from mido import MidiFile, MidiTrack, Message, MetaMessage

from .midi_generator import NoteEvent, MidiTrackBundle, _populate_midi_tracks
from .synth_renderer import render_midi_to_wav, calculate_loudness_stats, _master_to_target_lufs, SynthConfig, AudioMetrics
from .metadata_manager import generate_track_metadata, TrackMetadata


def _read_wav_stereo(wav_path: str) -> Tuple[np.ndarray, int]:
    """Lee un archivo WAV y devuelve array estereo float32 en rango [-1.0, 1.0] y sample rate."""
    with wave.open(wav_path, "rb") as wf:
        n_ch = wf.getnchannels()
        sr = wf.getframerate()
        sw = wf.getsampwidth()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)
        
    if sw == 2:
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sw == 3:
        # 24-bit PCM
        n_samples = len(raw) // 3
        int_samples = np.zeros(n_samples, dtype=np.int32)
        for i in range(n_samples):
            b = raw[i*3 : (i+1)*3]
            int_samples[i] = int.from_bytes(b, byteorder="little", signed=True)
        samples = int_samples.astype(np.float32) / 8388608.0
    else:
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        
    if n_ch == 1:
        stereo = np.column_stack([samples, samples])
    else:
        stereo = samples.reshape(-1, 2)
        
    return stereo, sr


def _write_wav_stereo(stereo: np.ndarray, sr: int, output_wav: str) -> None:
    """Escribe un array estereo en archivo WAV PCM de 16 bits."""
    clamped = np.clip(stereo, -0.9999, 0.9999)
    int16_data = (clamped * 32767.0).astype(np.int16)
    with wave.open(output_wav, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(int16_data.tobytes())


def crossfade_audio_tracks(
    wav_path_a: str,
    wav_path_b: str,
    output_wav: str,
    crossfade_sec: float = 4.0,
    target_lufs: float = -14.0,
) -> AudioMetrics:
    """Une dos canciones en secuencia con crossfade de potencia constante (DJ transition)."""
    audio_a, sr_a = _read_wav_stereo(wav_path_a)
    audio_b, sr_b = _read_wav_stereo(wav_path_b)
    
    sr = sr_a
    # Ajustar longitud del crossfade
    fade_samples = int(crossfade_sec * sr)
    fade_samples = min(fade_samples, len(audio_a) // 2, len(audio_b) // 2)
    
    if fade_samples <= 0:
        fade_samples = sr * 2
        
    total_len = len(audio_a) + len(audio_b) - fade_samples
    out_stereo = np.zeros((total_len, 2), dtype=np.float32)
    
    # 1. Copiar cuerpo de Track A antes del crossfade
    out_stereo[: len(audio_a) - fade_samples] = audio_a[: -fade_samples]
    
    # 2. Region de Crossfade (Curva de Potencia Constante: Cos / Sin)
    t = np.linspace(0.0, 1.0, fade_samples, dtype=np.float32)[:, np.newaxis]
    gain_a = np.cos(t * (np.pi / 2.0))
    gain_b = np.sin(t * (np.pi / 2.0))
    
    fade_start = len(audio_a) - fade_samples
    fade_end = len(audio_a)
    out_stereo[fade_start:fade_end] = (
        audio_a[-fade_samples:] * gain_a + audio_b[:fade_samples] * gain_b
    )
    
    # 3. Copiar cuerpo de Track B despues del crossfade
    out_stereo[fade_end:] = audio_b[fade_samples:]
    
    # Masterizar
    mastered = _master_to_target_lufs(out_stereo, sr, target_lufs=target_lufs)
    _write_wav_stereo(mastered, sr, output_wav)
    
    return calculate_loudness_stats(mastered, sr)


def blend_audio_tracks(
    wav_path_a: str,
    wav_path_b: str,
    output_wav: str,
    balance_a_to_b: float = 0.5,  # 0.0 = solo A, 0.5 = 50/50, 1.0 = solo B
    target_lufs: float = -14.0,
) -> AudioMetrics:
    """Mezcla simultaneamente dos pistas en paralelo con control de balance."""
    audio_a, sr_a = _read_wav_stereo(wav_path_a)
    audio_b, sr_b = _read_wav_stereo(wav_path_b)
    
    sr = sr_a
    max_len = max(len(audio_a), len(audio_b))
    
    pad_a = np.zeros((max_len, 2), dtype=np.float32)
    pad_b = np.zeros((max_len, 2), dtype=np.float32)
    
    pad_a[: len(audio_a)] = audio_a
    pad_b[: len(audio_b)] = audio_b
    
    gain_a = float(1.0 - balance_a_to_b)
    gain_b = float(balance_a_to_b)
    
    mixed = (pad_a * gain_a) + (pad_b * gain_b)
    mastered = _master_to_target_lufs(mixed, sr, target_lufs=target_lufs)
    _write_wav_stereo(mastered, sr, output_wav)
    
    return calculate_loudness_stats(mastered, sr)


def stem_mashup_remix(
    bundle_a: MidiTrackBundle,
    bundle_b: MidiTrackBundle,
    output_mid: str,
    output_wav: str,
    custom_title: Optional[str] = None,
    track_number: int = 1,
) -> Tuple[TrackMetadata, AudioMetrics]:
    """Crea un Remix Hibrido combinando Bateria/Bajo de A y Armonia/Melodia de B."""
    # Extraer eventos
    drums_bass_events = [e for e in bundle_a.events if e.track_name in ("drums", "bass")]
    chords_melody_events = [e for e in bundle_b.events if e.track_name in ("chords", "melody")]
    
    # Armonizar: Transportar Pista B a la tonalidad de Pista A si difieren
    semitone_diff = bundle_a.profile.root_note - bundle_b.profile.root_note
    harmonized_chords_melody = []
    for ev in chords_melody_events:
        new_pitch = min(120, max(24, ev.pitch + semitone_diff))
        harmonized_chords_melody.append(
            NoteEvent(
                pitch=new_pitch,
                velocity=ev.velocity,
                start_sec=ev.start_sec,
                duration_sec=ev.duration_sec,
                track_name=ev.track_name,
                channel=ev.channel,
            )
        )
        
    combined_events = drums_bass_events + harmonized_chords_melody
    # Duracion total
    dur = max(bundle_a.duration_sec, bundle_b.duration_sec)
    
    # Construir MIDI hibrido
    mid = MidiFile(type=1)
    track_tempo = MidiTrack()
    tempo_val = mido.bpm2tempo(bundle_a.bpm)
    track_tempo.append(MetaMessage("set_tempo", tempo=tempo_val, time=0))
    track_tempo.append(MetaMessage("track_name", name="Hybrid Mashup Conductor", time=0))
    track_tempo.append(MetaMessage("end_of_track", time=0))
    mid.tracks.append(track_tempo)
    
    for t_name in ["chords", "melody", "bass", "drums"]:
        t = MidiTrack()
        t.append(MetaMessage("track_name", name=f"Mashup - {t_name.capitalize()}", time=0))
        mid.tracks.append(t)
        
    _populate_midi_tracks(mid, combined_events, bundle_a.bpm, mid.ticks_per_beat)
    mid.save(output_mid)
    
    # Renderizar WAV hibrido
    hybrid_bundle = MidiTrackBundle(
        profile=bundle_a.profile,
        bars=max(bundle_a.bars, bundle_b.bars),
        bpm=bundle_a.bpm,
        duration_sec=dur,
        midi_file=mid,
        events=combined_events,
    )
    
    cfg = SynthConfig(sample_rate=44100, target_lufs=-14.0, bit_depth=16)
    metrics = render_midi_to_wav(hybrid_bundle, output_wav, config=cfg)
    
    title = custom_title or f"Hybrid Mashup ({bundle_a.profile.name} x {bundle_b.profile.name})"
    genre_tag = f"{bundle_a.profile.drum_style}_x_{bundle_b.profile.drum_style}"
    
    meta = generate_track_metadata(
        genre=bundle_a.profile.name,
        bpm=bundle_a.bpm,
        scale=bundle_a.profile.scale_type.value,
        duration_sec=metrics.duration_sec,
        track_number=track_number,
        midi_filename=Path(output_mid).name,
        audio_filename=Path(output_wav).name,
        peak_dbfs=metrics.peak_dbfs,
        estimated_lufs=metrics.estimated_lufs,
        custom_title=title,
    )
    
    return meta, metrics
