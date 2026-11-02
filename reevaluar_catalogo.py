"""Vuelve a medir los WAV del catálogo y recalcula content_id_certified con checks reales.

Hasta el 2026-11-01 el sello se escribía siempre en True. Este script mide cada WAV de
output/audio (sonoridad -14 LUFS, true peak, clipping) y reescribe el catálogo JSON/CSV
con el resultado. No cambia el audio ni los ISRC. La huella contra las fuentes de una
fusión no se recalcula aquí (hace falta el audio de las fuentes).

    python reevaluar_catalogo.py            # muestra el resultado sin escribir nada
    python reevaluar_catalogo.py --aplicar  # reescribe catalog_content_id.json y .csv
"""
import argparse
import json
from pathlib import Path

from motor_musica.content_id_checks import check_master
from motor_musica.metadata_manager import TrackMetadata, export_distribution_catalog, resumir_checks
from motor_musica.song_mixer import _read_wav_stereo
from motor_musica.synth_renderer import calculate_loudness_stats

RAIZ = Path(__file__).resolve().parent
META_DIR = RAIZ / "output" / "metadata"
AUDIO_DIR = RAIZ / "output" / "audio"


def reevaluar(item: dict) -> dict:
    wav = AUDIO_DIR / item["audio_filename"]
    nuevo = dict(item)
    if not wav.exists():
        nuevo.update(content_id_certified=False, content_id_checks="sin verificar (falta el WAV)")
        return nuevo
    audio, sr = _read_wav_stereo(str(wav))
    metrics = calculate_loudness_stats(audio, sr)
    checks = check_master(metrics)
    nuevo.update(
        content_id_certified=all(c.passed for c in checks),
        content_id_checks=resumir_checks(checks),
        peak_dbfs=round(metrics.peak_dbfs, 2),
        estimated_lufs=round(metrics.estimated_lufs, 2),
    )
    return nuevo


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--aplicar", action="store_true", help="reescribir el catálogo")
    a = p.parse_args()

    catalogo = json.loads((META_DIR / "catalog_content_id.json").read_text(encoding="utf-8"))
    nuevos = []
    for item in catalogo:
        n = reevaluar(item)
        nuevos.append(n)
        estado = "CERTIFICADO" if n["content_id_certified"] else "NO        "
        print(f"{estado}  {n['isrc']}  {n['audio_filename']:<34} LUFS {n.get('estimated_lufs')}  {n['content_id_checks']}",
              flush=True)
    ok = sum(n["content_id_certified"] for n in nuevos)
    print(f"\n{ok} de {len(nuevos)} temas pasan los checks del master.")

    if a.aplicar:
        campos = TrackMetadata.__dataclass_fields__.keys()
        export_distribution_catalog(
            [TrackMetadata(**{k: n[k] for k in campos if k in n}) for n in nuevos],
            str(META_DIR / "catalog_content_id.csv"),
            str(META_DIR / "catalog_content_id.json"),
        )
        print("Catálogo reescrito.")
    else:
        print("Simulación: nada escrito. Usa --aplicar para reescribir el catálogo.")


if __name__ == "__main__":
    main()
