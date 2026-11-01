# Importar Playlist — clasificar por género y componer temas parecidos

Pestaña **☰ Importar Playlist**. Pegas el link de una playlist de YouTube (pública o
**no listada**: basta con tener el link), el motor mide cada tema, lo clasifica por género
y compone temas **originales** parecidos, listos para editar en **✎ Editar Tema** o en FL Studio.

```
 link de playlist ──► medir ~30 s de cada tema ──► género + ficha de estilo ──► 1 tema nuevo
                      (el audio se borra)          (corregible a mano)         por canción o por género
```

## Qué se extrae y qué no

| Se extrae (no protegible) | NO se extrae (protegido) |
|---|---|
| Tempo (BPM) | Melodía |
| Tonalidad y modo (mayor / menor) | Letra |
| Brillo (centroide espectral) | Partitura / riff / línea de bajo |
| Peso de graves (< 150 Hz) | Audio, loops o samples |
| Percusividad (HPSS) | |
| Densidad rítmica (golpes por segundo) | |
| Energía (RMS) | |
| Huella acústica (hashes, solo para comparar) | |

Transcribir la melodía o la partitura de un tema y reutilizarla haría una **obra derivada**:
no se puede monetizar y Content ID la reclamaría. Por eso el motor compone cada tema nuevo
desde cero con el compositor del género, y solo lo lleva al **tempo y la tonalidad** medidos.

## Paso 1 — Analizar

1. Pega el link (`https://www.youtube.com/playlist?list=...`). Un link de un solo video también sirve.
2. Elige cuántos temas medir (5, 10, 15 o 25; se toman los primeros de la lista).
3. **⇩ Analizar playlist**. Cada tema tarda unos segundos (descarga, mide y borra). Un video
   privado o borrado se marca y no frena al resto.

El resultado se guarda en `output/metadata/playlists/<id>.json` (sin audio) y la app recuerda
la última playlist al recargar.

## Clasificación por género

Cada tema se compara con un prototipo de los 6 géneros del motor (tempo, modo, brillo, graves,
percusión, densidad rítmica). El tempo pesa más, y se acepta medio/doble tiempo (un trap a 140
a veces se mide a 70). Si los dos primeros géneros quedan muy parejos aparece un **?** rojo.

Es una **estimación por reglas**, no un reconocedor perfecto: si no te convence, cambia el
género en la lista y se usa el que elijas (AUTO vuelve a la estimación).

## Paso 2 — Componer

| Modo | Qué crea |
|---|---|
| **1 tema nuevo por cada canción marcada** | Un tema por fila marcada, en el género, tempo y tonalidad de esa canción. |
| **1 tema nuevo por cada género** | Un tema por género presente entre las filas marcadas, con el tempo mediano y la tonalidad del grupo. |

Sonido **AUTO** = el paquete típico del género (lo-fi → piano y kit lo-fi, trap → 808, rock →
guitarras, cinemático → orquesta, synthwave → supersaw, boom bap → piano, metales y contrabajo).
Cualquier paquete del rack lo reemplaza.

Cada tema nuevo pasa los checks habituales (-14 LUFS, pico ≤ -1 dBFS, cero samples) más:

- `similitud_fuente`: misma tonalidad (o vecina) y tempo a ≤ 8 %,
- `huella_content_id[#N]`: coincidencia de huella < 15 % contra **cada** canción de origen.

Todos los temas quedan en **♫ Mis Temas** con su proyecto editable (instrumentos, mezcla,
transponer, tempo, nueva melodía) y su paquete de FL Studio.

## API

| Endpoint | Uso |
|---|---|
| `POST /api/playlist/import` | `{url, limit}` → `{job_id}`. Analiza en segundo plano. |
| `GET /api/playlist/job/<job_id>` | `{status: running/done/error, done, total, current, playlist_id}` |
| `GET /api/playlist/<id>` | Temas, rasgos, género, ranking, grupos y temas generados. |
| `POST /api/playlist/<id>/genre` | `{index, genre}` (`genre: "auto"` vuelve a la estimación). |
| `POST /api/playlist/<id>/compose` | `{mode: per_track/per_genre, indices?, genres?, bars, pack?, instruments?}` |
