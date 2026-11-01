# Fusión Armónica Multi-Link

Convierte **uno o varios links** (YouTube u otros soportados por `yt-dlp`) y/o **temas ya
descargados** (WAV, MP3, M4A, FLAC, OGG…) en **un tema original**
que se siente parecido a las fuentes (tempo, tonalidad, color armónico) pero que no comparte con
ellas ni audio ni melodía. Con varios links, el resultado es un tema "mezclado" en el que cada
fuente tiene su sección, todas unidas con movimiento por cuartas del círculo de quintas.

- Código: `motor_musica/harmonic_fusion.py`, `motor_musica/content_id_checks.py`,
  utilidades de teoría en `motor_musica/theory.py`.
- API: `POST /api/harmonic-fusion`.
- UI: pestaña **Fusión Armónica Multi-Link** en `templates/index.html`.
- Tests: `tests/test_harmonic_fusion.py`, `tests/test_fusion_api.py`.

---

## 1. Flujo

```
links ──► análisis (30 s por fuente) ──► plan armónico ──► MIDI 4 canales ──► WAV -14 LUFS ──► checks
            tempo, tonalidad, croma        círculo de        leitmotiv propio    síntesis        huella,
            (el audio se descarta)         quintas                               NumPy           similitud,
                                                                                                 sonoridad
```

1. **Análisis.** De cada link se descargan ~30 s, se miden tempo (autocorrelación del flujo
   espectral), tonalidad (Krumhansl-Schmuckler sobre un croma armónico, sin batería) y un perfil
   12-croma. El archivo temporal se borra al terminar. **Nada del audio de la fuente entra en la
   composición.**
2. **Plan.** Se elige una tonalidad *hogar* (la que queda más cerca de todas las fuentes en el
   círculo de quintas) y un tempo común (mediana, plegando medio tiempo/doble tiempo). Cada fuente
   recibe una sección en **su propia tonalidad**; entre secciones hay puentes de dominantes.
3. **Composición.** Se genera un motivo de 2 compases (pregunta / respuesta) que viaja por todas
   las secciones: es lo que hace que la mezcla suene a *una* canción y no a un collage.
4. **Render y checks.** Síntesis procedural a -14 LUFS / -1 dBFS y verificación automática
   (sección 4). Se guarda el plan en `output/metadata/fusion_plans/<ISRC>.json` para reconstruir
   el proyecto de FL Studio nota por nota.

Forma resultante (ejemplo con 3 links en La menor, Sol mayor y Re menor):

```
Intro (Am) │ Tema A (Am) │ Puente V7 │ Tema B (G) │ Puente V7 │ Tema C (Dm) │ Puente V7 │ Cierre iv-V7-i (Am)
```

---

## 2. Lo que dijo Laura Shigihara sobre la música de *Plants vs. Zombies*

Laura Shigihara compuso la banda sonora de *Plants vs. Zombies* (PopCap, 2009). En entrevistas de
la época explicó su proceso. Resumen (parafraseado, con citas cortas):

| Lo que dijo | Fuente |
|---|---|
| Jugó las primeras versiones del juego antes de escribir y lo recorrió varias veces para captar su tono. | Audiogang, Game Developer |
| Identificó tres ejes de estilo: **lo macabro, lo tierno (cute) y el humor exagerado**. | Audiogang |
| Para lo macabro usó "Gothic-Classical elements (lots of half steps, minor scales, etc.)": muchos semitonos y escalas menores. | Audiogang |
| Para lo tierno escribió melodías y armonías pegadizas inspiradas en el pop y en la música de NES/SNES. | Audiogang |
| Para el humor usó "wacky percussion combinations": combinaciones de percusión raras. | Audiogang |
| Mezcló instrumentación gótico-clásica con **ritmos de swing de big band**; en el nivel nocturno, big band y swing contra melodías serias y "embrujadas". Otro nivel usa percusión de banda de marcha. | Audiogang, Game Developer |
| Resumió el tono como "macabre... but goofy" y lo comparó con la mezcla melódica y "funky" de Danny Elfman, frente al típico sonido de terror (cuerdas, semitonos, piano suave, pizzicato). | Game Developer |
| Admira a los compositores de NES/SNES: con poco espacio, la creatividad tenía que estar en la composición y no en los samples; de ahí melodías tan pegadizas. | Game Developer, Inven Global |
| La buena música de juego es la que "you never get tired of even in a loop": no cansa aunque se repita. | Inven Global |
| Compone con el juego corriendo de fondo para comprobar que la música encaja; la música demasiado intensa puede confundir al jugador. | Inven Global |

Fuentes:
- [Interview with "Plants Vs. Zombies" composer, Laura Shigihara — Audiogang](https://www.audiogang.org/interview-with-plants-vs-zombies-composer-laura-shigahara)
- [Interview: The Terrifying True Story of the Plants vs. Zombies Soundtrack — Game Developer (2009)](https://www.gamedeveloper.com/game-platforms/interview-the-terrifying-true-story-of-the-i-plants-vs-zombies-i-soundtrack)
- [Laura Shigihara, a composer who uses heartwarming music… — Inven Global](https://www.invenglobal.com/articles/4077/laura-shigihara-a-composer-who-uses-heartwarming-music-to-create-a-bond-between-the-player-and-the-game)

### Cómo se aplica en el motor (estilo `pvz_gotico_swing`)

| Principio | Implementación |
|---|---|
| Macabro: escalas menores y semitonos | Modo menor con **menor armónica en la dominante** (sensible elevada, V7). Bordaduras cromáticas: notas débiles del motivo que caen un semitono debajo de la siguiente nota fuerte. El walking bass llega a cada acorde por semitono. |
| Tierno: melodía pegadiza estilo NES/SNES | Motivo corto de 2 compases con **una celda rítmica repetida** (pregunta y respuesta), movimiento por grados, notas del acorde en tiempos fuertes, forma de frase **A-A-B-A** (B = contorno invertido). Lead de onda cuadrada/pulso. |
| Humor: percusión rara | Wood block, cencerro y claves sintetizados en el último contratiempo de cada 2 compases. |
| Gótico-clásico + swing de big band | Ride de swing ("ding, ding-da-ding") con corcheas en proporción 2:1, caja y charles en 2 y 4, **pizzicato en 2 y 4** (guiño a Elfman) sobre un fondo de órgano/cuerdas suave. |
| Banda de marcha | Redoble de caja antes de cada cambio de sección. |
| No cansar en loop | Secciones que cierran en la tónica, el mismo motivo transportado (reconocible pero variado) e intensidad contenida en intro/cierre. |
| Creatividad en la composición, no en los samples | Igual que la regla de oro de Content ID: todo es MIDI generado y síntesis NumPy. |

El estilo `seguir_fuente` conserva el mismo motor armónico pero con groove recto según el tempo
(medio tiempo tipo trap ≥130 BPM, boom bap ≤95 BPM, 4x4 en medio) y **v menor modal** en lugar de
V7, para respetar el color de géneros modernos.

---

## 3. Teoría: círculo de quintas y "ley de cuartas"

### Por qué cuartas

Subir una cuarta justa (5 semitonos) es lo mismo que bajar una quinta. Es el movimiento de
fundamental más fuerte de la armonía tonal: V→I, ii→V, vi→ii. Una cadena de acordes que suben
por cuartas genera tensión y resolución continua; es el motor de las secuencias barrocas, del
jazz (ii-V-I) y de muchas melodías de videojuegos.

### Dentro de cada sección

Las progresiones (`CIRCLE_PROGRESSIONS` en `theory.py`) recorren el ciclo diatónico de cuartas:

- Menor: `i → iv → VII → III → VI → ii° → V7 → i` (ciclo completo), `i-iv-V-i | VI-ii°-V-i`, …
- Mayor: `I → IV → vii° → iii → vi → ii → V → I`, `I-vi-ii-V`, …

En menor, el V usa la **menor armónica** (sensible) para que V7→i resuelva con fuerza.

### Entre secciones (modulación)

- Cada tonalidad tiene una posición en el círculo (las menores se ubican con su relativa mayor:
  La menor = Do mayor = posición 0).
- `fourths_path(origen, destino)` devuelve las tonalidades intermedias por el camino más corto.
- El puente toca **la dominante (V7) de cada tonalidad del camino**. Como el V7 de la tonalidad
  que está una cuarta arriba tiene como fundamental la tónica actual, cada acorde del puente
  resuelve una cuarta arriba hacia el siguiente: La menor → **A7** → Re → **D7** → Sol → … → destino.
- Si dos fuentes están en la misma tonalidad, un compás de V7 vuelve a preparar la entrada.
- La melodía del puente es la primera mitad del motivo **secuenciada** sobre cada dominante.

### Tonalidad hogar y tempo

- Hogar = tonalidad que minimiza la suma de distancias en el círculo a todas las fuentes (modo por
  mayoría; empate → menor). Intro y cierre están en el hogar.
- Tempo común = mediana de los tempos, plegando cada uno a ±√2 del primero (70 y 140 BPM cuentan
  como el mismo pulso).

---

## 4. Checks de publicación

Cada fusión devuelve un reporte (`report.checks`) que la UI muestra como `[OK]` / `[XX]`.
`aprobado = true` solo si todos pasan.

| Check | Qué mide | Criterio |
|---|---|---|
| `sonoridad_lufs` | Sonoridad integrada ITU-R BS.1770 | -14 LUFS ±2 LU |
| `true_peak` | Pico de muestra | ≤ -1.0 dBFS |
| `sin_clipping` | Muestras a escala completa | 0 |
| `cero_samples` | Composición 100 % desde eventos MIDI sintetizados | siempre verdadero por construcción |
| `huella_content_id[fuente N]` | Huella acústica por constelaciones de picos (mismo principio que Content ID/Shazam): fracción de hashes del tema que coinciden con la fuente en un mismo desfase | < 15 % (la misma grabación desplazada da ~50–90 %; temas distintos ~4 %) |
| `similitud_fuente[fuente N]` | Tonalidad medida en la sección de esa fuente vs tonalidad de la fuente, y afinidad tonal (correlación de los vectores de 24 tonalidades) | misma tónica o ≤1 paso en el círculo, afinidad ≥ 0.45, tempo ≤ 8 % (con una sola fuente; en fusiones el tempo es común y se informa) |

El máster ahora compensa la pérdida de sonoridad del limitador (hasta 4 iteraciones) para llegar
de verdad a -14 LUFS sin pasar -1 dBFS.

### Límites honestos

- La huella es una **aproximación** al método de Content ID; el sistema real de YouTube es
  privado. Que pase este check reduce el riesgo pero no es una garantía.
- La sonoridad sigue ITU-R BS.1770-4 (filtro K y bloques de 400 ms con puertas -70 / -10 LU),
  como YouTube o Spotify, pero no es un medidor certificado. El pico es por muestra, no true peak
  con sobremuestreo.
- Tempo y tonalidad no son protegibles por derechos de autor; melodía, letra y grabación sí. Por
  eso el motor solo toma tempo, tonalidad y color armónico, y escribe su propio motivo.

---

## 5. Uso

### UI

1. `python app.py` y abrir `http://127.0.0.1:5055`.
2. Pestaña **Fusión Armónica Multi-Link** → pegar links (uno por línea) y/o elegir temas
   descargados en "Temas descargados" (hasta 5 fuentes en total). Los archivos subidos se borran
   apenas se miden.
3. Elegir estilo, compases por sección y número de variación (mismos links + otra variación =
   otro tema publicable).
4. **Analizar y Fusionar**: aparece el círculo de quintas con fuentes (ámbar), hogar (blanco) y
   la ruta; la tira de arreglo con las secciones; y el reporte de checks. El tema queda en el
   catálogo con ISRC, WAV, MIDI y paquete de FL Studio.

### API

```http
POST /api/harmonic-fusion
Content-Type: application/json

{
  "urls": ["https://www.youtube.com/watch?v=...", "https://youtu.be/..."],
  "style": "pvz_gotico_swing",        // o "seguir_fuente"
  "bars_per_section": 8,              // 4..16
  "variation": 0,
  "title": ""                          // opcional
}
```

Para subir temas descargados se usa `multipart/form-data` con los mismos campos (`urls` como texto,
un link por línea) más uno o varios campos `files`.

Respuesta: `sources` (tempo/tonalidad detectados), `plan` (hogar, BPM, ruta, secciones),
`report` (checks) y `track` (ficha del catálogo).

### Python

```python
from motor_musica.harmonic_fusion import analyze_sources, create_harmonic_fusion

sources = analyze_sources(["https://youtu.be/...", "https://youtu.be/..."])
result = create_harmonic_fusion(sources, "out.mid", "out.wav", bars_per_section=8)
print(result.plan.circle_route, result.report["aprobado"])
```
