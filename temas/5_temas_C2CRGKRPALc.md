# 5 temas originales a partir de youtu.be/C2CRGKRPALc

Fuente: "Rico Nasty - You Can't Run From Me (Cyberpunk: Edgerunners 2) (slowed & reverb)".
Se descargaron ~30 s, se midieron rasgos abstractos y el audio se borró. No se transcribió melodía ni letra.

**Rasgos medidos:** 109 BPM, C# menor, brillo 1761 Hz, graves 86 %, percusión 49 %, 5.6 golpes/s.
Género estimado: Epic Cinematic (0.52) con duda frente a Synthwave (0.46) y Dark Trap (0.46).

Los 5 temas comparten tempo (109 BPM) y tonalidad (C# menor) con la fuente; varían en género del compositor, paquete de sonido y semilla aleatoria. 32 compases, ~72 s cada uno.

| # | ISRC | Título | Género / sonido | Instrumentos | Pico |
|---|---|---|---|---|---|
| 1 | US-SHM-26-00010 | Savage Dynasty Trap | Dark Trap / AUTO (trap) | Celesta FM, coro, Sub 808, kit trap | -1.65 dBFS |
| 2 | US-SHM-26-00011 | VVS Diamond Frost | Dark Trap / Synthwave | Supersaw, pad cálido, bajo ácido 303, kit acústico | -1.56 dBFS |
| 3 | US-SHM-26-00013 | Echoes of Valhalla | Epic Cinematic / AUTO (orquestal) | Violín, cuerdas, chelo, kit acústico | -1.11 dBFS |
| 4 | US-SHM-26-00014 | Harlem Brownstone Soul | Boom Bap / AUTO | Piano, metales, contrabajo, kit lo-fi | -1.03 dBFS |
| 5 | US-SHM-26-00016 | Chronicles of the Iron Titan | Epic Cinematic / Synthwave | Supersaw, pad cálido, bajo ácido 303, kit acústico | -1.17 dBFS |

## Checks de Content ID (los 5 aprobados)

Todos pasan: sonoridad -14.0 LUFS, true peak ≤ -1 dBFS, sin clipping, cero samples,
parecido con la fuente (tonalidad a ≤ 1 paso y tempo a 0 %) y huella acústica < 15 % contra la fuente.

## Dónde están los archivos

Raíz: `D:\Programacion\motor-musica-content-id\output\`

| # | WAV (`audio\`) | MIDI (`midi\`) | FL Studio (`fl_packages\`) |
|---|---|---|---|
| 1 | playlist_10_dark_trap.wav | playlist_10_dark_trap.mid | Track_US_SHM_26_00010_FLStudio_Project.zip |
| 2 | playlist_11_dark_trap.wav | playlist_11_dark_trap.mid | Track_US_SHM_26_00011_FLStudio_Project.zip |
| 3 | playlist_13_epic_cinematic.wav | playlist_13_epic_cinematic.mid | Track_US_SHM_26_00013_FLStudio_Project.zip |
| 4 | playlist_14_boom_bap.wav | playlist_14_boom_bap.mid | Track_US_SHM_26_00014_FLStudio_Project.zip |
| 5 | playlist_16_epic_cinematic.wav | playlist_16_epic_cinematic.mid | Track_US_SHM_26_00016_FLStudio_Project.zip |

Cada ZIP trae el MIDI maestro, 4 stems MIDI (acordes, melodía, bajo, batería), la guía de ruteo y `Open_In_FLStudio.ps1`.
El proyecto editable de cada tema está en `metadata\projects\<ISRC>.json` y aparece en **♫ Mis Temas**.

## Lo que falló (para revisar en el motor)

- **Descarga de YouTube:** sin fallos. yt-dlp 2026.10.21 + ffmpeg bajaron y midieron el video a la primera.
- **Compositor Synthwave:** dos intentos (US-SHM-26-00012 y US-SHM-26-00015) no pasaron `similitud_fuente`:
  el audio se detectó en G# menor y F# mayor en vez de C# menor. El modo dórico de ese compositor parece mover
  el centro tonal que mide el detector. Quedaron en el catálogo marcados como no aprobados; no usarlos para distribuir.
  Se reemplazaron por el tema 5 (cinematográfico con sonido synthwave).
- **Clasificación ambigua:** el tema es rap/trap ralentizado y el motor lo estimó como cinematográfico; por eso se
  repartieron los 5 entre los géneros más cercanos del ranking.
- **Duración:** 32 compases a 109 BPM dan ~72 s. Para Content ID conviene subir a 64 compases (~2:20).
