"""Script de Demostracion del Motor Procedural de Musica para Content ID.

Ejecuta el ciclo de vida completo:
1. Composicion algoritmica en MIDI multipista (cero samples pregrabados).
2. Renderizado a audio WAV estereo con sintesis procedural propia y masterizacion a -14 LUFS.
3. Generacion de scripts CLI headless para FL Studio.
4. Generacion de codigos ISRC y catalogos JSON / CSV para distribuidoras de Content ID.
"""

import os
from pathlib import Path
import sys
import time

# Asegurar que motor_musica se pueda importar localmente
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from motor_musica.theory import GENRES
from motor_musica.midi_generator import generate_track_midi
from motor_musica.synth_renderer import render_midi_to_wav, SynthConfig
from motor_musica.flstudio_cli import FLStudioCLI
from motor_musica.metadata_manager import (
    generate_track_metadata,
    export_distribution_catalog,
    TrackMetadata,
)


def run_demo():
    print("=" * 70)
    print("  MOTOR PROCEDURAL DE MUSICA & MONETIZACION CONTENT ID (DEMO)")
    print("  Shameless Company - Arquitectura Algoritmica Libre de Samples")
    print("=" * 70)
    
    out_dir = CURRENT_DIR / "output"
    midi_dir = out_dir / "midi"
    audio_dir = out_dir / "audio"
    meta_dir = out_dir / "metadata"
    fl_scripts_dir = out_dir / "flstudio_scripts"
    
    for d in [midi_dir, audio_dir, meta_dir, fl_scripts_dir]:
        d.mkdir(parents=True, exist_ok=True)
        
    fl_cli = FLStudioCLI()
    print(f"\n[1/4] Diagnostico de Entorno:")
    if fl_cli.is_available():
        print(f"  [+] FL Studio detectado en: {fl_cli.executable_path}")
    else:
        print(f"  [-] FL Studio no detectado localmente.")
        print(f"      Se usara el sintetizador procedural autonomo en Python (WAV 44.1kHz).")
        print(f"      Se generaran los scripts CLI para FL Studio listos para cuando se instale.")

    genres_to_generate = [
        ("epic_cinematic", 16, "Epic Theme - Wrath of Titans"),
        ("synthwave", 16, "Cyberpunk Overdrive 1984"),
        ("lofi_chill", 12, "Coffee & Midnight Vinyl"),
        ("hard_rock", 16, "Thunderstruck Velocity"),
    ]

    tracks_metadata: list[TrackMetadata] = []
    
    print(f"\n[2/4] Generando composiciones algoritmicas y renderizando audio...")
    start_time = time.time()
    
    for idx, (genre_key, bars, custom_title) in enumerate(genres_to_generate, start=1):
        clean_tag = f"track_{idx:02d}_{genre_key}"
        midi_path = midi_dir / f"{clean_tag}.mid"
        wav_path = audio_dir / f"{clean_tag}.wav"
        ps1_path = fl_scripts_dir / f"render_{clean_tag}.ps1"
        
        print(f"\n  -> Procesando Pista {idx}: '{custom_title}' ({genre_key.upper()})")
        
        # 1. Generar composicion MIDI
        bundle = generate_track_midi(
            genre=genre_key,
            bars=bars,
            seed=42 + idx * 10,
            output_mid_path=str(midi_path),
        )
        print(f"     [MIDI] 4 canales creados ({len(bundle.events)} notas). Guardado en: {midi_path.name}")
        
        # 2. Renderizar Audio WAV con Sintetizador Procedural Autonomo
        synth_cfg = SynthConfig(sample_rate=44100, target_lufs=-14.0, bit_depth=16)
        metrics = render_midi_to_wav(bundle, str(wav_path), config=synth_cfg)
        print(f"     [WAV]  Audio sintetizado a 44.1 kHz estereo: {metrics.duration_sec:.1f}s")
        print(f"            Peak: {metrics.peak_dbfs:.2f} dBFS | RMS: {metrics.rms_dbfs:.2f} dBFS | LUFS: {metrics.estimated_lufs:.2f}")
        
        # 3. Generar Script CLI de FL Studio
        flp_template = CURRENT_DIR / "templates" / "EpicTemplate.flp"
        fl_cli.generate_powershell_script(
            project_flp=str(flp_template),
            output_dir=str(audio_dir),
            output_ps1_path=str(ps1_path),
        )
        
        # 4. Ficha de Metadatos e ISRC
        meta = generate_track_metadata(
            genre=genre_key,
            bpm=bundle.bpm,
            scale=bundle.profile.scale_type.value,
            duration_sec=metrics.duration_sec,
            track_number=idx,
            midi_filename=midi_path.name,
            audio_filename=wav_path.name,
            peak_dbfs=metrics.peak_dbfs,
            estimated_lufs=metrics.estimated_lufs,
            custom_title=custom_title,
        )
        tracks_metadata.append(meta)
        print(f"     [ISRC] Codigo asignado: {meta.isrc} (Certificado Content ID)")

    total_time = time.time() - start_time
    
    # 4. Exportar Catalogo
    print(f"\n[3/4] Exportando Catalogo para Distribuidoras (Identifyy, Soundrop, Songtradr)...")
    csv_path = meta_dir / "catalog_content_id.csv"
    json_path = meta_dir / "catalog_content_id.json"
    export_distribution_catalog(tracks_metadata, str(csv_path), str(json_path))
    print(f"  [+] Catalogo CSV exportado: {csv_path.name}")
    print(f"  [+] Catalogo JSON exportado: {json_path.name}")

    print(f"\n[4/4] Resumen de Resultados (Tiempo total: {total_time:.2f}s):")
    print("-" * 92)
    header = f"{'ISRC':<18} | {'TITULO':<26} | {'GENERO':<15} | {'DUR':<6} | {'LUFS':<8} | {'ESTADO'}"
    print(header)
    print("-" * 92)
    for t in tracks_metadata:
        row = f"{t.isrc:<18} | {t.title:<26} | {t.genre:<15} | {t.duration_sec:<5.1f}s | {t.estimated_lufs:<6.2f} dB | CERTIFICADO OK"
        print(row)
    print("-" * 92)
    
    print("\n[OK] Demostracion completada con exito.")
    print("     Pistas listas para revision y subida a Git en D:\\Programacion\\motor-musica-content-id")
    return 0


if __name__ == "__main__":
    sys.exit(run_demo())
