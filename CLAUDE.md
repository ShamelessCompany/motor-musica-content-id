# CLAUDE.md — Contexto y Guía de Arquitectura para Claude Code

Este archivo proporciona todo el contexto técnico, reglas de diseño, invariantes y comandos para interactuar y modificar el proyecto **Motor Procedural de Música & Monetización por Content ID**.

---

## 1. Visión General del Proyecto

- **Nombre:** Motor Procedural de Música & Beat Studio (Shameless Company)
- **Ruta Local:** `D:\ProyectosProgramacion\motor-musica-content-id`
- **Repositorio GitHub:** [ShamelessCompany/motor-musica-content-id](https://github.com/ShamelessCompany/motor-musica-content-id)
- **Propósito:** Generación algorítmica de fonogramas 100% originales (audio WAV y proyectos MIDI editables) diseñados para monetizar en **YouTube Content ID** (Identifyy, Soundrop, Songtradr) y vender licencias de Beats a raperos (BeatStars/Airbit), con interfaz Retro PC DAW (Windows 98).

---

## 2. Comandos Esenciales (Build, Test, Run)

### Entorno Virtual
```powershell
cd D:\ProyectosProgramacion\motor-musica-content-id
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### Ejecutar Pruebas Unitarias (51 tests)
```powershell
python -m unittest discover -s tests -t . -v
```

### Iniciar Servidor Web / Panel Visual (Port 5055)
```powershell
python app.py
```
Acceso web: `http://127.0.0.1:5055`

### Ejecutar Demo por Consola (Genera WAV, MID, Scripts y Catálogo)
```powershell
python demo.py
```

---

## 3. Invariantes y Reglas Críticas del Dominio

> [!CAUTION]
> **1. Regla de Oro de YouTube Content ID (Cero Samples / Cero Loops):**
> Las distribuidoras (Identifyy, Soundrop) expulsan permanentemente cuentas que usen loops melódicos pregrabados (Splice, Looperman, Cymatics).
> **Solución implementada:** TODAS las notas, arpegios, progresiones armónicas y líneas de bajo se generan matemáticamente en Python. Cero uso de archivos WAV de terceros en la composición.

> [!IMPORTANT]
> **2. Calibración de Sonoridad Profesional:**
> Todo renderizado de audio estéreo 44.1 kHz PCM debe masterizarse con normalización soft-limiter a **-14.0 LUFS** con un techo **True Peak máximo de -1.0 dBFS** (ver `motor_musica/synth_renderer.py`).

> [!NOTE]
> **3. Ruteo MIDI Estándar Formato 1:**
> - Canal 0: Acordes / Armonía / Pads
> - Canal 1: Melodía / Lead / Arpegio
> - Canal 2: Bajo (Sub 808, Walking bass o sintetizado)
> - Canal 9 (10 en FL Studio): Batería GM estándar (36 Bombo, 38 Caja, 42 Hi-hat cerrado, 49 Crash, 39 Clap)

> [!IMPORTANT]
> **4. Fusión Multi-Link: el audio de las fuentes solo se mide:**
> `harmonic_fusion.py` descarga ~30 s de cada link para medir tempo, tonalidad y huella, y borra el archivo. Nunca se copia, recorta ni re-sintetiza audio de la fuente. Toda fusión debe pasar `content_id_checks.py` (huella < 15 % por fuente, -14 LUFS ±2, pico ≤ -1 dBFS). Ver `docs/FUSION_ARMONICA.md`.

> [!IMPORTANT]
> **4b. Importar Playlist: solo rasgos abstractos:**
> `playlist_import.py` guarda por tema tempo, tonalidad, modo, brillo, graves, percusión, densidad rítmica, energía y la huella (hashes), nunca audio ni notas. Está prohibido transcribir melodía, letra o partitura de las fuentes. Ver `docs/IMPORTAR_PLAYLIST.md`.

> [!NOTE]
> **5. Curvas de Mezcla de Igual Potencia:**
> Los crossfades en `song_mixer.py` deben usar modulación trigonométrica ($\cos(\theta)$ y $\sin(\theta)$ donde $\cos^2 + \sin^2 = 1$) para evitar la caída de 3 dB en el punto medio de transición.

---

## 4. Mapa de Arquitectura y Módulos

```
motor-musica-content-id/
├── app.py                         # Servidor Flask, API REST y ruteo de archivos
├── demo.py                        # Script CLI generador de pistas y catálogo
├── requirements.txt               # Dependencias mínimas (mido, numpy, Flask)
├── .gitignore                     # Ignora audio/*.wav y zips pesados
├── motor_musica/
│   ├── __init__.py                # Exporta clases principales
│   ├── theory.py                  # Escalas, acordes, power chords, perfiles de género
│   ├── midi_generator.py          # Constructor MIDI Format 1 multipista (808 rolls, fills)
│   ├── synth_renderer.py          # Síntesis procedural NumPy (sustractiva, aditiva, kicks, snares, hats)
│   ├── dna_extractor.py          # Cadenas de Markov y extracción de matrices armónicas
│   ├── youtube_dna.py             # Croma armónico (HPSS) Krumhansl-Schmuckler y BPM por flujo espectral
│   ├── harmonic_fusion.py         # Fusión multi-link: círculo de quintas, leitmotiv, estilo PvZ (Shigihara)
│   ├── content_id_checks.py       # Huella acústica, similitud tonal y checks de sonoridad
│   ├── playlist_import.py         # Playlist de YouTube → rasgos abstractos, género por reglas y temas parecidos
│   ├── instruments.py             # Rack de 31 instrumentos procedurales, familias, 9 paquetes de sonido y elección por timbre
│   ├── song_editor.py             # Proyecto editable por tema: instrumentos, mezcla, transponer, tempo, nueva melodía
│   ├── fl_project_builder.py      # Empaquetador .zip para FL Studio (master MIDI, stems, routing JSON)
│   ├── song_mixer.py              # Mezclador multi-pista (DJ Crossfade, Stem Mashup, Dual Deck)
│   ├── license_generator.py       # Emisión de licencias para raperos (MP3, WAV, Stems, Exclusivo)
│   ├── flstudio_cli.py            # Generador de scripts headless para FL64.exe
│   └── metadata_manager.py        # Códigos ISRC ISO 3901 y exportación CSV/JSON
├── templates/
│   ├── index.html                 # UI Retro Windows 98 DAW con pantalla CRT verde y Web Audio
│   ├── channel_mapping.json       # Mapeo de canales MIDI a VSTs de FL Studio (Sytrus, FLEX, FPC)
│   └── README_TEMPLATES.md        # Documentación de plantillas DAW
├── docs/
│   ├── FUSION_ARMONICA.md         # Teoría (ley de cuartas), principios de Laura Shigihara y checks
│   ├── RACK_INSTRUMENTOS.md       # Catálogo de instrumentos, síntesis y elección automática
│   ├── IMPORTAR_PLAYLIST.md       # Playlist → géneros → temas originales parecidos (qué se extrae y qué no)
│   └── GUIA_WORKFLOW.md           # Guía de uso: crear en 3 pasos, editar, FL Studio y plugins gratis legales
├── tests/                         # Suite completa con 51 unit tests
└── output/                        # Directorios generados (audio, midi, metadata, fl_packages)
```

---

## 5. Endpoints de la API REST (`app.py`)

- `GET /` — Carga la estación de trabajo visual Retro PC (Windows 98).
- `GET /api/tracks` — Lista catálogo actual con metadatos ISRC.
- `POST /api/generate` — Genera pista inédita (`genre`, `bars`, `title`).
- `POST /api/youtube-dna` — Analiza link YouTube, extrae BPM/Tonalidad y compone tema original.
- `POST /api/harmonic-fusion` — 1 a 5 fuentes (links y/o archivos subidos por multipart `files`) → tema original armónico + reporte de checks (`urls`, `style`: `pvz_gotico_swing`|`seguir_fuente`, `bars_per_section`, `variation`, `title`).
- `GET /api/instruments` — Catálogo del rack por rol (`lead`, `pad`, `bass`, `drums`) con `family`, más `packs` (paquetes de sonido).
- `GET /api/instrument-preview/<id>` — WAV corto para escuchar un instrumento.
- `POST /api/generate` y `POST /api/harmonic-fusion` aceptan `pack` (id de paquete de sonido) e `instruments` ({rol: id}; rol ausente = AUTO). Ambos guardan el proyecto editable en `output/metadata/projects/<isrc>.json`.
- `GET /api/project/<isrc>` — Proyecto editable del tema + piano roll.
- `POST /api/project/<isrc>/render` — Aplica `edits` (`rack`, `volumes`, `muted`, `transpose`, `bpm`, `new_melody`) y re-renderiza: versión `_vN` del mismo ISRC, o tema nuevo con `as_new: true` (+ `title`).
- `POST /api/playlist/import` — `{url, limit<=25}` → `job_id`; mide cada tema en segundo plano (`GET /api/playlist/job/<job_id>`).
- `GET /api/playlist/<id>` — Temas con rasgos abstractos, género estimado (ranking y razón) y grupos por género.
- `POST /api/playlist/<id>/genre` — Corrige el género de un tema (`index`, `genre` o `auto`).
- `POST /api/playlist/<id>/compose` — Temas originales parecidos: `mode` `per_track`|`per_genre`, `indices`/`genres`, `bars`, `pack`, `instruments`. Guarda proyecto editable y checks de huella por fuente.
- `POST /api/mix-tracks` — Mezcla 2 temas (`isrc_a`, `isrc_b`, `mode`: `crossfade`|`mashup`|`blend`).
- `GET /api/flstudio-package/<isrc>` — Genera y descarga el paquete `.zip` editable en FL Studio.
- `GET /api/license/<isrc>?tier=...` — Genera contrato legal (`basic_mp3`, `premium_wav`, `stems`, `exclusive`).
- `GET /audio/<filename>` — Transmite audio `.wav` estéreo.
- `GET /midi/<filename>` — Descarga archivo `.mid` multipista.

---

## 6. Géneros y Algoritmos Implementados

| Género | BPM | Escala / Modo | Claves de Síntesis / Composición |
|---|---|---|---|
| `dark_trap` | 140 | Frigia (`PHRYGIAN`) | 808 Sub-bass con glide y pitch-drop, hi-hat rolls (semicorcheas/fusas), claps a contratiempo, campanas oscuras. |
| `boom_bap` | 92 | Dórica (`DORIAN`) | Swing polvoriento, bombo/caja 90s, walking bass sincopado, acordes jazz. |
| `hard_rock` | 136 | Pentatónica Blues (`ROCK_PENTATONIC`) | Power chords distorsionados (raíz + 5ta + octava), crash fills, solos blues. |
| `epic_cinematic` | 120 | Menor Armónica (`HARMONIC_MINOR`) | Arpegios rápidos, staccato, timbales y cuerdas orquestales. |
| `synthwave` | 124 | Dórica (`DORIAN`) | Bajo octavado analógico, pads analógicos retro, bombo 4-on-the-floor. |
| `lofi_chill` | 82 | Menor Natural (`NATURAL_MINOR`) | Acordes extendidos de 7ma y 9na estilo Rhodes, swing relajado. |

---

## 7. Directrices para Modificar el Código con Claude Code

1. **Mantener la filosofía minimalista:** No agregar dependencias externas pesadas si `NumPy` o la biblioteca estándar de Python lo resuelven.
2. **Preservar el aislamiento de Content ID:** NUNCA reemplazar la síntesis algorítmica por paquetes de loops de audio pregrabados.
3. **Mantener compatibilidad de pruebas:** Cada nueva funcionalidad o ajuste debe pasar los 51 tests existentes (`python -m unittest discover -s tests -t . -v`) o agregar su respectivo test en `tests/`.
4. **Preservar el estilo de UI:** La interfaz debe conservar la estética retro (Windows 98, bordes 3D, monitor CRT verde fósforo, controles físicos). No convertir a diseño moderno plano o plantillas SaaS genéricas.
