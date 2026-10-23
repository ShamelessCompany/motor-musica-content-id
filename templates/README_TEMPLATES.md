# Guía de Plantillas (.flp) y Ruteo de Canales para FL Studio

Este documento detalla la estructura para crear la plantilla maestra (`EpicTemplate.flp`) en FL Studio para renderizado automatizado por línea de comandos.

---

## 1. Mapeo de Instrumentos y Canales MIDI

El generador algorítmico exporta archivos MIDI estándar (Formato 1) organizados en 4 canales:

| Canal MIDI (1-16) | Índice Python (0-15) | Rol Musical | Instrumento Nativo Recomendado | Inserción en Mixer |
|---|---|---|---|---|
| **Canal 1** | 0 | Chords / Pads (Armonía) | **Sytrus** o **FLEX** (Preset: Warm String Pad) | Insert 1 |
| **Canal 2** | 1 | Melody / Lead (Tema / Arpegio) | **Sytrus** o **Harmless** (Preset: Pluck Synth / Lead) | Insert 2 |
| **Canal 3** | 2 | Bassline (Línea de Bajo) | **3xOSC** o **BooBass** (Sub Bass saturado) | Insert 3 |
| **Canal 10** | 9 | Batería (General MIDI) | **FPC** con mapeo estándar GM (Kick=36, Snare=38, Hat=42) | Insert 4 |

---

## 2. Configuración del Master Bus (Loudness Content ID)

Para cumplir con las normas de YouTube Content ID y evitar penalizaciones de normalización:
1. **Target Loudness:** `-14.0 LUFS` integrado.
2. **True Peak Ceiling:** `-1.0 dBFS` (para prevenir distorsión en la conversión a Opus/AAC de YouTube).
3. **Efectos recomendados en el Master:**
   - **Fruity Parametric EQ 2:** Corte paso alto a 25 Hz (elimina sub-bajos inaudibles que saturan el limitador).
   - **Fruity Limiter / Maximus:** Ceiling en `-1.0 dB`, compresión suave con ratio 2:1 y release de 150-200ms.

---

## 3. Renderizado Headless CLI

Una vez guardada la plantilla en `templates/EpicTemplate.flp`, se puede renderizar directamente con:

```powershell
& "C:\Program Files\Image-Line\FL Studio 21\FL64.exe" /R /Fwav /O"d:\Programacion\motor-musica-content-id\output\audio\" "d:\Programacion\motor-musica-content-id\templates\EpicTemplate.flp"
```

*Nota: Si no tienes FL Studio instalado, el motor cuenta con `synth_renderer.py` que genera el audio WAV de alta fidelidad de forma matemática autónoma.*
