# Motor Procedural de Música & Monetización por Content ID

Motor algorítmico en Python para la composición y renderizado de música instrumental original, diseñado específicamente para cumplir con las políticas estrictas de monetización de **YouTube Content ID** (Identifyy, Soundrop, Songtradr, TuneCore) y la creación de Beats para Raperos con licencias comerciales.

Ubicación del proyecto: `D:\Programacion\motor-musica-content-id`

---

## 1. Advertencia Crítica: Reglas de YouTube Content ID

> [!CAUTION]
> **Prohibición Total de Sample Packs Comerciales o Gratuitos:**
> Las distribuidoras autorizadas para Content ID penalizan y expulsan permanentemente a los creadores que utilicen loops o melodías prediseñadas (Splice, Looperman, Cymatics).
> 
> **Solución de este Motor:**
> 1. **Cero Muestras Pregrabadas:** Todas las progresiones armónicas, arpegios y líneas de bajo se componen matemáticamente en tiempo de ejecución.
> 2. **Composición Algorítmica en MIDI:** Matrices de teoría musical (Menor Armónica, Dórica, Frigia, Blues Pentatónica, Lofi 7/9).
> 3. **Síntesis Pura:** Síntesis procedural integrada por software (NumPy sin dependencias de hardware externas) y ruteo a sintetizadores nativos de FL Studio.
> 4. **Masterización a -14 LUFS:** Calibración de sonoridad profesional con techo True Peak de -1.0 dBFS.

---

## 2. Requisitos Previos e Instalación

### Requisitos del Sistema
- **Sistema Operativo:** Windows 10/11 (o Linux en servidores cloud).
- **Python:** Versión 3.10 o superior (verificado en Python 3.14).
- **Opcional:** FL Studio 20, 21 o 2024 (para edición interactiva mediante los paquetes `.zip` generados o renderizado CLI).

### Pasos de Instalación

1. **Abrir terminal en la carpeta del proyecto:**
   ```powershell
   cd D:\Programacion\motor-musica-content-id
   ```

2. **Crear y activar un entorno virtual (recomendado):**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\activate
   ```

3. **Instalar dependencias requeridas:**
   ```powershell
   pip install -r requirements.txt
   ```
   *Dependencias instaladas:*
   - `mido>=1.3.0` (Generación de archivos MIDI multipista estándar).
   - `numpy>=1.24.0` (Cálculo vectorial de síntesis aditiva/sustractiva y procesamiento de señales).
   - `Flask>=3.0.0` (Servidor del Panel de Control Visual).

---

## 3. Panel de Control Visual — Estilo Retro PC DAW (Windows 98)

El software cuenta con un entorno retro de estación de trabajo musical (estilo DAW vintage / Windows 98) con monitor CRT de fósforo verde, visualizador de frecuencias Web Audio API y medidor LCD:

```powershell
python app.py
```

Abre en tu navegador: **`http://127.0.0.1:5055`**

### Pestañas y Funcionalidades:
- **🎛️ Compositor Procedural:** Selector de géneros (Rock, Trap, Boom Bap, Cinematic, Synthwave, Lofi), afinación base, escala, tempo y complejidad rítmica.
- **🧬 YouTube DNA a Canción Original:** Convierte cualquier link de YouTube en una composición 100% original analizando BPM y tonalidad espectral (cero samples del audio original, inmune a Content ID).
- **🎚️ Mezclador Multi-Pista:** Selector de pistas para mezclas estilo DJ (Crossfade de igual potencia matemática $\cos/\sin$), Mashups de Stems (mezcla de bases y melodías de diferentes temas) y Dual Deck Blend.
- **📦 Paquetes Editables FL Studio:** Descarga proyectos en `.zip` con archivo MIDI multipista maestro, MIDIs individuales de cada stem (chords, lead, bass, drums), guía de ruteo de canales a VSTs y script de arranque `Open_In_FLStudio.ps1`.
- **📄 Contratos y Licencias:** Emisión de licencias para venta de beats a raperos (MP3 Lease $29, WAV Lease $49, Trackout Stems $149, Derechos Exclusivos $499) con cláusulas legales para BeatStars / Airbit.
- **📁 Catálogo ISRC:** Gestión de códigos de identificación fonográfica ISO 3901 y exportación directa a CSV y JSON para distribuidoras.

---

## 4. Géneros y Beats Disponibles

- **😈 Dark Trap & 808 Sub (140 BPM - Modo Frigio):** 808 Sub Bass saturado con pitch drop, hi-hat rolls en semicorcheas y fusas, claps en tiempo 3, campanas oscuras estilo Metro Boomin / Travis Scott.
- **📻 90s Boom Bap (92 BPM - Modo Dórico):** Bombo y caja con swing polvoriento, walking bass sincopado y acordes de piano jazz estilo NYC Golden Era / Griselda.
- **🎸 Hard Rock & Heavy Riffs (136 BPM - Pentatónica Blues):** Power chords distorsionados (raíz + 5ta + octava), bajo con groove octavado, crash cymbals y solos de guitarra blues.
- **⚔️ Epic Cinematic (120 BPM - Menor Armónica):** Arpegios rápidos, cuerdas orquestales épicas y percusión de marcha.
- **🌆 Synthwave 80s (124 BPM - Dórica):** Bajo octavado analógico, leads brillantes y bombo 4-on-the-floor.
- **☕ Lofi Chillhop (82 BPM - 7mas & 9nas):** Acordes de teclado Rhodes, bombo boom-bap relajado con swing sutil.

---

## 5. Demostración Rápida por Consola

Para generar una tanda completa de temas de prueba con audio WAV, MIDI multipista, scripts FL Studio y catálogo ISRC sin abrir el navegador:

```powershell
python demo.py
```

---

## 6. Ejecución de la Suite de Pruebas Unitarias

Para verificar la integridad matemática y técnica de todo el motor:

```powershell
python -m unittest discover -s tests -t . -v
```

Resultado esperado: 18 tests ejecutados con `OK`.

---

## 7. Estructura del Proyecto

```
D:\Programacion\motor-musica-content-id/
├── README.md                      # Documentación completa de instalación y uso
├── requirements.txt               # Dependencias (mido, numpy, Flask)
├── .gitignore                     # Exclusión de binarios pesados y venv
├── app.py                         # Servidor Flask con API REST y panel retro
├── demo.py                        # Demostración ejecutable por consola
├── motor_musica/
│   ├── __init__.py                # Paquete exportador del motor
│   ├── theory.py                  # Escalas, acordes, power chords y perfiles de género
│   ├── midi_generator.py          # Constructor de MIDI multipista Formato 1
│   ├── synth_renderer.py          # Sintetizador procedural y limitador LUFS
│   ├── dna_extractor.py          # Extractor de matrices de transición y ADN armónico
│   ├── youtube_dna.py             # Análisis espectral de audio YouTube a beat original
│   ├── license_generator.py       # Generador de contratos y licencias para raperos
│   ├── fl_project_builder.py      # Empaquetador de proyectos editables para FL Studio
│   ├── song_mixer.py              # Mezclador multi-pista y crossfade de igual potencia
│   ├── flstudio_cli.py            # Detección y puente CLI headless con FL Studio
│   └── metadata_manager.py        # Generación de códigos ISRC y catálogos CSV/JSON
├── templates/
│   ├── index.html                 # Interfaz visual Retro PC / Windows 98 DAW
│   ├── channel_mapping.json       # Definición de canales y ruteo a VSTs
│   └── README_TEMPLATES.md        # Documentación técnica de plantillas DAW
├── tests/
│   ├── test_theory.py             # Pruebas de teoría musical
│   ├── test_midi_generator.py     # Pruebas de exportación MIDI
│   ├── test_synth_renderer.py     # Pruebas de síntesis y masterización
│   ├── test_metadata.py           # Pruebas de ISRC y catálogos
│   ├── test_flstudio_cli.py       # Pruebas de comandos CLI
│   ├── test_dna_extractor.py      # Pruebas de matrices de ADN y mutación
│   ├── test_fl_project_builder.py # Pruebas de proyectos editables FL Studio
│   └── test_song_mixer.py         # Pruebas de mezclas y crossfade de potencia
└── output/
    ├── audio/                     # Archivos WAV estéreo generados (.wav)
    ├── midi/                      # Archivos MIDI multipista generados (.mid)
    ├── fl_packages/               # Paquetes editables ZIP para FL Studio
    ├── flstudio_scripts/          # Scripts PowerShell para renderizado CLI
    └── metadata/                  # Catálogos ISRC en CSV y JSON
```

---

## 8. Flujo de Monetización en Content ID

1. Ejecutar `python app.py` o `python demo.py` para generar una tanda de pistas instrumentales.
2. Comprobar que los audios cumplen con el estándar (-14 LUFS, True Peak <= -1.0 dBFS).
3. Importar `output/metadata/catalog_content_id.csv` en tu distribuidora (**Identifyy**, **Soundrop**, **Songtradr** o **TuneCore**).
4. Subir los archivos `.wav` de `output/audio/` correspondientes a cada código ISRC.
5. Activar la casilla **"YouTube Content ID"** en el panel de distribución.
6. A partir de ese momento, cualquier video de YouTube que utilice la música generará ingresos automáticos por reclamo de derechos de autor.
