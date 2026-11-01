# Guía del Workflow — Crear un tema en 3 pasos y editarlo sin salir de la app

Esta guía explica cómo usar el programa para sacar temas rápido. La idea es simple:
**crear → escuchar → retocar → descargar**. Todo lo demás (pestañas de la derecha marcadas
como *AVANZADO*) es opcional.

```
 ★ Crear Tema Rápido  ──►  ✎ Editar Tema  ──►  ♫ Mis Temas (WAV / MIDI / FL Studio / Contrato)
   1 idea · 2 sonido · 3 crear    instrumentos, mezcla,       descargar y publicar
                                  tono, tempo, melodía
```

> **¿Tienes una playlist de referencia?** La pestaña **☰ Importar Playlist** mide cada tema de una
> playlist de YouTube (también no listada), los agrupa por género y crea un tema original parecido
> por canción o por género. Ver `IMPORTAR_PLAYLIST.md`.

## 1. Arrancar

```bash
pip install -r requirements.txt
python app.py            # abre http://127.0.0.1:5055
```

La app se abre directamente en **★ Crear Tema Rápido**.

## 2. Crear un tema (pestaña ★ Crear Tema Rápido)

### Paso 1 — ¿De dónde sale la idea?

| Opción | Qué hace |
|---|---|
| **🔗 De links o archivos** | Pega de 1 a 5 links (uno por línea) y/o sube temas descargados (wav, mp3, m4a, flac, ogg...). El motor mide tempo, tonalidad y timbre de cada uno. Con varias fuentes compone una **fusión armónica**: una sección en la tonalidad de cada fuente, unidas por el círculo de quintas (ver `FUSION_ARMONICA.md`). |
| **🎲 Sin fuente** | Eliges un estilo (rock, trap, lofi, synthwave, cinemático, boom bap) y el motor compone desde cero. |

El audio de los links **solo se mide y se borra**: ninguna nota ni muestra pasa al tema nuevo.

### Paso 2 — Elige el sonido

Un clic elige los cuatro instrumentos (melodía, armonía, bajo, batería):

| Paquete | Instrumentos |
|---|---|
| **AUTO** | Con links: elige según el brillo, los graves y la percusión medidos en tus fuentes. Sin fuente: rack por defecto. |
| Gótico-tierno (PvZ) | Celesta FM, órgano, contrabajo pulsado, kit swing |
| Orquestal | Violín solista, cuerdas, chelo, kit acústico |
| Rock | Guitarra limpia, power chords distorsionados, bajo eléctrico |
| Acústico | Guitarra punteada, guitarra rasgueada, contrabajo, kit acústico |
| Lo-fi | Piano, pad cálido, bajo eléctrico, kit lo-fi |
| Trap | Celesta FM, coro, sub 808, kit trap 808 |
| Synthwave | Supersaw, pad cálido, bajo ácido 303, kit acústico |
| 8-bit / Chiptune | Pulso NES, metales, bajo sintetizado, kit 8-bit (NES) |
| Piano Bar | Piano, metales, contrabajo, swing |

Todos son **sintetizadores procedurales** (fórmulas matemáticas: Karplus-Strong para cuerdas
pulsadas, arco simulado para violín/chelo, FM, aditiva con filtro, formantes para coro...).
No hay samples dentro del programa.

### Paso 3 — Crear

Elige **Corto / Medio / Largo** (8, 16 o 32 compases; en fusiones 4, 8 o 16 por sección),
un título opcional y pulsa **♫ CREAR TEMA**. En unos segundos aparece:

- el veredicto **✓ APTO PARA PUBLICAR** con todos los checks (sonoridad -14 LUFS, pico ≤ -1 dBFS,
  sin clipping, cero samples y, si hubo links, huella Content ID < 15% y similitud tonal),
- botones **✎ Editar este tema**, **💾 WAV**, **🎹 MIDI**, **FL Studio** y **🎲 Otra versión**
  (mismas fuentes y sonido, otra composición).

## 3. Editar el tema (pestaña ✎ Editar Tema)

Arriba eliges el tema (o llegas con **✎ Editar** desde el resultado o desde *Mis Temas*).
Verás el **piano roll** con las cuatro pistas en colores y una mesa de 4 canales:

| Control | Qué cambia |
|---|---|
| Selector de instrumento (agrupado por familia: Guitarras, Cuerdas, Teclados, Sintetizadores, 8-bit, Vientos, Voces, Percusión afinada, Baterías) | El timbre de la pista. **▶** lo prueba antes de aplicar. |
| Deslizador de volumen (0-200%) | El nivel de la pista en la mezcla. |
| **Silenciar** | Quita la pista (p. ej. tema sin batería). No se pueden silenciar las 4. |
| **Transponer − / +** | Sube o baja todo el tema en semitonos (±12). La batería no se transpone. |
| **Tempo** | 60-180 BPM. Se reescribe el MIDI al nuevo tempo (no es un estiramiento de audio). |
| **🎲 Nueva melodía** | Otra melodía sobre la misma armonía y forma. |

Luego:

- **⟳ Aplicar y escuchar** crea la versión siguiente del mismo tema (`_v2`, `_v3`...) con el mismo ISRC
  y la reproduce. Las versiones anteriores siguen en la carpeta `output/`.
- **＋ Guardar como tema nuevo** guarda el resultado como otro tema (ISRC nuevo) y deja el original intacto.

Cada render vuelve a pasar los checks de master. Si transpones una fusión aparece una nota
informativa: el tema se aleja de la tonalidad de las fuentes (es aún más original, no menos).

## 4. Descargar y llevar a FL Studio (pestaña ♫ Mis Temas)

- **WAV**: master final, listo para subir.
- **MID**: las 4 pistas en un MIDI multipista (canales 0 armonía, 1 melodía, 2 bajo, 9 batería) con
  el programa General MIDI de cada instrumento elegido.
- **FL Studio**: un .zip con stems MIDI por pista, guía de ruteo y el plugin sugerido para cada canal.
  Si editaste el tema, el paquete se regenera con la última versión.
- **Doc**: contrato de licencia del tema.

### Ida y vuelta con FL Studio

1. Descarga el paquete **FL Studio** y abre el MIDI maestro (o arrastra cada stem a su canal).
2. Carga en cada canal el plugin sugerido (ver tabla de abajo). Puedes cambiar notas, añadir efectos, etc.
3. Exporta tu WAV. Ese WAV ya no lo genera el motor, así que antes de publicar comprueba tú mismo
   -14 LUFS y pico ≤ -1 dBFS (FL Studio: *Wave Candy* / medidor de sonoridad, o el plugin gratuito
   *Youlean Loudness Meter*).

## 5. Instrumentos gratuitos y legales para seguir en FL Studio

Regla de oro del proyecto: **instrumentos sí, loops y frases grabadas no**. Un instrumento que toca
*tus* notas (sintetizador o librería de notas sueltas) es seguro. Un loop, una frase melódica o un
"construction kit" puede estar registrado en Content ID por otra persona y provocar reclamaciones.

| Herramienta (gratis) | Tipo | Para qué canal | Notas de licencia |
|---|---|---|---|
| Plugins incluidos en FL Studio (3x Osc, FLEX, FL Keys, Fruity DX10, BooBass, FPC) | Sintes / teclado / batería | Todos | Vienen con tu licencia de FL Studio. Ojo con los *presets* de FLEX/FPC que traen loops: usa solo notas sueltas. |
| **Vital** (versión gratuita) | Sintetizador wavetable | Lead, pad, bajo, supersaw | Sintetizador: todo el sonido lo generas tú. |
| **Surge XT** | Sintetizador (código abierto, GPL) | Lead, pad, bajo, ácido | Código abierto, uso comercial libre. |
| **Spitfire LABS** | Instrumentos muestreados por nota (cuerdas, piano, guitarras, coros...) | Violín, cuerdas, chelo, coro, piano | Gratis con cuenta; permite uso en música propia. Lee la licencia vigente antes de publicar. |
| **Piano One** (Sound Magic) | Piano muestreado | Piano | Gratuito. |
| **Decent Sampler** + bibliotecas gratuitas de Pianobook | Reproductor de instrumentos por nota | Cualquiera | Cada biblioteca tiene su licencia: elige las que permitan uso comercial. |

Evita: packs de loops (Splice, Cymatics, Looperman...), "construction kits", stems de otras canciones,
y cualquier archivo que suene como una frase completa en vez de una nota.

## 6. Si algo no sale

| Mensaje | Qué hacer |
|---|---|
| *Pega un link o sube un archivo* | En el paso 1 no hay fuentes. Pega un link o pulsa **🎲 Sin fuente**. |
| *Máximo 5 fuentes* | Quita links o archivos. |
| *Formato no soportado* | Sube wav, mp3, m4a, aac, flac, ogg, opus o webm. |
| Error al descargar un link de YouTube | Descarga el audio por tu cuenta y súbelo como archivo. |
| *No se pueden silenciar las 4 pistas* | Deja al menos una pista sonando. |
| *Este tema no tiene proyecto editable* | Temas creados con versiones antiguas o mezclas DJ no se pueden editar; vuelve a crearlo. |
| ✗ REVISAR ANTES DE PUBLICAR | Mira qué check falló: huella alta → **🎲 Otra versión**; similitud baja → prueba otro paquete o menos fuentes. |

## 7. Publicar

Dónde publicar (no solo YouTube) y cómo registrar los temas se trata en un plan aparte.
Antes de cualquier plataforma, el tema tiene que mostrar **✓ APTO PARA PUBLICAR** en la app.
