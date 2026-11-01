"""Extractor de ADN desde Links de YouTube y Compositor 100% Original (Content ID Safe).

Permite analizar cualquier cancion de YouTube (tempo, escala, modo y densidad armonica)
y componer una obra completamente nueva que comparte la vibra y tonalidad pero
con CERO muestras o melodias copiadas, garantizando el paso de Content ID.
"""

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import List, Optional, Tuple
import wave

import imageio_ffmpeg
import numpy as np
import yt_dlp

from .instruments import measure_timbre
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
    chroma: Optional[List[float]] = None  # Perfil 12-croma normalizado (solo estadistica, no audio)
    brightness_hz: Optional[float] = None  # Centroide espectral (timbre brillante / oscuro)
    bass_ratio: Optional[float] = None  # Energia < 150 Hz sobre el total
    percussiveness: Optional[float] = None  # Energia percusiva (HPSS) sobre el total


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


def compute_chroma(mono: np.ndarray, sr: int, max_sec: float = 15.0) -> np.ndarray:
    """Chromagrama armonico acumulado (12 clases de tono) de los primeros max_sec segundos.

    1. HPSS por mediana: se descarta lo percusivo (caja ~185 Hz, barrido del bombo).
    2. Saliencia armonica: cada nota candidata (C3..F6) suma la energia de sus 6
       primeros armonicos con peso decreciente. Asi el timbre (formantes de un coro,
       armonicos de una tuba) no "inventa" notas que no se tocaron.
    3. Las magnitudes se comprimen con raiz cuadrada para que el bajo no domine.
    """
    # Misma resolucion en Hz a cualquier sample rate (~5.4 Hz por bin)
    scale = max(1, int(round(sr / 22050)))
    n_fft = 4096 * scale
    hop = 1024 * scale
    kernel = 9
    n_harmonics = 6
    decay = 0.6
    window = np.hanning(n_fft)

    max_samples = min(len(mono), int(sr * max_sec))
    starts = range(0, max_samples - n_fft, hop)
    chroma = np.zeros(12, dtype=np.float64)
    if len(starts) == 0:
        return chroma
    spec = np.array([np.abs(np.fft.rfft(mono[st:st + n_fft] * window)) for st in starts])

    if len(spec) >= kernel:
        from numpy.lib.stride_tricks import sliding_window_view

        half = kernel // 2
        harmonic = np.median(sliding_window_view(np.pad(spec, ((half, half), (0, 0)), mode="edge"), kernel, axis=0), axis=-1)
        percussive = np.median(sliding_window_view(np.pad(spec, ((0, 0), (half, half)), mode="edge"), kernel, axis=1), axis=-1)
        spec = spec * (harmonic >= percussive)

    spec = np.sqrt(spec)
    # Tolerancia de +/-1 bin para armonicos que caen entre bins
    spec = np.maximum(spec, np.maximum(np.roll(spec, 1, axis=1), np.roll(spec, -1, axis=1)))
    # Desde C3: por debajo la resolucion no separa semitonos y el barrido de un 808
    # contamina; las notas graves igual aportan por sus armonicos 2 y 3.
    pitches = np.arange(48, 90)
    f0 = 440.0 * 2.0 ** ((pitches - 69) / 12.0)
    bin_hz = sr / n_fft
    salience = np.zeros(len(pitches))
    for k in range(1, n_harmonics + 1):
        bins = np.round(k * f0 / bin_hz).astype(int)
        ok = bins < spec.shape[1]
        salience[ok] += (decay ** (k - 1)) * spec[:, bins[ok]].sum(axis=0)
    np.add.at(chroma, pitches % 12, salience)
    return chroma


def estimate_bpm(mono: np.ndarray, sr: int) -> int:
    """Tempo por autocorrelacion del flujo espectral (onsets) con preferencia suave por ~110 BPM.

    El flujo espectral marca donde empiezan las notas y golpes; su autocorrelacion
    tiene picos en el periodo del pulso. El peso log-gaussiano (como en librosa)
    evita elegir el doble o la mitad del tempo real.
    """
    n_fft, hop = 1024, 256
    if len(mono) < n_fft * 4:
        return 120
    frame_rate = sr / hop
    window = np.hanning(n_fft)
    n_frames = 1 + (len(mono) - n_fft) // hop
    frames = np.lib.stride_tricks.as_strided(
        np.ascontiguousarray(mono, dtype=np.float32),
        shape=(n_frames, n_fft),
        strides=(4 * hop, 4),
    )
    mag = np.log1p(np.abs(np.fft.rfft(frames * window, axis=1)) * 10.0)
    flux = np.maximum(0.0, np.diff(mag, axis=0)).sum(axis=1)
    flux = flux - np.convolve(flux, np.ones(16) / 16.0, mode="same")  # quitar tendencia
    flux = np.maximum(flux, 0.0)

    # Autocorrelacion via FFT (Wiener-Khinchin), O(n log n)
    n_ac = 1 << int(np.ceil(np.log2(2 * len(flux) + 1)))
    spec = np.fft.rfft(flux, n_ac)
    corr = np.fft.irfft(spec * np.conj(spec), n_ac)[:len(flux)]

    # Rango 65 - 170 BPM
    min_lag = max(1, int(frame_rate * 60.0 / 170.0))
    max_lag = min(len(corr) - 1, int(frame_rate * 60.0 / 65.0))
    if max_lag <= min_lag:
        return 120
    lags = np.arange(min_lag, max_lag + 1)
    bpms = 60.0 * frame_rate / lags
    prior = np.exp(-0.5 * (np.log2(bpms / 110.0) / 0.9) ** 2)
    best_lag = lags[int(np.argmax(corr[lags] * prior))]
    # Refinar con interpolacion parabolica para no perder precision entre frames
    if min_lag < best_lag < max_lag:
        y0, y1, y2 = corr[best_lag - 1], corr[best_lag], corr[best_lag + 1]
        denom = y0 - 2 * y1 + y2
        shift = 0.5 * (y0 - y2) / denom if denom else 0.0
    else:
        shift = 0.0
    return int(round(60.0 * frame_rate / (best_lag + shift)))


def analyze_audio_buffer(audio: np.ndarray, sr: int) -> Tuple[int, str, ScaleType, int, float]:
    """Extrae BPM y escala usando procesamiento espectral (Chromagram + Autocorrelacion)."""
    # 1. Deteccion de BPM via Autocorrelacion de Onsets
    mono = np.mean(audio, axis=1) if audio.ndim > 1 else audio
    detected_bpm = estimate_bpm(mono, sr)
        
    detected_bpm = max(70, min(detected_bpm, 160))
    
    # 2. Deteccion de Tonalidad (Chromagram FFT)
    chroma = compute_chroma(mono, sr)
            
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


def convert_to_pcm_wav(input_path: str, output_wav_path: str, max_duration_sec: int = 30) -> str:
    """Convierte cualquier audio (mp3, m4a, flac, ogg, wav 24-bit...) a WAV PCM 16-bit 44.1 kHz estereo."""
    cmd = [
        imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-v", "error",
        "-i", input_path,
        "-t", str(max_duration_sec),
        "-ac", "2", "-ar", "44100", "-acodec", "pcm_s16le",
        output_wav_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0 or not os.path.exists(output_wav_path):
        raise ValueError(f"No se pudo leer el audio '{Path(input_path).name}': {result.stderr.strip()[:200]}")
    return output_wav_path


def load_source_audio(
    url_or_path: str,
    max_duration_sec: int = 30,
    label: Optional[str] = None,
) -> Tuple[np.ndarray, int, str]:
    """Carga hasta max_duration_sec de audio de un link (descarga temporal) o de un archivo local.

    Los archivos locales pueden ser WAV, MP3, M4A, FLAC u OGG (se convierten con ffmpeg).
    El audio se usa SOLO para medir estadisticas (tempo, croma, huella) y los temporales
    se borran antes de retornar: nunca entra en la composicion.
    """
    temp_dir = tempfile.mkdtemp()
    try:
        if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
            target_wav = os.path.join(temp_dir, "yt_preview.wav")
            downloaded = download_youtube_audio_preview(url_or_path, target_wav)
            wav_file = convert_to_pcm_wav(downloaded, os.path.join(temp_dir, "pcm.wav"), max_duration_sec)
            source_label = label or url_or_path
        else:
            wav_file = convert_to_pcm_wav(url_or_path, os.path.join(temp_dir, "pcm.wav"), max_duration_sec)
            source_label = label or Path(url_or_path).name

        with wave.open(wav_file, "rb") as wf:
            n_ch = wf.getnchannels()
            sr = wf.getframerate()
            n_frames = min(wf.getnframes(), sr * max_duration_sec)
            raw = wf.readframes(n_frames)
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            if n_ch == 2:
                samples = samples.reshape(-1, 2)
        return samples, sr, source_label
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def analyze_loaded_audio(samples: np.ndarray, sr: int, source_label: str) -> ExtractedYouTubeDNA:
    """Extrae el ADN (tempo, tonalidad, croma) de un buffer de audio ya cargado."""
    bpm, key_name, scale_type, root_midi, confidence = analyze_audio_buffer(samples, sr)
    dur = float(len(samples)) / sr
    mono = np.mean(samples, axis=1) if samples.ndim > 1 else samples
    chroma = compute_chroma(mono, sr)
    norm = float(np.max(chroma)) or 1.0
    timbre = measure_timbre(mono, sr)
    
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
        chroma=[round(float(c) / norm, 4) for c in chroma],
        brightness_hz=timbre.brightness_hz,
        bass_ratio=timbre.bass_ratio,
        percussiveness=timbre.percussiveness,
    )


def analyze_youtube_dna(url_or_wav: str) -> ExtractedYouTubeDNA:
    """Extrae las caracteristicas de tempo y tonalidad de un video de YouTube o archivo de audio."""
    samples, sr, source_label = load_source_audio(url_or_wav)
    return analyze_loaded_audio(samples, sr, source_label)


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
