"""Rack de Instrumentos Procedurales (100% sintesis NumPy, cero samples).

Cada instrumento es una "receta" matematica que convierte (nota, velocidad, duracion)
en audio estereo. Hay cuatro roles, que coinciden con los canales MIDI del proyecto:

- lead  -> Canal 1 (melodia)
- pad   -> Canal 0 (acordes / armonia)
- bass  -> Canal 2 (bajo)
- drums -> Canal 9 (bateria GM)

Cada instrumento declara tambien su programa General MIDI y el plugin sugerido de
FL Studio, para que el paquete editable abra con sonidos equivalentes.

`suggest_instruments` elige un instrumento por rol a partir del timbre medido en los
temas de YouTube (brillo, peso de graves, percusividad), el tempo y el modo.
"""

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

Stereo = Tuple[np.ndarray, np.ndarray]
ROLES = ("lead", "pad", "bass", "drums")
TRACK_ROLE = {"melody": "lead", "chords": "pad", "bass": "bass", "drums": "drums"}
DEFAULT_RACK = {"lead": "saw_lead", "pad": "warm_pad", "bass": "synth_bass", "drums": "acoustic_kit"}
# Nivel de pico por rol: mantiene el balance de mezcla antes del master a -14 LUFS
ROLE_LEVEL = {"lead": 0.17, "pad": 0.11, "bass": 0.27, "drums": 0.38}


@dataclass(frozen=True)
class Instrument:
    id: str
    name: str
    role: str
    gm_program: int
    fl_plugin: str
    description: str
    render: Callable[..., Stereo]


def _midi_to_freq(pitch: float) -> float:
    return 440.0 * (2.0 ** ((pitch - 69.0) / 12.0))


def _time(dur: float, sr: int) -> np.ndarray:
    return np.arange(max(1, int(dur * sr)), dtype=np.float64) / sr


def _adsr(n: int, sr: int, a: float, d: float, s: float, r: float, hold: float) -> np.ndarray:
    """Envolvente ADSR: hold = segundos que la nota esta presionada; el release va despues."""
    t = np.arange(n) / sr
    env = np.empty(n)
    a = max(a, 1e-4)
    att = t < a
    env[att] = t[att] / a
    dec = (t >= a) & (t < a + d)
    env[dec] = 1.0 - (1.0 - s) * (t[dec] - a) / max(d, 1e-4)
    env[t >= a + d] = s
    rel = t >= hold
    if np.any(rel):
        start_level = env[np.argmax(rel)] if np.any(~rel) else s
        env[rel] = start_level * np.maximum(0.0, 1.0 - (t[rel] - hold) / max(r, 1e-4))
    return env


def _additive(freq: float, t: np.ndarray, sr: int, cutoff: np.ndarray, resonance: float = 0.0,
              odd_only: bool = False, slope: float = 1.0, max_harm: int = 48) -> np.ndarray:
    """Sintesis aditiva con filtro paso bajo variable en el tiempo (y pico de resonancia).

    Equivale a una onda de sierra (o cuadrada con odd_only) pasada por un filtro analogico,
    pero sin bucles por muestra: cada armonico se pondera por la respuesta del filtro.
    """
    n_harm = int(min(max_harm, (sr * 0.45) // max(freq, 1.0)))
    out = np.zeros_like(t)
    phase = 2.0 * np.pi * freq * t
    for k in range(1, n_harm + 1):
        if odd_only and k % 2 == 0:
            continue
        hf = k * freq
        x = hf / np.maximum(cutoff, 20.0)
        gain = 1.0 / (1.0 + x ** 4)
        if resonance:
            gain = gain + resonance * np.exp(-((x - 1.0) ** 2) / 0.02)
        out += (1.0 / k ** slope) * gain * np.sin(k * phase)
    return out


def _fft_lowpass(sig: np.ndarray, sr: int, cutoff: float) -> np.ndarray:
    """Paso bajo de 24 dB/oct aplicado en frecuencia (rapido para notas sueltas)."""
    spec = np.fft.rfft(sig)
    freqs = np.fft.rfftfreq(len(sig), 1.0 / sr)
    return np.fft.irfft(spec / (1.0 + (freqs / cutoff) ** 4), len(sig))


def _karplus_strong(freq: float, dur: float, sr: int, brightness: float = 0.5, decay: float = 0.996) -> np.ndarray:
    """Cuerda pulsada (Karplus-Strong) vectorizada por bloques de un periodo."""
    period = max(2, int(round(sr / freq)))
    n = int(dur * sr)
    rng = np.random.default_rng(int(freq * 1000) % (2 ** 32))
    block = rng.uniform(-1.0, 1.0, period)
    # Excitacion suavizada = cuerda menos brillante
    if brightness < 1.0:
        k = max(1, int((1.0 - brightness) * 6))
        block = np.convolve(block, np.ones(k) / k, mode="same")
    blocks = [block]
    total = period
    while total < n:
        prev = blocks[-1]
        nxt = decay * 0.5 * (prev + np.roll(prev, 1))
        blocks.append(nxt)
        total += period
    return np.concatenate(blocks)[:n]


def _norm(sig: np.ndarray, level: float, vel: int) -> np.ndarray:
    peak = float(np.max(np.abs(sig))) if sig.size else 0.0
    if peak < 1e-9:
        return sig.astype(np.float32)
    return (sig / peak * level * (vel / 127.0)).astype(np.float32)


def _stereo(sig: np.ndarray, width_samples: int = 0, pan: float = 0.0) -> Stereo:
    left = sig * (1.0 - max(pan, 0.0))
    right = sig * (1.0 + min(pan, 0.0))
    if width_samples:
        right = np.concatenate([np.zeros(width_samples, dtype=sig.dtype), right[:-width_samples]])
    return left.astype(np.float32), right.astype(np.float32)


# ---------------------------------------------------------------------------
# LEADS (Canal 1)
# ---------------------------------------------------------------------------

def _nes_pulse(pitch: int, vel: int, dur: float, sr: int) -> Stereo:
    """Onda de pulso 25% estilo 2A03 (NES) con vibrato tardio, como las melodias 8-bit."""
    t = _time(dur + 0.08, sr)
    f = _midi_to_freq(pitch)
    vib = 1.0 + 0.006 * np.sin(2 * np.pi * 5.5 * t) * np.clip((t - 0.18) / 0.2, 0.0, 1.0)
    phase = np.cumsum(f * vib) / sr
    pulse = np.where((phase % 1.0) < 0.25, 1.0, -0.33)
    # Cuantizacion a 4 bits de volumen, como el chip original
    env = np.round(_adsr(len(t), sr, 0.005, 0.12, 0.7, 0.06, dur) * 15.0) / 15.0
    return _stereo(_norm(pulse * env, ROLE_LEVEL["lead"], vel), int(sr * 0.012))


def _saw_lead(pitch: int, vel: int, dur: float, sr: int) -> Stereo:
    """Sierra con filtro que se abre y cierra (lead clasico de sintetizador sustractivo)."""
    t = _time(dur + 0.2, sr)
    f = _midi_to_freq(pitch)
    cutoff = f * (2.0 + 6.0 * np.exp(-t * 7.0))
    sig = _additive(f * 0.997, t, sr, cutoff, resonance=0.3, max_harm=24) + _additive(f * 1.003, t, sr, cutoff, resonance=0.3, max_harm=24)
    env = _adsr(len(t), sr, 0.01, 0.2, 0.75, 0.15, dur)
    return _stereo(_norm(sig * env, ROLE_LEVEL["lead"], vel), int(sr * 0.08))


def _fm_bell(pitch: int, vel: int, dur: float, sr: int) -> Stereo:
    """Campana / celesta FM de 2 operadores (cajita de musica, toque 'macabro tierno')."""
    tail = max(dur, 0.6) + 0.4
    t = _time(tail, sr)
    f = _midi_to_freq(pitch)
    index = 4.0 * np.exp(-t * 6.0) + 0.4
    sig = np.sin(2 * np.pi * f * t + index * np.sin(2 * np.pi * f * 3.5 * t))
    env = np.exp(-t * 3.2) * np.minimum(1.0, t / 0.002)
    return _stereo(_norm(sig * env, ROLE_LEVEL["lead"], vel), int(sr * 0.015), pan=0.1)


def _pizzicato(pitch: int, vel: int, dur: float, sr: int) -> Stereo:
    """Cuerdas en pizzicato (Karplus-Strong): el guino a Danny Elfman."""
    f = _midi_to_freq(pitch)
    sig = _karplus_strong(f, min(dur, 0.5) + 0.25, sr, brightness=0.55, decay=0.993)
    return _stereo(_norm(sig, ROLE_LEVEL["lead"], vel), int(sr * 0.006))


def _flute(pitch: int, vel: int, dur: float, sr: int) -> Stereo:
    """Flauta: seno + armonicos suaves + soplido filtrado y vibrato."""
    t = _time(dur + 0.12, sr)
    f = _midi_to_freq(pitch)
    vib = 1.0 + 0.004 * np.sin(2 * np.pi * 5.0 * t)
    phase = 2.0 * np.pi * np.cumsum(f * vib) / sr
    tone = np.sin(phase) + 0.25 * np.sin(2 * phase) + 0.08 * np.sin(3 * phase)
    rng = np.random.default_rng(pitch)
    breath = np.convolve(rng.uniform(-1, 1, len(t)), np.ones(8) / 8, mode="same") * 0.12
    env = _adsr(len(t), sr, 0.06, 0.1, 0.85, 0.1, dur)
    return _stereo(_norm((tone + breath) * env, ROLE_LEVEL["lead"], vel), int(sr * 0.02))


# ---------------------------------------------------------------------------
# PADS / ARMONIA (Canal 0)
# ---------------------------------------------------------------------------

def _warm_pad(pitch: int, vel: int, dur: float, sr: int) -> Stereo:
    """Pad calido: dos sierras desafinadas + seno, ataque lento (sonido clasico del motor)."""
    t = _time(dur + 0.5, sr)
    f = _midi_to_freq(pitch)
    saw_l = 2.0 * (t * f * 0.996 - np.floor(t * f * 0.996 + 0.5))
    saw_r = 2.0 * (t * f * 1.004 - np.floor(t * f * 1.004 + 0.5))
    sine = np.sin(2 * np.pi * f * t)
    env = _adsr(len(t), sr, 0.12, 0.2, 0.9, 0.35, dur)
    left = _norm((0.5 * saw_l + 0.5 * sine) * env, ROLE_LEVEL["pad"], vel)
    right = _norm((0.5 * saw_r + 0.5 * sine) * env, ROLE_LEVEL["pad"], vel)
    return left, right


def _gothic_organ(pitch: int, vel: int, dur: float, sr: int) -> Stereo:
    """Organo de iglesia por registros (16', 8', 4', 2 2/3', 2') con tremolo de Leslie."""
    t = _time(dur + 0.15, sr)
    f = _midi_to_freq(pitch)
    drawbars = [(0.5, 0.6), (1.0, 1.0), (2.0, 0.7), (3.0, 0.45), (4.0, 0.35), (8.0, 0.15)]
    sig = sum(a * np.sin(2 * np.pi * f * m * t) for m, a in drawbars)
    trem = 1.0 + 0.12 * np.sin(2 * np.pi * 6.2 * t)
    env = _adsr(len(t), sr, 0.02, 0.0, 1.0, 0.12, dur)
    left = _norm(sig * env * trem, ROLE_LEVEL["pad"], vel)
    right = _norm(sig * env * (2.0 - trem), ROLE_LEVEL["pad"], vel)
    return left, right


def _string_ensemble(pitch: int, vel: int, dur: float, sr: int) -> Stereo:
    """Seccion de cuerdas: 4 sierras desafinadas con filtro y ataque de arco."""
    t = _time(dur + 0.4, sr)
    f = _midi_to_freq(pitch)
    voices = [2.0 * ((t + i * 0.003) * f * d % 1.0) - 1.0 for i, d in enumerate((0.994, 0.998, 1.002, 1.006))]
    env = _adsr(len(t), sr, 0.25, 0.1, 0.9, 0.35, dur)
    left = _norm(_fft_lowpass(voices[0] + voices[2], sr, f * 5.0) * env, ROLE_LEVEL["pad"], vel)
    right = _norm(_fft_lowpass(voices[1] + voices[3], sr, f * 5.0) * env, ROLE_LEVEL["pad"], vel)
    return left, right


def _choir(pitch: int, vel: int, dur: float, sr: int) -> Stereo:
    """Coro 'aah': armonicos ponderados por los formantes de la vocal A (700/1220/2600 Hz)."""
    t = _time(dur + 0.4, sr)
    f = _midi_to_freq(pitch)
    vib = 1.0 + 0.005 * np.sin(2 * np.pi * 4.8 * t)
    phase = 2.0 * np.pi * np.cumsum(f * vib) / sr
    sig = np.zeros_like(t)
    for k in range(1, int(min(40, 4000 // f)) + 1):
        hf = k * f
        formant = sum(a * np.exp(-((hf - c) / bw) ** 2) for c, bw, a in ((700, 130, 1.0), (1220, 150, 0.5), (2600, 250, 0.25)))
        sig += (formant + 0.02) * np.sin(k * phase)
    env = _adsr(len(t), sr, 0.2, 0.1, 0.9, 0.3, dur)
    return _stereo(_norm(sig * env, ROLE_LEVEL["pad"], vel), int(sr * 0.018))


# ---------------------------------------------------------------------------
# BAJOS (Canal 2)
# ---------------------------------------------------------------------------

def _synth_bass(pitch: int, vel: int, dur: float, sr: int) -> Stereo:
    """Bajo sintetizado: seno + 2o armonico con saturacion suave."""
    t = _time(dur + 0.1, sr)
    f = _midi_to_freq(pitch)
    sig = np.tanh(1.5 * (np.sin(2 * np.pi * f * t) + 0.4 * np.sin(4 * np.pi * f * t)))
    env = _adsr(len(t), sr, 0.008, 0.0, 1.0, 0.08, dur)
    mono = _norm(sig * env, ROLE_LEVEL["bass"], vel)
    return mono, mono


def _sub_808(pitch: int, vel: int, dur: float, sr: int) -> Stereo:
    """808: seno con golpe de tono inicial, cola larga y saturacion para parlantes chicos."""
    t = _time(max(dur, 0.4) + 0.15, sr)
    f = _midi_to_freq(min(pitch, 45))
    inst = f + 45.0 * np.exp(-t * 30.0)
    phase = 2.0 * np.pi * np.cumsum(inst) / sr
    sig = np.tanh(2.2 * (np.sin(phase) + 0.3 * np.sin(2 * phase)))
    env = np.minimum(1.0, t / 0.003) * np.exp(-t * 1.2)
    env[t > dur + 0.05] *= np.exp(-(t[t > dur + 0.05] - dur - 0.05) * 25.0)
    mono = _norm(sig * env, ROLE_LEVEL["bass"], vel)
    return mono, mono


def _upright_pluck(pitch: int, vel: int, dur: float, sr: int) -> Stereo:
    """Contrabajo pulsado (Karplus-Strong grave) para walking bass de swing/jazz."""
    f = _midi_to_freq(pitch)
    sig = _karplus_strong(f, dur + 0.15, sr, brightness=0.25, decay=0.997)
    t = np.arange(len(sig)) / sr
    sig = sig + 0.4 * np.sin(2 * np.pi * f * t) * np.exp(-t * 3.0)  # cuerpo de la caja
    mono = _norm(sig, ROLE_LEVEL["bass"], vel)
    return mono, mono


def _tuba(pitch: int, vel: int, dur: float, sr: int) -> Stereo:
    """Tuba / bronce grave: el brillo sigue a la envolvente (soplido que abre el sonido)."""
    t = _time(dur + 0.1, sr)
    f = _midi_to_freq(pitch)
    env = _adsr(len(t), sr, 0.04, 0.15, 0.8, 0.08, dur)
    cutoff = f * (1.5 + 4.0 * env)
    sig = _additive(f, t, sr, cutoff, max_harm=20)
    mono = _norm(sig * env, ROLE_LEVEL["bass"], vel)
    return mono, mono


def _acid_303(pitch: int, vel: int, dur: float, sr: int) -> Stereo:
    """Bajo acido: sierra con filtro resonante que barre hacia abajo en cada nota."""
    t = _time(dur + 0.05, sr)
    f = _midi_to_freq(pitch)
    accent = vel / 127.0
    cutoff = f * (1.2 + 10.0 * accent * np.exp(-t * 14.0))
    sig = np.tanh(1.4 * _additive(f, t, sr, cutoff, resonance=1.6, max_harm=32))
    env = _adsr(len(t), sr, 0.003, 0.0, 1.0, 0.03, dur)
    mono = _norm(sig * env, ROLE_LEVEL["bass"], vel)
    return mono, mono


# ---------------------------------------------------------------------------
# KITS DE BATERIA (Canal 9, notas GM)
# ---------------------------------------------------------------------------

def _acoustic_kit(pitch: int, vel: int, dur: float, sr: int) -> Stereo:
    """Kit acustico procedural del motor (bombo, caja, platos, ride, wood blocks...)."""
    from .synth_renderer import _render_drum_hit

    return _render_drum_hit(pitch, vel, sr)


def _lfsr_noise(n: int, short: bool, seed: int = 1) -> np.ndarray:
    """Ruido del chip NES: registro de desplazamiento de 15 bits (modo corto = metalico)."""
    reg = seed or 1
    tap = 6 if short else 1
    period = 93 if short else 32767
    seq = np.empty(min(n, period), dtype=np.float64)
    for i in range(len(seq)):
        bit = (reg ^ (reg >> tap)) & 1
        reg = (reg >> 1) | (bit << 14)
        seq[i] = 1.0 if reg & 1 else -1.0
    return np.resize(seq, n)


def _chip_kit(pitch: int, vel: int, dur: float, sr: int) -> Stereo:
    """Bateria 8-bit: bombo de triangulo con caida de tono y cajas/platos de ruido LFSR."""
    step = max(1, sr // 11025)  # el chip corre a baja resolucion: se 'pixela' el ruido
    if pitch in (35, 36):
        t = _time(0.18, sr)
        f = 40.0 + 180.0 * np.exp(-t * 35.0)
        phase = np.cumsum(f) / sr
        tri = 2.0 * np.abs(2.0 * (phase % 1.0) - 1.0) - 1.0
        sig = np.round(tri * 7) / 7 * np.exp(-t * 14.0)
    elif pitch in (38, 39, 40):
        t = _time(0.16, sr)
        noise = np.repeat(_lfsr_noise(len(t) // step + 1, short=False), step)[:len(t)]
        sig = noise * np.exp(-t * 22.0)
    elif pitch in (42, 44, 46, 49, 51, 57):
        length = 0.04 if pitch in (42, 44) else 0.25
        t = _time(length, sr)
        noise = np.repeat(_lfsr_noise(len(t) // step + 1, short=True), step)[:len(t)]
        sig = noise * np.exp(-t * (60.0 if pitch in (42, 44) else 9.0)) * 0.6
    else:
        # Wood block / cencerro / claves -> 'blip' de pulso agudo
        t = _time(0.06, sr)
        f = {56: 1100.0, 75: 2200.0, 76: 1600.0, 77: 1250.0}.get(pitch, 900.0)
        sig = np.where((t * f) % 1.0 < 0.5, 1.0, -1.0) * np.exp(-t * 45.0) * 0.5
    return _stereo(_norm(sig, ROLE_LEVEL["drums"], vel), pan=0.0)


def _trap_808_kit(pitch: int, vel: int, dur: float, sr: int) -> Stereo:
    """Kit trap: bombo 808 largo, clap de 3 rafagas, hats nitidos y platos brillantes."""
    rng = np.random.default_rng(pitch * 31 + vel)
    if pitch in (35, 36):
        t = _time(0.55, sr)
        f = 48.0 + 110.0 * np.exp(-t * 40.0)
        sig = np.tanh(2.0 * np.sin(2 * np.pi * np.cumsum(f) / sr)) * np.exp(-t * 5.5)
    elif pitch in (38, 39, 40):
        t = _time(0.25, sr)
        noise = rng.uniform(-1, 1, len(t))
        bursts = sum(np.exp(-np.maximum(t - o, 0) * 60.0) * (t >= o) for o in (0.0, 0.011, 0.023))
        hp = np.diff(noise, prepend=0.0)
        sig = hp * (bursts + 0.6 * np.exp(-t * 14.0) * (t >= 0.023))
    elif pitch in (42, 44, 46):
        length = 0.035 if pitch != 46 else 0.2
        t = _time(length, sr)
        hp = np.diff(np.diff(rng.uniform(-1, 1, len(t)), prepend=0.0), prepend=0.0)
        sig = hp * np.exp(-t * (90.0 if pitch != 46 else 16.0)) * 0.5
    else:
        return _acoustic_kit(pitch, vel, dur, sr)
    return _stereo(_norm(sig, ROLE_LEVEL["drums"], vel), int(sr * 0.002) if pitch in (42, 44, 46) else 0)


# ---------------------------------------------------------------------------
# GUITARRAS, CUERDAS FROTADAS, TECLADOS, METALES (modelos fisicos simplificados)
# ---------------------------------------------------------------------------

def _body_filter(sig: np.ndarray, sr: int, resonances: Sequence[Tuple[float, float, float]]) -> np.ndarray:
    """Caja de resonancia: realza bandas (frecuencia, ancho, ganancia) en el dominio de frecuencia."""
    spec = np.fft.rfft(sig)
    freqs = np.fft.rfftfreq(len(sig), 1.0 / sr)
    gain = np.ones_like(freqs)
    for f0, bw, g in resonances:
        gain += g * np.exp(-((freqs - f0) / bw) ** 2)
    return np.fft.irfft(spec * gain, len(sig))


def _acoustic_guitar(pitch: int, vel: int, dur: float, sr: int) -> Stereo:
    """Guitarra acustica (nylon/acero): Karplus-Strong + caja de madera (~100/200/400 Hz)."""
    f = _midi_to_freq(pitch)
    sig = _karplus_strong(f, max(dur, 0.35) + 0.4, sr, brightness=0.7, decay=0.9975)
    sig = _body_filter(sig, sr, ((105, 30, 1.2), (210, 50, 0.8), (420, 120, 0.5), (2500, 900, 0.3)))
    return _stereo(_norm(sig, ROLE_LEVEL["lead"], vel), int(sr * 0.007))


def _guitar_strum(pitch: int, vel: int, dur: float, sr: int) -> Stereo:
    """Rasgueo de guitarra: cada cuerda entra unos ms despues segun su altura (rasgueo hacia abajo)."""
    f = _midi_to_freq(pitch)
    delay = int(sr * 0.006 * max(0, min(pitch - 48, 24)) / 2)
    sig = _karplus_strong(f, dur + 0.45, sr, brightness=0.65, decay=0.998)
    sig = _body_filter(sig, sr, ((105, 30, 1.0), (210, 50, 0.7), (420, 120, 0.4)))
    sig = np.concatenate([np.zeros(delay), sig])
    env = np.ones_like(sig)
    cut = delay + int(dur * sr)
    if cut < len(sig):
        env[cut:] = np.exp(-np.arange(len(sig) - cut) / (0.06 * sr))  # apagado con la palma
    return _stereo(_norm(sig * env, ROLE_LEVEL["pad"], vel), int(sr * 0.011))


def _electric_clean(pitch: int, vel: int, dur: float, sr: int) -> Stereo:
    """Electrica limpia: cuerda brillante + pastilla (realce 2-3 kHz) y chorus estereo."""
    f = _midi_to_freq(pitch)
    sig = _karplus_strong(f, max(dur, 0.3) + 0.3, sr, brightness=0.9, decay=0.998)
    sig = _body_filter(sig, sr, ((2500, 800, 0.8),))
    t = np.arange(len(sig)) / sr
    mod = (0.002 + 0.0015 * np.sin(2 * np.pi * 0.8 * t)) * sr
    idx = np.clip(np.arange(len(sig)) - mod, 0, len(sig) - 1)
    chorus = np.interp(idx, np.arange(len(sig)), sig)
    left = _norm(sig + 0.5 * chorus, ROLE_LEVEL["lead"], vel)
    right = _norm(sig - 0.3 * chorus + 0.5 * np.roll(chorus, int(sr * 0.004)), ROLE_LEVEL["lead"], vel)
    return left, right


def _distortion_guitar(pitch: int, vel: int, dur: float, sr: int) -> Stereo:
    """Guitarra distorsionada (power chords): cuerda + saturacion fuerte + parlante 4x12 (paso bajo 4.5 kHz)."""
    f = _midi_to_freq(pitch)
    sig = _karplus_strong(f, dur + 0.15, sr, brightness=0.95, decay=0.999)
    sig = np.tanh(9.0 * sig / (np.max(np.abs(sig)) + 1e-9))
    sig = _fft_lowpass(sig, sr, 4500.0)
    sig = _body_filter(sig, sr, ((120, 60, 0.6), (1800, 700, 0.4)))
    env = _adsr(len(sig), sr, 0.003, 0.0, 1.0, 0.05, dur)
    return _stereo(_norm(sig * env, ROLE_LEVEL["pad"], vel), int(sr * 0.013))


def _bowed(pitch: int, vel: int, dur: float, sr: int, body: Sequence[Tuple[float, float, float]],
           level: float, vib_rate: float = 5.5) -> np.ndarray:
    """Cuerda frotada: sierra con vibrato que entra tarde, ruido de arco y resonancias de caja."""
    t = _time(dur + 0.25, sr)
    f = _midi_to_freq(pitch)
    vib = 1.0 + 0.0045 * np.sin(2 * np.pi * vib_rate * t) * np.clip((t - 0.25) / 0.3, 0.0, 1.0)
    phase = np.cumsum(f * vib) / sr
    saw = 2.0 * (phase % 1.0) - 1.0
    rng = np.random.default_rng(pitch)
    bow = np.convolve(rng.uniform(-1, 1, len(t)), np.ones(4) / 4, mode="same") * 0.08
    sig = _fft_lowpass(saw + bow, sr, min(f * 9.0, 7000.0))
    sig = _body_filter(sig, sr, body)
    env = _adsr(len(t), sr, 0.09, 0.15, 0.85, 0.22, dur)
    return _norm(sig * env, level, vel)


def _violin(pitch: int, vel: int, dur: float, sr: int) -> Stereo:
    """Violin solista (resonancias de caja ~280/460 Hz y formante del puente ~2.8 kHz)."""
    sig = _bowed(pitch, vel, dur, sr, ((280, 60, 0.8), (460, 90, 0.6), (2800, 600, 0.7)), ROLE_LEVEL["lead"])
    return _stereo(sig, int(sr * 0.012), pan=0.1)


def _cello(pitch: int, vel: int, dur: float, sr: int) -> Stereo:
    """Violonchelo como bajo (resonancias ~100/220 Hz)."""
    sig = _bowed(pitch, vel, dur, sr, ((100, 30, 0.9), (220, 60, 0.6), (1500, 400, 0.3)), ROLE_LEVEL["bass"], 5.0)
    return sig, sig


def _piano_tone(pitch: int, vel: int, dur: float, sr: int) -> np.ndarray:
    """Piano: parciales ligeramente inarmonicos (cuerda rigida), los agudos decaen antes, golpe de martillo."""
    f = _midi_to_freq(pitch)
    tail = max(dur, 0.4) + 0.6
    t = _time(tail, sr)
    inharm = 0.0004 * (2 ** ((pitch - 60) / 24))
    sig = np.zeros_like(t)
    hardness = 0.6 + 0.4 * vel / 127.0
    for k in range(1, int(min(16, (sr * 0.45) // f)) + 1):
        fk = k * f * np.sqrt(1.0 + inharm * k * k)
        decay = 1.2 + 0.35 * k * (1 + (pitch - 48) / 48)
        sig += (hardness ** k / k) * np.sin(2 * np.pi * fk * t) * np.exp(-t * decay)
    rng = np.random.default_rng(pitch)
    hammer = rng.uniform(-1, 1, len(t)) * np.exp(-t * 250.0) * 0.3
    damper = np.ones_like(t)
    off = t > dur
    damper[off] = np.exp(-(t[off] - dur) * 9.0)
    return (sig + hammer) * damper * np.minimum(1.0, t / 0.002)


def _piano(pitch: int, vel: int, dur: float, sr: int) -> Stereo:
    sig = _norm(_piano_tone(pitch, vel, dur, sr), ROLE_LEVEL["lead"], vel)
    return _stereo(sig, int(sr * 0.004), pan=0.05 * (pitch - 64) / 12)


def _piano_chords(pitch: int, vel: int, dur: float, sr: int) -> Stereo:
    sig = _norm(_piano_tone(pitch, vel, dur, sr), ROLE_LEVEL["pad"], vel)
    return _stereo(sig, int(sr * 0.004), pan=0.05 * (pitch - 60) / 12)


def _marimba(pitch: int, vel: int, dur: float, sr: int) -> Stereo:
    """Marimba: barra de madera con modos 1 : 3.9 : 9.2 y decaimiento rapido de los agudos."""
    f = _midi_to_freq(pitch)
    t = _time(0.9, sr)
    sig = (np.sin(2 * np.pi * f * t) * np.exp(-t * 4.0)
           + 0.35 * np.sin(2 * np.pi * f * 3.9 * t) * np.exp(-t * 14.0)
           + 0.12 * np.sin(2 * np.pi * f * 9.2 * t) * np.exp(-t * 30.0))
    return _stereo(_norm(sig * np.minimum(1.0, t / 0.001), ROLE_LEVEL["lead"], vel), int(sr * 0.006))


def _harp(pitch: int, vel: int, dur: float, sr: int) -> Stereo:
    """Arpa: cuerda pulsada brillante con resonancia larga."""
    f = _midi_to_freq(pitch)
    sig = _karplus_strong(f, max(dur, 0.8) + 0.8, sr, brightness=0.8, decay=0.9992)
    sig = _body_filter(sig, sr, ((180, 60, 0.6), (900, 300, 0.3)))
    return _stereo(_norm(sig, ROLE_LEVEL["lead"], vel), int(sr * 0.01))


def _brass_section(pitch: int, vel: int, dur: float, sr: int) -> Stereo:
    """Seccion de metales: 2 voces desafinadas; el brillo se abre con el soplido (como trompetas/trombones)."""
    t = _time(dur + 0.12, sr)
    f = _midi_to_freq(pitch)
    env = _adsr(len(t), sr, 0.035, 0.12, 0.85, 0.1, dur)
    cutoff = f * (1.5 + 7.0 * env * (vel / 127.0))
    a = _additive(f * 0.998, t, sr, cutoff, max_harm=24)
    b = _additive(f * 1.002, t + 0.004, sr, cutoff, max_harm=24)
    return _norm(a * env, ROLE_LEVEL["pad"], vel), _norm(b * env, ROLE_LEVEL["pad"], vel)


def _supersaw(pitch: int, vel: int, dur: float, sr: int) -> Stereo:
    """Supersaw (trance / synthwave): 7 sierras desafinadas en abanico estereo."""
    t = _time(dur + 0.2, sr)
    f = _midi_to_freq(pitch)
    detunes = (-0.011, -0.007, -0.003, 0.0, 0.003, 0.007, 0.011)
    voices = [2.0 * ((t * f * (1 + d) + i * 0.13) % 1.0) - 1.0 for i, d in enumerate(detunes)]
    left = sum(v * (1.0 - i / 6) for i, v in enumerate(voices))
    right = sum(v * (i / 6) for i, v in enumerate(voices))
    env = _adsr(len(t), sr, 0.01, 0.15, 0.8, 0.15, dur)
    left = _fft_lowpass(left, sr, min(f * 12, 9000.0)) * env
    right = _fft_lowpass(right, sr, min(f * 12, 9000.0)) * env
    return _norm(left, ROLE_LEVEL["lead"], vel), _norm(right, ROLE_LEVEL["lead"], vel)


def _electric_bass(pitch: int, vel: int, dur: float, sr: int) -> Stereo:
    """Bajo electrico tocado con dedos: cuerda pulsada grave + fundamental reforzada."""
    f = _midi_to_freq(pitch)
    sig = _karplus_strong(f, dur + 0.08, sr, brightness=0.45, decay=0.9985)
    t = np.arange(len(sig)) / sr
    sig = sig + 0.6 * np.sin(2 * np.pi * f * t) * np.exp(-t * 1.5)
    env = np.ones_like(sig)
    cut = int(dur * sr)
    if cut < len(sig):
        env[cut:] = np.exp(-np.arange(len(sig) - cut) / (0.02 * sr))
    mono = _norm(sig * env, ROLE_LEVEL["bass"], vel)
    return mono, mono


def _lofi_kit(pitch: int, vel: int, dur: float, sr: int) -> Stereo:
    """Kit lo-fi: el kit acustico pasado por un muestreador de 12 bits y paso bajo (sonido 'polvoriento')."""
    left, right = _acoustic_kit(pitch, vel, dur, sr)
    sig = (left + right) * 0.5
    sig = np.round(sig * 2048) / 2048  # 12 bits
    sig = _fft_lowpass(sig, sr, 5500.0)
    return _stereo(_norm(sig, ROLE_LEVEL["drums"] * 0.9, vel), int(sr * 0.003))


# ---------------------------------------------------------------------------
# Catalogo
# ---------------------------------------------------------------------------

INSTRUMENTS: Dict[str, Instrument] = {i.id: i for i in [
    Instrument("nes_pulse", "Pulso 8-bit (NES)", "lead", 80, "Magical 8bit Plug / 3xOSC (pulso 25%)",
               "Melodías pegadizas estilo NES/SNES, con vibrato tardío y volumen de 4 bits.", _nes_pulse),
    Instrument("saw_lead", "Saw Lead Analógico", "lead", 81, "Sytrus / 3xOSC (sierra + filtro)",
               "Lead brillante sustractivo con barrido de filtro.", _saw_lead),
    Instrument("fm_bell", "Celesta FM (cajita de música)", "lead", 8, "FL Keys / Sytrus (FM 3.5:1)",
               "Campana FM de 2 operadores: lo tierno con un toque macabro.", _fm_bell),
    Instrument("pizzicato", "Cuerdas Pizzicato", "lead", 45, "FL Slayer / Fruity DX10 (pluck)",
               "Cuerda pulsada Karplus-Strong, el sonido 'Danny Elfman'.", _pizzicato),
    Instrument("flute", "Flauta", "lead", 73, "Sytrus (seno + soplido)",
               "Seno con armonicos suaves, soplido y vibrato.", _flute),
    Instrument("warm_pad", "Pad Cálido", "pad", 89, "Sytrus / FLEX (Warm Pad)",
               "Dos sierras desafinadas con ataque lento.", _warm_pad),
    Instrument("gothic_organ", "Órgano Gótico", "pad", 19, "FPC Organ / Sytrus (registros 16'-2')",
               "Órgano por registros con trémolo Leslie: el lado gótico-clásico.", _gothic_organ),
    Instrument("string_ensemble", "Sección de Cuerdas", "pad", 48, "FLEX Strings / Sytrus",
               "Cuatro sierras desafinadas con ataque de arco.", _string_ensemble),
    Instrument("choir", "Coro 'Aah'", "pad", 52, "Sytrus (formantes)",
               "Armónicos filtrados por los formantes de la vocal A.", _choir),
    Instrument("synth_bass", "Bajo Sintetizado", "bass", 38, "3xOSC / BooBass",
               "Seno + 2.º armónico con saturación suave.", _synth_bass),
    Instrument("sub_808", "Sub 808", "bass", 38, "FL 808 / Transistor Bass",
               "808 con golpe de tono y cola larga para trap.", _sub_808),
    Instrument("upright_pluck", "Contrabajo Pulsado", "bass", 32, "BooBass / FL Slayer",
               "Karplus-Strong grave para walking bass de swing.", _upright_pluck),
    Instrument("tuba", "Tuba", "bass", 58, "Sytrus (bronce)",
               "Bronce grave cuyo brillo sigue al soplido: oom-pah de banda.", _tuba),
    Instrument("acid_303", "Bajo Ácido 303", "bass", 87, "Transistor Bass / Sytrus",
               "Sierra con filtro resonante que barre en cada nota.", _acid_303),
    Instrument("acoustic_kit", "Kit Acústico / Swing", "drums", 0, "FPC (Acoustic Kit)",
               "Bombo, caja, ride, wood blocks y cencerro procedurales.", _acoustic_kit),
    Instrument("chip_kit", "Kit 8-bit (NES)", "drums", 0, "FPC + Magical 8bit Plug",
               "Bombo de triangulo y ruido LFSR del chip 2A03.", _chip_kit),
    Instrument("trap_808_kit", "Kit Trap 808", "drums", 0, "FPC (808 Kit)",
               "Bombo 808 largo, clap de 3 rafagas y hats nitidos.", _trap_808_kit),
    Instrument("acoustic_guitar", "Guitarra Acústica", "lead", 24, "FL Slayer / Kontakt Factory (gratis: Spitfire LABS Guitar)",
               "Cuerda pulsada Karplus-Strong con caja de madera.", _acoustic_guitar),
    Instrument("electric_clean", "Guitarra Eléctrica Limpia", "lead", 27, "FL Slayer + Fruity Chorus",
               "Cuerda brillante con pastilla y chorus estéreo.", _electric_clean),
    Instrument("violin", "Violín Solista", "lead", 40, "FLEX Strings (gratis: Spitfire LABS Strings)",
               "Cuerda frotada con vibrato tardío, ruido de arco y caja de resonancia.", _violin),
    Instrument("piano", "Piano", "lead", 0, "FL Keys / FLEX Piano (gratis: Piano One, Spitfire LABS Soft Piano)",
               "Parciales inarmónicos de cuerda rígida y golpe de martillo.", _piano),
    Instrument("marimba", "Marimba", "lead", 12, "FPC / Sytrus (modos 1:3.9:9.2)",
               "Barra de madera con modos de vibración reales.", _marimba),
    Instrument("harp", "Arpa", "lead", 46, "FL Slayer / Sytrus",
               "Cuerda pulsada brillante con resonancia larga.", _harp),
    Instrument("supersaw", "Supersaw", "lead", 81, "Sytrus / Vital (gratis) / Surge XT (gratis)",
               "Siete sierras desafinadas en abanico estéreo (trance, synthwave).", _supersaw),
    Instrument("guitar_strum", "Guitarra Rasgueada", "pad", 25, "FL Slayer (acordes)",
               "Acordes rasgueados: cada cuerda entra unos milisegundos después.", _guitar_strum),
    Instrument("distortion_guitar", "Guitarra Distorsionada", "pad", 30, "FL Slayer + Fruity Fast Dist",
               "Power chords con saturación fuerte y simulación de parlante 4x12.", _distortion_guitar),
    Instrument("piano_chords", "Piano (acordes)", "pad", 0, "FL Keys / FLEX Piano",
               "El mismo piano físico, nivelado para acompañar.", _piano_chords),
    Instrument("brass_section", "Sección de Metales", "pad", 61, "FLEX Brass / Sytrus",
               "Dos voces de bronce cuyo brillo se abre con el soplido.", _brass_section),
    Instrument("electric_bass", "Bajo Eléctrico", "bass", 33, "BooBass (incluido en FL Studio)",
               "Cuerda grave pulsada con los dedos y fundamental reforzada.", _electric_bass),
    Instrument("cello", "Violonchelo", "bass", 42, "FLEX Strings (gratis: Spitfire LABS Strings)",
               "Cuerda frotada grave con caja de resonancia.", _cello),
    Instrument("lofi_kit", "Kit Lo-fi", "drums", 0, "FPC + Fruity Squeeze (12 bits)",
               "Kit acústico pasado por un muestreador de 12 bits y paso bajo.", _lofi_kit),
]}


# Familia de cada instrumento (para agrupar en la UI)
FAMILIES: Dict[str, str] = {
    "nes_pulse": "8-bit", "chip_kit": "8-bit",
    "saw_lead": "Sintetizadores", "supersaw": "Sintetizadores", "warm_pad": "Sintetizadores",
    "synth_bass": "Sintetizadores", "sub_808": "Sintetizadores", "acid_303": "Sintetizadores",
    "acoustic_guitar": "Guitarras", "electric_clean": "Guitarras", "guitar_strum": "Guitarras",
    "distortion_guitar": "Guitarras", "electric_bass": "Guitarras",
    "violin": "Cuerdas", "pizzicato": "Cuerdas", "string_ensemble": "Cuerdas", "cello": "Cuerdas",
    "upright_pluck": "Cuerdas", "harp": "Cuerdas",
    "piano": "Teclados", "piano_chords": "Teclados", "gothic_organ": "Teclados", "fm_bell": "Teclados",
    "marimba": "Percusión afinada",
    "flute": "Vientos", "brass_section": "Vientos", "tuba": "Vientos", "choir": "Voces",
    "acoustic_kit": "Baterías", "trap_808_kit": "Baterías", "lofi_kit": "Baterías",
}


@dataclass(frozen=True)
class SoundPack:
    id: str
    name: str
    description: str
    rack: Dict[str, str]
    style: str  # estilo de composicion sugerido para la fusion


# Paquetes de sonido: un clic elige los 4 instrumentos y el estilo
SOUND_PACKS: Dict[str, SoundPack] = {p.id: p for p in [
    SoundPack("pvz_gotico", "Gótico-tierno (PvZ)", "Celesta, órgano, contrabajo y swing con percusión rara.",
              {"lead": "fm_bell", "pad": "gothic_organ", "bass": "upright_pluck", "drums": "acoustic_kit"}, "pvz_gotico_swing"),
    SoundPack("orquestal", "Orquestal", "Violín solista, cuerdas, chelo y percusión.",
              {"lead": "violin", "pad": "string_ensemble", "bass": "cello", "drums": "acoustic_kit"}, "seguir_fuente"),
    SoundPack("rock", "Rock", "Guitarra limpia, power chords distorsionados y bajo eléctrico.",
              {"lead": "electric_clean", "pad": "distortion_guitar", "bass": "electric_bass", "drums": "acoustic_kit"}, "seguir_fuente"),
    SoundPack("acustico", "Acústico", "Guitarra punteada y rasgueada, contrabajo y kit acústico.",
              {"lead": "acoustic_guitar", "pad": "guitar_strum", "bass": "upright_pluck", "drums": "acoustic_kit"}, "seguir_fuente"),
    SoundPack("lofi", "Lo-fi", "Piano, pad cálido, bajo eléctrico y batería de 12 bits.",
              {"lead": "piano", "pad": "warm_pad", "bass": "electric_bass", "drums": "lofi_kit"}, "seguir_fuente"),
    SoundPack("trap", "Trap", "Campanas FM, coro, 808 y kit trap.",
              {"lead": "fm_bell", "pad": "choir", "bass": "sub_808", "drums": "trap_808_kit"}, "seguir_fuente"),
    SoundPack("synthwave", "Synthwave", "Supersaw, pad, bajo ácido y kit acústico.",
              {"lead": "supersaw", "pad": "warm_pad", "bass": "acid_303", "drums": "acoustic_kit"}, "seguir_fuente"),
    SoundPack("chiptune", "8-bit / Chiptune", "Pulso NES, metales, bajo sintetizado y kit LFSR.",
              {"lead": "nes_pulse", "pad": "brass_section", "bass": "synth_bass", "drums": "chip_kit"}, "seguir_fuente"),
    SoundPack("piano_bar", "Piano Bar", "Piano, metales, contrabajo y swing.",
              {"lead": "piano", "pad": "brass_section", "bass": "upright_pluck", "drums": "acoustic_kit"}, "pvz_gotico_swing"),
]}


def instruments_for_role(role: str) -> List[Instrument]:
    return [i for i in INSTRUMENTS.values() if i.role == role]


def resolve_rack(choice: Optional[Dict[str, str]], fallback: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Completa un rack: valores invalidos o 'auto' toman el de fallback (o el rack por defecto)."""
    base = dict(DEFAULT_RACK)
    base.update(fallback or {})
    out = {}
    for role in ROLES:
        value = (choice or {}).get(role)
        if value and value in INSTRUMENTS and INSTRUMENTS[value].role == role:
            out[role] = value
        else:
            out[role] = base[role]
    return out


def gm_programs(rack: Dict[str, str]) -> Dict[str, int]:
    """Programas GM por pista MIDI (chords/melody/bass) segun el rack."""
    return {track: INSTRUMENTS[rack[role]].gm_program for track, role in TRACK_ROLE.items() if role != "drums"}


def render_note(instrument_id: str, track_name: str, pitch: int, vel: int, dur: float, sr: int) -> Stereo:
    return INSTRUMENTS[instrument_id].render(pitch, vel, dur, sr)


# ---------------------------------------------------------------------------
# Eleccion automatica a partir del timbre de las fuentes
# ---------------------------------------------------------------------------

# Umbrales (centroide hasta 8 kHz; graves por potencia; percusion por mascara HPSS suave).
# Referencias medidas: leads sostenidos ~0.25 de percusion, pads ~0.4, baterias 0.6-0.7;
# musica comercial suele tener centroide de 1500-3000 Hz.
BRIGHT_LOW = 1300.0
BRIGHT_MID = 2000.0
BRIGHT_HIGH = 2500.0
BASS_HEAVY = 0.6
BASS_LIGHT = 0.3
PERC_AMBIENT = 0.35


@dataclass
class TimbreProfile:
    brightness_hz: float  # centroide espectral
    bass_ratio: float  # energia < 150 Hz / total
    percussiveness: float  # energia percusiva / total (HPSS)


def measure_timbre(mono: np.ndarray, sr: int, max_sec: float = 30.0) -> TimbreProfile:
    """Mide brillo, peso de graves y percusividad (solo estadistica, no se guarda audio)."""
    n_fft, hop = 2048, 1024
    mono = np.asarray(mono[: int(sr * max_sec)], dtype=np.float64)
    if len(mono) < n_fft * 2:
        return TimbreProfile(2000.0, 0.2, 0.3)
    window = np.hanning(n_fft)
    frames = np.array([mono[s:s + n_fft] * window for s in range(0, len(mono) - n_fft, hop)])
    spec = np.abs(np.fft.rfft(frames, axis=1))
    freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
    power = spec ** 2
    total = float(power.sum()) or 1e-12
    # Centroide hasta 8 kHz: por encima casi todo es ruido de platillos y aire
    band = freqs <= 8000.0
    centroid = float((spec[:, band] * freqs[band]).sum() / max(spec[:, band].sum(), 1e-12))
    bass = float(power[:, freqs < 150.0].sum()) / total

    k = 9
    if len(spec) >= k:
        from numpy.lib.stride_tricks import sliding_window_view

        half = k // 2
        harm = np.median(sliding_window_view(np.pad(spec, ((half, half), (0, 0)), mode="edge"), k, axis=0), axis=-1)
        perc = np.median(sliding_window_view(np.pad(spec, ((0, 0), (half, half)), mode="edge"), k, axis=1), axis=-1)
        # Mascara suave P/(H+P) ponderada por magnitud (no potencia), para que un bajo
        # sostenido no tape a la bateria: ~0.2 en un pad ambiental, >0.4 con bateria.
        soft = perc / np.maximum(harm + perc, 1e-12)
        perc_energy = float((spec * soft).sum()) / max(float(spec.sum()), 1e-12)
    else:
        perc_energy = 0.3
    return TimbreProfile(round(centroid, 1), round(bass, 3), round(perc_energy, 3))


def suggest_instruments(
    timbres: Sequence[TimbreProfile],
    bpm: int,
    minor: bool,
    style: str,
) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Elige un instrumento por rol a partir del timbre promedio de las fuentes.

    Devuelve (rack, razones). Las reglas son simples y explicables a proposito:
    el usuario ve en la UI por que se eligio cada sonido y puede cambiarlo.
    """
    if timbres:
        bright = float(np.mean([t.brightness_hz for t in timbres]))
        bass = float(np.mean([t.bass_ratio for t in timbres]))
        perc = float(np.mean([t.percussiveness for t in timbres]))
    else:
        bright, bass, perc = 2000.0, 0.2, 0.3
    pvz = style == "pvz_gotico_swing"
    rack: Dict[str, str] = {}
    why: Dict[str, str] = {}
    info = f"brillo {bright:.0f} Hz, graves {bass:.0%}, percusion {perc:.0%}, {bpm} BPM"

    # Lead
    if pvz:
        rack["lead"] = "fm_bell" if minor and bright < BRIGHT_MID else "nes_pulse"
        why["lead"] = "estilo PvZ: melodia pegadiza 8-bit" if rack["lead"] == "nes_pulse" else "estilo PvZ en menor y fuente oscura: cajita de musica macabra"
    elif bright >= BRIGHT_HIGH:
        rack["lead"], why["lead"] = "saw_lead", "fuente brillante"
    elif bright < BRIGHT_LOW:
        rack["lead"], why["lead"] = "flute", "fuente oscura y suave"
    elif perc < PERC_AMBIENT:
        rack["lead"], why["lead"] = "fm_bell", "fuente poco percusiva (ambiental)"
    else:
        rack["lead"], why["lead"] = "nes_pulse", "brillo medio: lead de pulso pegadizo"

    # Armonia
    if pvz:
        rack["pad"] = "gothic_organ" if minor else "string_ensemble"
        why["pad"] = "lado gotico-clasico de Shigihara" if minor else "estilo PvZ en mayor: cuerdas"
    elif perc < PERC_AMBIENT:
        rack["pad"], why["pad"] = "choir", "fuente ambiental: coro"
    elif bpm <= 95:
        rack["pad"], why["pad"] = "warm_pad", "tempo lento: pad calido"
    else:
        rack["pad"], why["pad"] = "string_ensemble", "tempo medio/rapido: cuerdas"

    # Bajo
    if pvz:
        rack["bass"] = "upright_pluck" if minor else "tuba"
        why["bass"] = "walking bass de swing" if minor else "oom-pah de banda"
    elif bpm >= 130 and bass >= BASS_HEAVY:
        rack["bass"], why["bass"] = "sub_808", "tempo trap y fuente con muchos graves"
    elif 115 <= bpm < 135 and bright >= BRIGHT_MID:
        rack["bass"], why["bass"] = "acid_303", "tempo de pista y fuente brillante"
    else:
        rack["bass"], why["bass"] = "synth_bass", "bajo neutro"

    # Bateria
    if pvz:
        rack["drums"], why["drums"] = "acoustic_kit", "swing de big band con percusion rara"
    elif bpm >= 130 and bass >= BASS_HEAVY:
        rack["drums"], why["drums"] = "trap_808_kit", "tempo trap y graves fuertes"
    elif bright >= BRIGHT_HIGH and bass < BASS_LIGHT:
        rack["drums"], why["drums"] = "chip_kit", "fuente brillante y liviana: kit 8-bit"
    else:
        rack["drums"], why["drums"] = "acoustic_kit", "kit acustico"

    reasons = {role: f"{why[role]} ({info})" for role in ROLES}
    return rack, reasons


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

def preview_events(instrument_id: str, bpm: int = 110):
    """Frase corta para escuchar un instrumento en la UI (arpegio en La menor o groove)."""
    from .midi_generator import NoteEvent

    inst = INSTRUMENTS[instrument_id]
    spb = 60.0 / bpm
    track = {v: k for k, v in TRACK_ROLE.items()}[inst.role]
    ch = {"lead": 1, "pad": 0, "bass": 2, "drums": 9}[inst.role]
    events = []
    if inst.role == "drums":
        for bar in range(2):
            for s16 in range(16):
                t = (bar * 16 + s16) * spb / 4
                if s16 % 2 == 0:
                    events.append(NoteEvent(42, 80, t, 0.05, track, ch))
                if s16 in (0, 6, 10):
                    events.append(NoteEvent(36, 112, t, 0.15, track, ch))
                if s16 in (4, 12):
                    events.append(NoteEvent(38, 104, t, 0.18, track, ch))
            events.append(NoteEvent(76, 100, (bar * 16 + 15) * spb / 4, 0.08, track, ch))
    elif inst.role == "pad":
        for i, chord in enumerate(([57, 60, 64], [53, 57, 60], [52, 56, 59, 62], [57, 60, 64])):
            events += [NoteEvent(p, 84, i * spb * 2, spb * 1.9, track, ch) for p in chord]
    else:
        base = [69, 72, 76, 81, 79, 76, 75, 76] if inst.role == "lead" else [45, 45, 52, 45, 41, 48, 40, 44]
        events = [NoteEvent(p, 100, i * spb / 2, spb * 0.45, track, ch) for i, p in enumerate(base)]
    duration = max(e.start_sec + e.duration_sec for e in events)
    return events, duration
