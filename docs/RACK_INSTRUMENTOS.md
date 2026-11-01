# Rack de Instrumentos Procedurales

Treinta y un instrumentos sintetizados con fórmulas matemáticas en NumPy (cero samples, igual que
el resto del motor). Se eligen a mano en la pestaña **Rack de Instrumentos** o automáticamente a
partir del timbre de los temas analizados (links de YouTube o archivos descargados).

- Código: `motor_musica/instruments.py`
- UI: pestaña **Rack de Instrumentos** (`templates/index.html`)
- API: `GET /api/instruments`, `GET /api/instrument-preview/<id>`, y el campo `instruments` en
  `POST /api/generate` y `POST /api/harmonic-fusion`
- Tests: `tests/test_instruments.py`, `tests/test_song_editor.py`
- Paquetes de sonido (`SOUND_PACKS`) y edición de temas: ver [`GUIA_WORKFLOW.md`](GUIA_WORKFLOW.md)

## 1. Catálogo

Cada rol corresponde a un canal MIDI del proyecto (ver `CLAUDE.md`).

| Rol (canal) | Id | Instrumento | Técnica de síntesis | GM | Plugin sugerido en FL Studio |
|---|---|---|---|---|---|
| Melodía (1) | `nes_pulse` | Pulso 8-bit (NES) | Onda de pulso 25 %, volumen cuantizado a 4 bits, vibrato tardío | 80 | Magical 8bit Plug / 3xOSC |
| | `saw_lead` | Saw Lead Analógico | Dos sierras desafinadas, filtro con barrido (síntesis aditiva filtrada) | 81 | Sytrus / 3xOSC |
| | `fm_bell` | Celesta FM | FM de 2 operadores, relación 3.5:1, índice que decae | 8 | FL Keys / Sytrus |
| | `pizzicato` | Cuerdas Pizzicato | Karplus-Strong (cuerda pulsada) | 45 | FL Slayer / DX10 |
| | `flute` | Flauta | Seno + armónicos suaves + soplido filtrado + vibrato | 73 | Sytrus |
| | `acoustic_guitar` | Guitarra Acústica | Karplus-Strong + resonancia de caja de madera | 24 | FL Slayer (gratis: Spitfire LABS) |
| | `electric_clean` | Guitarra Eléctrica Limpia | Cuerda brillante con pastilla y chorus estéreo | 27 | FL Slayer + Fruity Chorus |
| | `violin` | Violín Solista | Cuerda frotada (arco), vibrato tardío, ruido de arco y caja | 40 | FLEX Strings (gratis: Spitfire LABS) |
| | `piano` | Piano | Parciales inarmónicos de cuerda rígida + martillo | 0 | FL Keys (gratis: Piano One) |
| | `marimba` | Marimba | Modos de barra de madera 1 : 3.9 : 9.2 | 12 | FPC / Sytrus |
| | `harp` | Arpa | Cuerda pulsada brillante con resonancia larga | 46 | FL Slayer / Sytrus |
| | `supersaw` | Supersaw | Siete sierras desafinadas en abanico estéreo | 81 | Sytrus / Vital / Surge XT |
| Armonía (0) | `warm_pad` | Pad Cálido | Sierras desafinadas + seno, ataque lento | 89 | Sytrus / FLEX |
| | `gothic_organ` | Órgano Gótico | Aditiva por registros 16'-2' con trémolo Leslie | 19 | FPC Organ / Sytrus |
| | `string_ensemble` | Sección de Cuerdas | 4 sierras desafinadas, paso bajo, ataque de arco | 48 | FLEX Strings |
| | `choir` | Coro "Aah" | Armónicos ponderados por formantes de la vocal A (700/1220/2600 Hz) | 52 | Sytrus |
| | `guitar_strum` | Guitarra Rasgueada | Acordes con cada cuerda entrando unos ms después | 25 | FL Slayer |
| | `distortion_guitar` | Guitarra Distorsionada | Power chords saturados + simulación de parlante 4x12 | 30 | FL Slayer + Fruity Fast Dist |
| | `piano_chords` | Piano (acordes) | El mismo piano físico, nivelado para acompañar | 0 | FL Keys |
| | `brass_section` | Sección de Metales | Dos voces de bronce cuyo brillo sigue al soplido | 61 | FLEX Brass / Sytrus |
| Bajo (2) | `synth_bass` | Bajo Sintetizado | Seno + 2.º armónico saturado | 38 | 3xOSC / BooBass |
| | `sub_808` | Sub 808 | Seno con golpe de tono y cola larga | 38 | FL 808 / Transistor Bass |
| | `upright_pluck` | Contrabajo Pulsado | Karplus-Strong grave + cuerpo | 32 | BooBass / FL Slayer |
| | `tuba` | Tuba | Bronce: el brillo del filtro sigue a la envolvente | 58 | Sytrus |
| | `acid_303` | Bajo Ácido 303 | Sierra con filtro resonante que barre en cada nota | 87 | Transistor Bass |
| | `electric_bass` | Bajo Eléctrico | Cuerda grave pulsada con los dedos, fundamental reforzada | 33 | BooBass |
| | `cello` | Violonchelo | Cuerda frotada grave con caja de resonancia | 42 | FLEX Strings (gratis: Spitfire LABS) |
| Batería (9) | `acoustic_kit` | Kit Acústico / Swing | Bombo con barrido, caja tono+ruido, ride, wood blocks, cencerro | — | FPC |
| | `chip_kit` | Kit 8-bit (NES) | Bombo de triángulo, ruido LFSR de 15 bits del chip 2A03 | — | FPC + Magical 8bit Plug |
| | `trap_808_kit` | Kit Trap 808 | 808 largo, clap de 3 ráfagas, hats nítidos | — | FPC (808 Kit) |
| | `lofi_kit` | Kit Lo-fi | Kit acústico reducido a 12 bits con paso bajo | — | FPC + Fruity Squeeze |

Todos los instrumentos salen normalizados a un nivel por rol (`ROLE_LEVEL`) para que la mezcla
quede balanceada antes del máster a -14 LUFS / -1 dBFS.

## 2. Elección automática a partir de los temas de YouTube

Además de tempo y tonalidad, el análisis de cada fuente mide tres rasgos de timbre
(`measure_timbre`), que se guardan en el ADN (`brightness_hz`, `bass_ratio`, `percussiveness`):

| Medida | Cómo se calcula | Referencias |
|---|---|---|
| Brillo | Centroide espectral hasta 8 kHz | música comercial ≈ 1500-3000 Hz |
| Graves | Energía < 150 Hz sobre el total | trap/808 > 0.6 |
| Percusión | Máscara suave P/(H+P) de la separación armónico-percusiva | leads sostenidos ≈ 0.25, pads ≈ 0.4, baterías 0.6-0.7 |

`suggest_instruments` aplica reglas simples y explicables (la UI muestra la razón de cada elección):

- **Estilo PvZ (Shigihara):** celesta FM en menor con fuente oscura, o pulso 8-bit; órgano gótico
  (menor) o cuerdas (mayor); contrabajo pulsado (walking bass) o tuba (oom-pah); kit acústico de swing.
- **Seguir la fuente:** fuente brillante → saw lead; oscura → flauta; ambiental → celesta y coro;
  tempo trap con graves fuertes → sub 808 y kit 808; tempo de pista con fuente brillante → bajo ácido;
  fuente brillante y liviana → kit 8-bit.

Lo que el usuario fija a mano en el rack tiene prioridad; los módulos en **AUTO** usan la sugerencia.
En el Compositor (sin fuentes) AUTO usa el rack clásico (`DEFAULT_RACK`).

## 3. FL Studio

El MIDI maestro y cada stem llevan el `program_change` General MIDI del instrumento elegido, y
`FL_Studio_Routing_Guide.json` indica el plugin nativo sugerido por canal, para recrear el sonido
con sintetizadores de FL Studio y seguir editando.

## 4. Detección de tonalidad robusta al timbre

Un coro o una tuba refuerzan armónicos concretos (formantes) y engañaban al detector de tonalidad
del check de similitud. Por eso el cromagrama (`compute_chroma`) ahora usa **saliencia armónica**:
cada nota candidata (C3-F6) suma la energía de sus 6 primeros armónicos con peso decreciente,
después de quitar la batería (HPSS) y con la misma resolución en Hz a cualquier sample rate. En las
pruebas con sintes del motor acertó la tonalidad (o su relativa/vecina) en todas las combinaciones
de rack, y el umbral de afinidad tonal se recalibró a 0.45.
