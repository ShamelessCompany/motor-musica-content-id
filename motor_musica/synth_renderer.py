"""Motor de Sintesis Procedural de Audio y Masterizacion a -14 LUFS.

Renderiza archivos de audio WAV estereo sin necesidad de DAWs ni librerias externas,
asegurando sintesis matematica 100% original apta para Content ID.
"""

from dataclasses import dataclass
import math
import struct
from typing import Dict, List, Optional, Tuple
import wave

import numpy as np

from .midi_generator import NoteEvent, MidiTrackBundle


@dataclass
class SynthConfig:
    sample_rate: int = 44100
    target_lufs: float = -14.0
    tail_sec: float = 2.0  # Cola de reverberacion / release al final
    bit_depth: int = 16  # 16 o 24 bits


@dataclass
class AudioMetrics:
    duration_sec: float
    sample_rate: int
    peak_dbfs: float
    rms_dbfs: float
    estimated_lufs: float
    clipped_samples: int


def _midi_to_freq(pitch: int) -> float:
    return 440.0 * (2.0 ** ((pitch - 69.0) / 12.0))


def _biquad_response(b, a, w: np.ndarray) -> np.ndarray:
    z1 = np.exp(-1j * w)
    z2 = z1 * z1
    return (b[0] + b[1] * z1 + b[2] * z2) / (a[0] + a[1] * z1 + a[2] * z2)


def _k_weighting_response(n_fft: int, sr: int) -> np.ndarray:
    """Respuesta en frecuencia del filtro K (ITU-R BS.1770-4) para cualquier sample rate.

    Etapa 1: shelf de agudos +4 dB (efecto de la cabeza). Etapa 2: paso alto RLB a 38 Hz.
    Coeficientes derivados analiticamente (a 48 kHz coinciden con los de la norma).
    """
    w = 2.0 * np.pi * np.fft.rfftfreq(n_fft, 1.0 / sr) / sr
    # Shelf de agudos (forma de Brecht De Man)
    gain_db, q, fc = 3.999843853973347, 0.7071752369554196, 1681.974450955533
    k = np.tan(np.pi * fc / sr)
    vh = 10.0 ** (gain_db / 20.0)
    vb = vh ** 0.4996667741545416
    a0 = 1.0 + k / q + k * k
    shelf = _biquad_response(
        (vh + vb * k / q + k * k, 2.0 * (k * k - vh), vh - vb * k / q + k * k),
        (a0, 2.0 * (k * k - 1.0), 1.0 - k / q + k * k),
        w,
    )
    # Paso alto RLB
    q, fc = 0.5003270373238773, 38.13547087602444
    k = np.tan(np.pi * fc / sr)
    highpass = _biquad_response(
        (1.0, -2.0, 1.0),
        (1.0 + k / q + k * k, 2.0 * (k * k - 1.0), 1.0 - k / q + k * k),
        w,
    )
    return shelf * highpass


def _k_weighting_filter(signal: np.ndarray, sr: int) -> np.ndarray:
    """Filtro K-weighting (ITU-R BS.1770) aplicado en frecuencia, por canal."""
    n = signal.shape[0]
    if n == 0:
        return signal
    response = _k_weighting_response(n, sr)
    spec = np.fft.rfft(signal, axis=0)
    return np.fft.irfft(spec * response[:, None], n=n, axis=0)


def _integrated_lufs(filtered: np.ndarray, sr: int) -> float:
    """Sonoridad integrada BS.1770: bloques de 400 ms (75% solape), puerta absoluta -70 y relativa -10."""
    block, hop = int(0.4 * sr), int(0.1 * sr)
    power = np.sum(filtered ** 2, axis=1)  # canales L+R con peso 1.0
    if len(power) < block:
        z = np.array([np.mean(power)]) if len(power) else np.array([0.0])
    else:
        csum = np.concatenate(([0.0], np.cumsum(power)))
        starts = np.arange(0, len(power) - block + 1, hop)
        z = (csum[starts + block] - csum[starts]) / block
    loud = -0.691 + 10.0 * np.log10(np.maximum(z, 1e-12))
    gated = z[loud > -70.0]
    if gated.size == 0:
        return -70.0
    relative = -0.691 + 10.0 * np.log10(np.mean(gated)) - 10.0
    gated = z[(loud > -70.0) & (loud > relative)]
    return float(-0.691 + 10.0 * np.log10(max(float(np.mean(gated)), 1e-12)))


def calculate_loudness_stats(stereo_audio: np.ndarray, sr: int) -> AudioMetrics:
    """Calcula metricas acusticas profesionales (Peak, RMS, LUFS estimado)."""
    peak = float(np.max(np.abs(stereo_audio)))
    peak_dbfs = 20.0 * math.log10(max(peak, 1e-9))
    
    mean_sq = float(np.mean(stereo_audio ** 2))
    rms_dbfs = 10.0 * math.log10(max(mean_sq, 1e-9))
    
    # Sonoridad integrada ITU-R BS.1770 (la que miden YouTube, Spotify, Apple Music...)
    estimated_lufs = _integrated_lufs(_k_weighting_filter(stereo_audio, sr), sr)
    
    clipped = int(np.sum(np.abs(stereo_audio) >= 0.9999))
    dur = float(stereo_audio.shape[0]) / sr
    
    return AudioMetrics(
        duration_sec=dur,
        sample_rate=sr,
        peak_dbfs=peak_dbfs,
        rms_dbfs=rms_dbfs,
        estimated_lufs=estimated_lufs,
        clipped_samples=clipped,
    )


def _render_pad_chord(
    pitch: int,
    vel: int,
    dur: float,
    sr: int,
) -> Tuple[np.ndarray, np.ndarray]:
    """Sintetiza un timbre calido tipo Pad/Strings (SuperSaw suave + Triangle) en estereo."""
    n_samples = int(sr * (dur + 0.5))
    t = np.linspace(0, (dur + 0.5), n_samples, endpoint=False)
    freq = _midi_to_freq(pitch)
    
    # 3 Osciladores desafinados con fase aleatoria para apertura estereo
    detune = 0.004
    f_l = freq * (1.0 - detune)
    f_r = freq * (1.0 + detune)
    
    # Sawtooth y seno armonico
    osc_l = 0.5 * (2.0 * (t * f_l - np.floor(t * f_l + 0.5))) + 0.5 * np.sin(2 * np.pi * freq * t)
    osc_r = 0.5 * (2.0 * (t * f_r - np.floor(t * f_r + 0.5))) + 0.5 * np.sin(2 * np.pi * freq * t)
    
    # Sub-octava para profundidad
    sub = 0.3 * np.sin(2 * np.pi * (freq * 0.5) * t)
    left = osc_l + sub
    right = osc_r + sub
    
    # Envolvente ADSR suave
    attack_s = 0.12
    release_s = 0.35
    env = np.ones(n_samples, dtype=np.float32)
    
    att_samples = int(attack_s * sr)
    if att_samples > 0:
        env[:att_samples] = np.linspace(0.0, 1.0, att_samples)
        
    sustain_samples = int(dur * sr)
    rel_samples = n_samples - sustain_samples
    if rel_samples > 0 and sustain_samples < n_samples:
        env[sustain_samples:] = np.linspace(1.0, 0.0, rel_samples) ** 1.5
        
    scale = (vel / 127.0) * 0.15
    out_l = left * env * scale
    out_r = right * env * scale
    
    # Si es registro bajo de acordes / guitarras (pitch < 53), añadir distorsion armonica de amplificador
    if pitch < 53:
        out_l = np.tanh(2.4 * out_l) * 1.15
        out_r = np.tanh(2.4 * out_r) * 1.15
        
    return out_l.astype(np.float32), out_r.astype(np.float32)


def _render_pluck_lead(
    pitch: int,
    vel: int,
    dur: float,
    sr: int,
) -> Tuple[np.ndarray, np.ndarray]:
    """Sintetiza un timbre brillante de Lead / Pluck con decay exponencial."""
    decay_sec = min(dur, 0.45)
    n_samples = int(sr * (decay_sec + 0.2))
    t = np.linspace(0, (decay_sec + 0.2), n_samples, endpoint=False)
    freq = _midi_to_freq(pitch)
    
    # Pulso brillante + diente de sierra
    osc = 0.6 * np.sign(np.sin(2 * np.pi * freq * t)) + 0.4 * (2.0 * (t * freq - np.floor(t * freq + 0.5)))
    
    # Envolvente percusiva rapida
    env = np.exp(-t * (8.0 / (decay_sec + 0.05)))
    sig = osc * env * (vel / 127.0) * 0.18
    
    # Ligero delay estereo (ping-pong)
    delay_samples = int(sr * 0.08)
    left = np.copy(sig)
    right = np.zeros_like(sig)
    if delay_samples < n_samples:
        right[delay_samples:] = sig[:-delay_samples] * 0.45
    return left.astype(np.float32), right.astype(np.float32)


def _render_synth_bass(
    pitch: int,
    vel: int,
    dur: float,
    sr: int,
) -> np.ndarray:
    """Sintetiza un bajo solido centrado (mono) con saturacion analogica suave."""
    n_samples = int(sr * (dur + 0.1))
    t = np.linspace(0, (dur + 0.1), n_samples, endpoint=False)
    freq = _midi_to_freq(pitch)
    
    # Onda fundamental seno + segunda armonica saturada
    if pitch <= 44:
        # 808 Sub Bass con pitch punch al inicio y saturacion para altavoces pequeños
        inst_f = freq + (35.0 * np.exp(-t * 32.0))
        phase = 2.0 * np.pi * np.cumsum(inst_f) / sr
        raw = np.sin(phase) + 0.35 * np.sin(phase * 2)
        dist = np.tanh(2.2 * raw) * 1.2
    else:
        fund = np.sin(2 * np.pi * freq * t)
        harm = 0.4 * np.sin(2 * np.pi * (freq * 2) * t)
        raw = fund + harm
        dist = np.tanh(1.5 * raw)
    
    # Envolvente
    env = np.ones(n_samples, dtype=np.float32)
    att_samples = int(0.008 * sr)
    env[:att_samples] = np.linspace(0.0, 1.0, att_samples)
    rel_samples = int(0.08 * sr)
    if rel_samples > 0:
        env[-rel_samples:] = np.linspace(1.0, 0.0, rel_samples)
        
    return (dist * env * (vel / 127.0) * 0.28).astype(np.float32)


def _render_drum_hit(pitch: int, vel: int, sr: int) -> Tuple[np.ndarray, np.ndarray]:
    """Genera bombos, cajas y charles mediante sintesis acustica procedural pura (sin samples)."""
    vel_scale = (vel / 127.0)
    
    if pitch == 36:  # Kick Drum (Barrido de tono 140 Hz -> 42 Hz)
        n_samples = int(sr * 0.22)
        t = np.linspace(0, 0.22, n_samples, endpoint=False)
        # Caida de frecuencia exponencial
        inst_freq = 42.0 + (120.0 * np.exp(-t * 28.0))
        phase = 2.0 * np.pi * np.cumsum(inst_freq) / sr
        body = np.sin(phase) * np.exp(-t * 18.0)
        kick = np.tanh(1.8 * body) * vel_scale * 0.45
        return kick.astype(np.float32), kick.astype(np.float32)
        
    elif pitch == 38:  # Snare Drum (Cuerpo tonal 180 Hz + Ruido blanco filtrado)
        n_samples = int(sr * 0.20)
        t = np.linspace(0, 0.20, n_samples, endpoint=False)
        # Tono de la membrana
        tone = np.sin(2 * np.pi * 185.0 * t) * np.exp(-t * 26.0)
        # Bordonera (ruido)
        noise = (np.random.uniform(-1.0, 1.0, n_samples) * np.exp(-t * 16.0))
        snare = (0.45 * tone + 0.55 * noise) * vel_scale * 0.38
        return snare.astype(np.float32), snare.astype(np.float32)
        
    elif pitch in (42, 46):  # Hi-Hats (Closed=42, Open=46)
        dur = 0.05 if pitch == 42 else 0.25
        n_samples = int(sr * dur)
        t = np.linspace(0, dur, n_samples, endpoint=False)
        noise = np.random.uniform(-1.0, 1.0, n_samples)
        # Filtro pasa altos rudimentario (diferenciacion)
        hp_noise = np.diff(noise, prepend=0.0)
        decay_rate = 55.0 if pitch == 42 else 14.0
        hat = hp_noise * np.exp(-t * decay_rate) * vel_scale * (0.16 if pitch == 42 else 0.22)
        # Apertura espacial sutil
        return (hat * 0.9).astype(np.float32), (hat * 1.1).astype(np.float32)
        
    elif pitch == 49:  # Crash Cymbal (Platillo Rock brillante)
        dur = 0.85
        n_samples = int(sr * dur)
        t = np.linspace(0, dur, n_samples, endpoint=False)
        noise = np.random.uniform(-1.0, 1.0, n_samples)
        hp_noise = np.diff(noise, prepend=0.0)
        crash = hp_noise * np.exp(-t * 4.2) * vel_scale * 0.26
        return (crash * 0.85).astype(np.float32), (crash * 1.15).astype(np.float32)
        
    elif pitch == 51:  # Ride Cymbal (swing / big band): ruido brillante + campana metalica
        dur = 0.45
        n_samples = int(sr * dur)
        t = np.linspace(0, dur, n_samples, endpoint=False)
        noise = np.diff(np.random.uniform(-1.0, 1.0, n_samples), prepend=0.0)
        bell = np.sin(2 * np.pi * 3150.0 * t) * 0.25 + np.sin(2 * np.pi * 4720.0 * t) * 0.15
        ride = (0.7 * noise + bell) * np.exp(-t * 9.0) * vel_scale * 0.12
        return (ride * 1.1).astype(np.float32), (ride * 0.9).astype(np.float32)

    elif pitch in (56, 75, 76, 77):  # Cowbell, Claves, Wood Blocks (percusion "graciosa")
        tones = {56: (562.0, 845.0, 0.09, 30.0), 75: (2500.0, 0.0, 0.05, 70.0),
                 76: (1250.0, 0.0, 0.06, 55.0), 77: (880.0, 0.0, 0.07, 50.0)}
        f1, f2, dur, decay = tones[pitch]
        n_samples = int(sr * dur)
        t = np.linspace(0, dur, n_samples, endpoint=False)
        body = np.sin(2 * np.pi * f1 * t)
        if f2:
            body = 0.6 * np.sign(body) + 0.6 * np.sign(np.sin(2 * np.pi * f2 * t))
        hit = body * np.exp(-t * decay) * vel_scale * 0.16
        pan = 0.8 if pitch in (76, 56) else 1.2
        return (hit * pan).astype(np.float32), (hit * (2.0 - pan)).astype(np.float32)

    elif pitch == 54:  # Tambourine: ruido agudo con jingles
        dur = 0.18
        n_samples = int(sr * dur)
        t = np.linspace(0, dur, n_samples, endpoint=False)
        noise = np.diff(np.random.uniform(-1.0, 1.0, n_samples), prepend=0.0)
        jingle = noise * (1.0 + 0.5 * np.sin(2 * np.pi * 38.0 * t)) * np.exp(-t * 22.0)
        tamb = jingle * vel_scale * 0.11
        return (tamb * 0.85).astype(np.float32), (tamb * 1.15).astype(np.float32)

    # Default hit generico
    n_samples = int(sr * 0.05)
    click = np.random.uniform(-0.1, 0.1, n_samples).astype(np.float32)
    return click, click


def _mix_event(
    event: NoteEvent,
    master_l: np.ndarray,
    master_r: np.ndarray,
    sr: int,
    instruments: Optional[Dict[str, str]] = None,
    gains: Optional[Dict[str, float]] = None,
) -> None:
    start_idx = max(0, int(event.start_sec * sr))
    if start_idx >= len(master_l) or event.duration_sec <= 0:
        return
        
    if instruments is not None:
        # Rack de instrumentos elegido por el usuario o sugerido por el timbre de las fuentes
        from .instruments import TRACK_ROLE, render_note

        role = TRACK_ROLE.get(event.track_name)
        if role is None:
            return
        sig_l, sig_r = render_note(instruments[role], event.track_name, event.pitch, event.velocity, event.duration_sec, sr)
    elif event.track_name == "chords":
        sig_l, sig_r = _render_pad_chord(event.pitch, event.velocity, event.duration_sec, sr)
    elif event.track_name == "melody":
        sig_l, sig_r = _render_pluck_lead(event.pitch, event.velocity, event.duration_sec, sr)
    elif event.track_name == "bass":
        bass_mono = _render_synth_bass(event.pitch, event.velocity, event.duration_sec, sr)
        sig_l, sig_r = bass_mono, bass_mono
    elif event.track_name == "drums":
        sig_l, sig_r = _render_drum_hit(event.pitch, event.velocity, sr)
    else:
        return
        
    if gains:
        from .instruments import TRACK_ROLE

        gain = gains.get(TRACK_ROLE.get(event.track_name, ""), 1.0)
        if gain <= 0.0:
            return
        sig_l, sig_r = sig_l * gain, sig_r * gain

    end_idx = min(start_idx + len(sig_l), len(master_l))
    length = end_idx - start_idx
    if length > 0:
        master_l[start_idx:end_idx] += sig_l[:length]
        master_r[start_idx:end_idx] += sig_r[:length]


def _soft_limit(scaled: np.ndarray, ceiling: float) -> np.ndarray:
    """Limitador suave analogico (Soft Knee Limiter con tanh)."""
    knee_threshold = ceiling * 0.85
    output = np.zeros_like(scaled)
    for ch in range(2):
        sig = scaled[:, ch]
        abs_sig = np.abs(sig)
        signs = np.sign(sig)
        
        # Region lineal vs region saturada
        is_high = abs_sig > knee_threshold
        saturated = knee_threshold + (ceiling - knee_threshold) * np.tanh(
            (abs_sig - knee_threshold) / max((ceiling - knee_threshold), 1e-6)
        )
        
        output[:, ch] = np.where(is_high, saturated * signs, sig)
    return output


def _master_to_target_lufs(
    audio: np.ndarray,
    sr: int,
    target_lufs: float = -14.0,
    max_peak_dbfs: float = -1.0,
) -> np.ndarray:
    """Aplica ganancia automatica y limitador suave para cumplir con los estandares de Content ID."""
    current_metrics = calculate_loudness_stats(audio, sr)
    
    # Calcular diferencia de ganancia para alcanzar target LUFS
    gain_db = target_lufs - current_metrics.estimated_lufs
    # Limitar el impulso de ganancia a un rango prudente
    gain_db = max(-12.0, min(gain_db, 18.0))
    linear_gain = 10.0 ** (gain_db / 20.0)
    
    # El limitador recorta picos y baja la sonoridad real: se re-mide y se compensa
    # la ganancia hasta 4 veces para aterrizar en el objetivo sin pasar el techo.
    ceiling = 10.0 ** (max_peak_dbfs / 20.0)  # Ej. 0.891 (-1.0 dBFS)
    output = _soft_limit(audio * linear_gain, ceiling)
    for _ in range(4):
        deficit_db = target_lufs - calculate_loudness_stats(output, sr).estimated_lufs
        if abs(deficit_db) < 0.25 or gain_db >= 24.0:
            break
        gain_db = min(gain_db + deficit_db, 24.0)
        linear_gain = 10.0 ** (gain_db / 20.0)
        output = _soft_limit(audio * linear_gain, ceiling)

    # Corte estricto de seguridad true-peak
    np.clip(output, -ceiling, ceiling, out=output)
    return output


def render_midi_to_wav(
    bundle: MidiTrackBundle,
    output_wav_path: str,
    config: SynthConfig = SynthConfig(),
    instruments: Optional[Dict[str, str]] = None,
    gains: Optional[Dict[str, float]] = None,
) -> AudioMetrics:
    """Sintetiza la pista generada a un archivo WAV estereo masterizado a -14 LUFS.

    instruments: rack {rol: id} de motor_musica.instruments. Sin rack se usan los
    timbres clasicos del motor.
    gains: volumen por rol {lead|pad|bass|drums: 0.0-2.0} (0 = silenciado), antes del master.
    """
    if instruments is not None:
        from .instruments import resolve_rack

        instruments = resolve_rack(instruments)
    sr = config.sample_rate
    total_samples = int((bundle.duration_sec + config.tail_sec) * sr)
    
    master_l = np.zeros(total_samples, dtype=np.float32)
    master_r = np.zeros(total_samples, dtype=np.float32)
    
    # Mezclar cada evento procedural
    for ev in bundle.events:
        _mix_event(ev, master_l, master_r, sr, instruments, gains)
        
    raw_stereo = np.column_stack([master_l, master_r])
    
    # Masterizar a -14 LUFS con limitador suave
    mastered = _master_to_target_lufs(raw_stereo, sr, target_lufs=config.target_lufs)
    
    # Exportar archivo WAV PCM de alta fidelidad
    if config.bit_depth == 24:
        # 24-bit PCM
        scaled = (mastered * 8388607.0).astype(np.int32)
        # Empacar 3 bytes por muestra
        raw_bytes = bytearray()
        for i in range(len(scaled)):
            l_val = int(scaled[i, 0])
            r_val = int(scaled[i, 1])
            raw_bytes.extend(l_val.to_bytes(3, byteorder="little", signed=True))
            raw_bytes.extend(r_val.to_bytes(3, byteorder="little", signed=True))
            
        with wave.open(output_wav_path, "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(3)
            wf.setframerate(sr)
            wf.writeframes(raw_bytes)
    else:
        # 16-bit PCM (estándar CD / YouTube)
        scaled = (mastered * 32767.0).astype(np.int16)
        with wave.open(output_wav_path, "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(scaled.tobytes())
            
    final_metrics = calculate_loudness_stats(mastered, sr)
    return final_metrics
