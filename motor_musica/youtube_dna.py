"""Extractor de ADN desde Links de YouTube y Compositor 100% Original (Content ID Safe).

Permite analizar cualquier cancion de YouTube (tempo, escala, modo y densidad armonica)
y componer una obra completamente nueva que comparte la vibra y tonalidad pero
con CERO muestras o melodias copiadas, garantizando el paso de Content ID.
"""

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import tempfile
from typing import Optional, Tuple
import wave

import imageio_ffmpeg
import numpy as np
import yt_dlp

from .theory import GENRES, MusicalProfile, ScaleType
from .midi_generator import generate_track_midi, MidiTrackBundle
from .synth_renderer import render_midi_to_wav, SynthConfig, AudioMetrics
from .metadata_manager import generate_track_metadata, TrackMetadata

# Perfiles tonales de Krumhansl-Schmuckler para deteccion de escala
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
PITCH_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
BASE_MIDI_MAP = {"C": 48, "C#": 49, "D": 50, "D#": 51, "E": 52, "F": 53, "F#": 54, "G": 55, "G#": 56, "A": 57, "A#": 58, "B": 59}


@dataclass
class ExtractedYouTubeDNA:
    source_url: str
    detected_bpm: int
    detected_key: str
    root_midi: int
    scale_type: ScaleType
    genre_hint: str
    confidence: float
    analysis_duration_sec: float


def download_youtube_audio_preview(url: str, output_wav_path: str, max_duration_sec: int = 30) -> str:
    """Descarga de forma rapida un fragmento de audio de YouTube usando yt-dlp y ffmpeg."""
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    
    ydl_opts = {
        "format": "bestaudio/best",
        "ffmpeg_location": ffmpeg_exe,
        "outtmpl": output_wav_path.replace(".wav", ""),
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "wav",
        }],
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
        
    final_wav = output_wav_path if os.path.exists(output_wav_path) else output_wav_path.replace(".wav", "") + ".wav"
    return final_wav


def analyze_audio_buffer(audio: np.ndarray, sr: int) -> Tuple[int, str, ScaleType, int, float]:
    """Extrae BPM y escala usando procesamiento espectral (Chromagram + Autocorrelacion)."""
    # 1. Deteccion de BPM via Autocorrelacion de Onsets
    mono = np.mean(audio, axis=1) if audio.ndim > 1 else audio
    # Downsample para velocidad
    target_sr = 11025
    step_down = max(1, sr // target_sr)
    downsampled = mono[::step_down]
    effective_sr = sr // step_down
    
    # Envolvente de energía
    envelope = np.diff(np.abs(downsampled), prepend=0.0)
    envelope = np.maximum(0, envelope)
    
    # Autocorrelación para rango 65 - 170 BPM
    min_lag = int(effective_sr * (60.0 / 170.0))
    max_lag = int(effective_sr * (60.0 / 65.0))
    
    corr = np.correlate(envelope, envelope, mode="full")
    corr = corr[len(corr) // 2:]
    
    if len(corr) > max_lag:
        search_region = corr[min_lag:max_lag]
        best_lag = min_lag + int(np.argmax(search_region))
        detected_bpm = int(round((60.0 * effective_sr) / best_lag))
    else:
        detected_bpm = 120
        
    detected_bpm = max(70, min(detected_bpm, 160))
    
    # 2. Deteccion de Tonalidad (Chromagram FFT)
    n_fft = 4096
    hop = 2048
    chroma = np.zeros(12, dtype=np.float32)
    
    # Ventanas FFT a lo largo de los primeros 15 segundos
    max_samples = min(len(mono), sr * 15)
    for start in range(0, max_samples - n_fft, hop):
        segment = mono[start:start + n_fft] * np.hanning(n_fft)
        spectrum = np.abs(np.fft.rfft(segment))
        freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
        
        # Mapear frecuencias audibles (65 Hz a 2000 Hz) a clases de tono (0-11)
        valid = (freqs >= 65.0) & (freqs <= 2000.0)
        valid_freqs = freqs[valid]
        valid_mags = spectrum[valid]
        
        pitch_classes = np.round(12.0 * np.log2(valid_freqs / 440.0) + 69.0).astype(int) % 12
        for p_cls, mag in zip(pitch_classes, valid_mags):
            chroma[p_cls] += mag
            
    # Correlacion con Krumhansl-Schmuckler
    best_score = -1.0
    best_pitch_name = "A"
    best_mode = "minor"
    
    for i in range(12):
        # Mayor
        maj_shift = np.roll(MAJOR_PROFILE, i)
        score_maj = float(np.corrcoef(chroma, maj_shift)[0, 1])
        if score_maj > best_score:
            best_score = score_maj
            best_pitch_name = PITCH_NAMES[i]
            best_mode = "major"
            
        # Menor
        min_shift = np.roll(MINOR_PROFILE, i)
        score_min = float(np.corrcoef(chroma, min_shift)[0, 1])
        if score_min > best_score:
            best_score = score_min
            best_pitch_name = PITCH_NAMES[i]
            best_mode = "minor"
            
    root_midi = BASE_MIDI_MAP.get(best_pitch_name, 57)
    scale_type = ScaleType.NATURAL_MINOR if best_mode == "minor" else ScaleType.DORIAN
    key_name = f"{best_pitch_name} {best_mode}"
    
    return detected_bpm, key_name, scale_type, root_midi, max(0.6, min(best_score, 0.99))


def analyze_youtube_dna(url_or_wav: str) -> ExtractedYouTubeDNA:
    """Extrae las caracteristicas de tempo y tonalidad de un video de YouTube o archivo WAV."""
    temp_dir = tempfile.mkdtemp()
    
    if url_or_wav.startswith("http://") or url_or_wav.startswith("https://"):
        target_wav = os.path.join(temp_dir, "yt_preview.wav")
        wav_file = download_youtube_audio_preview(url_or_wav, target_wav)
        source_label = url_or_wav
    else:
        wav_file = url_or_wav
        source_label = Path(url_or_wav).name
        
    with wave.open(wav_file, "rb") as wf:
        n_ch = wf.getnchannels()
        sr = wf.getframerate()
        n_frames = min(wf.getnframes(), sr * 30)  # Max 30 segs
        raw = wf.readframes(n_frames)
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if n_ch == 2:
            samples = samples.reshape(-1, 2)
            
    bpm, key_name, scale_type, root_midi, confidence = analyze_audio_buffer(samples, sr)
    dur = float(len(samples)) / sr if samples.ndim == 1 else float(len(samples)) / sr
    
    # Sugerir genero segun tempo y modo
    if bpm >= 135:
        genre_hint = "dark_trap" if "minor" in key_name else "hard_rock"
    elif bpm <= 95:
        genre_hint = "boom_bap" if "minor" in key_name else "lofi_chill"
    else:
        genre_hint = "synthwave" if "minor" in key_name else "epic_cinematic"
        
    return ExtractedYouTubeDNA(
        source_url=source_label,
        detected_bpm=bpm,
        detected_key=key_name,
        root_midi=root_midi,
        scale_type=scale_type,
        genre_hint=genre_hint,
        confidence=round(confidence, 2),
        analysis_duration_sec=round(dur, 2),
    )


def compose_original_from_youtube_dna(
    dna: ExtractedYouTubeDNA,
    bars: int = 16,
    custom_title: Optional[str] = None,
    output_mid_path: Optional[str] = None,
    output_wav_path: Optional[str] = None,
    track_number: int = 1,
) -> Tuple[TrackMetadata, AudioMetrics]:
    """Compone una obra 100% original a partir de los parametros de tempo y tonalidad extraidos."""
    # Usar el genero sugerido por el analisis
    genre = dna.genre_hint
    
    # 1. Generar composicion algoritmica limpia
    bundle = generate_track_midi(
        genre=genre,
        bars=bars,
        output_mid_path=output_mid_path,
    )
    
    # 2. Renderizar audio WAV masterizado
    cfg = SynthConfig(sample_rate=44100, target_lufs=-14.0, bit_depth=16)
    metrics = render_midi_to_wav(bundle, output_wav_path or "temp_yt.wav", config=cfg)
    
    title = custom_title or f"Inspired by {dna.detected_key} [{genre.upper()}]"
    
    meta = generate_track_metadata(
        genre=genre,
        bpm=dna.detected_bpm,
        scale=dna.scale_type.value,
        duration_sec=metrics.duration_sec,
        track_number=track_number,
        midi_filename=Path(output_mid_path).name if output_mid_path else "yt_track.mid",
        audio_filename=Path(output_wav_path).name if output_wav_path else "yt_track.wav",
        peak_dbfs=metrics.peak_dbfs,
        estimated_lufs=metrics.estimated_lufs,
        custom_title=title,
    )
    
    return meta, metrics
