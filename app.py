"""Servidor Web y Panel de Control Visual para el Motor de Musica Content ID.

Permite reproducir temas generados, visualizar audio en tiempo real con Web Audio API,
lanzar nuevas composiciones algoritmicas en vivo y descargar MIDIs, WAVs y metadatos ISRC.
"""

import json
import os
from pathlib import Path
import shutil
import sys

# Agregar la ruta raiz del proyecto a sys.path
PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from flask import Flask, jsonify, render_template, request, send_from_directory

from motor_musica.theory import GENRES
from motor_musica.midi_generator import generate_track_midi
from motor_musica.synth_renderer import render_midi_to_wav, SynthConfig
from motor_musica.flstudio_cli import FLStudioCLI
from motor_musica.metadata_manager import (
    generate_track_metadata,
    export_distribution_catalog,
    TrackMetadata,
)
from motor_musica.youtube_dna import (
    analyze_youtube_dna,
    compose_original_from_youtube_dna,
)
from motor_musica.license_generator import (
    LicenseTier,
    generate_beat_license_agreement,
)
from motor_musica.song_mixer import (
    crossfade_audio_tracks,
    blend_audio_tracks,
    stem_mashup_remix,
)
from motor_musica.fl_project_builder import (
    create_flstudio_editable_project,
)

app = Flask(__name__, template_folder=str(PROJECT_DIR / "templates"))

OUTPUT_DIR = PROJECT_DIR / "output"
AUDIO_DIR = OUTPUT_DIR / "audio"
MIDI_DIR = OUTPUT_DIR / "midi"
META_DIR = OUTPUT_DIR / "metadata"
FL_SCRIPTS_DIR = OUTPUT_DIR / "flstudio_scripts"
FL_PACKAGES_DIR = OUTPUT_DIR / "fl_packages"

for d in [AUDIO_DIR, MIDI_DIR, META_DIR, FL_SCRIPTS_DIR, FL_PACKAGES_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def _load_catalog():
    catalog_path = META_DIR / "catalog_content_id.json"
    if catalog_path.exists():
        try:
            with open(catalog_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


@app.route("/")
def index():
    fl_cli = FLStudioCLI()
    genres_list = [
        {"id": k, "name": v.name, "bpm": v.bpm, "style": v.drum_style}
        for k, v in GENRES.items()
    ]
    return render_template(
        "index.html",
        genres=genres_list,
        fl_available=fl_cli.is_available(),
        fl_path=fl_cli.executable_path or "No detectado (usando sintetizador procedural)",
    )


@app.route("/api/tracks", methods=["GET"])
def get_tracks():
    tracks = _load_catalog()
    return jsonify({"success": True, "tracks": tracks})


@app.route("/api/generate", methods=["POST"])
def generate_track():
    data = request.get_json() or {}
    genre = data.get("genre", "hard_rock")
    bars = int(data.get("bars", 16))
    custom_title = data.get("title", "").strip() or None
    
    if genre not in GENRES:
        genre = "hard_rock"
        
    catalog = _load_catalog()
    track_num = len(catalog) + 1
    clean_tag = f"track_{track_num:02d}_{genre}"
    
    midi_path = MIDI_DIR / f"{clean_tag}.mid"
    wav_path = AUDIO_DIR / f"{clean_tag}.wav"
    ps1_path = FL_SCRIPTS_DIR / f"render_{clean_tag}.ps1"
    
    # 1. Componer MIDI
    bundle = generate_track_midi(
        genre=genre,
        bars=bars,
        output_mid_path=str(midi_path),
    )
    
    # 2. Renderizar WAV
    cfg = SynthConfig(sample_rate=44100, target_lufs=-14.0, bit_depth=16)
    metrics = render_midi_to_wav(bundle, str(wav_path), config=cfg)
    
    # 3. Generar Script FL Studio
    fl_cli = FLStudioCLI()
    flp_template = PROJECT_DIR / "templates" / "EpicTemplate.flp"
    fl_cli.generate_powershell_script(
        project_flp=str(flp_template),
        output_dir=str(AUDIO_DIR),
        output_ps1_path=str(ps1_path),
    )
    
    # 4. Crear Metadatos ISRC
    new_meta = generate_track_metadata(
        genre=genre,
        bpm=bundle.bpm,
        scale=bundle.profile.scale_type.value,
        duration_sec=metrics.duration_sec,
        track_number=track_num,
        midi_filename=midi_path.name,
        audio_filename=wav_path.name,
        peak_dbfs=metrics.peak_dbfs,
        estimated_lufs=metrics.estimated_lufs,
        custom_title=custom_title,
    )
    
    # Actualizar catalogo
    catalog_objects = []
    for item in catalog:
        catalog_objects.append(
            TrackMetadata(
                title=item["title"],
                artist=item["artist"],
                genre=item["genre"],
                bpm=item["bpm"],
                scale=item["scale"],
                duration_sec=item["duration_sec"],
                isrc=item["isrc"],
                creation_date=item["creation_date"],
                content_id_certified=item["content_id_certified"],
                sample_packs_used=item["sample_packs_used"],
                composition_mode=item["composition_mode"],
                midi_filename=item["midi_filename"],
                audio_filename=item["audio_filename"],
                peak_dbfs=item.get("peak_dbfs"),
                estimated_lufs=item.get("estimated_lufs"),
            )
        )
    catalog_objects.append(new_meta)
    
    export_distribution_catalog(
        catalog_objects,
        str(META_DIR / "catalog_content_id.csv"),
        str(META_DIR / "catalog_content_id.json"),
    )
    
    return jsonify({
        "success": True,
        "track": {
            "title": new_meta.title,
            "artist": new_meta.artist,
            "genre": new_meta.genre,
            "bpm": new_meta.bpm,
            "scale": new_meta.scale,
            "duration_sec": new_meta.duration_sec,
            "isrc": new_meta.isrc,
            "midi_filename": new_meta.midi_filename,
            "audio_filename": new_meta.audio_filename,
            "peak_dbfs": new_meta.peak_dbfs,
            "estimated_lufs": new_meta.estimated_lufs,
        }
    })


@app.route("/api/youtube-dna", methods=["POST"])
def analyze_and_compose_youtube():
    data = request.get_json() or {}
    url = data.get("url", "").strip()
    custom_title = data.get("title", "").strip() or None
    bars = int(data.get("bars", 16))
    
    if not url:
        return jsonify({"success": False, "error": "URL de YouTube requerida"}), 400
        
    try:
        # 1. Extraer ADN de la cancion de YouTube (tempo, tono, modo)
        dna = analyze_youtube_dna(url)
        
        # 2. Componer obra 100% original a partir del ADN
        catalog = _load_catalog()
        track_num = len(catalog) + 1
        clean_tag = f"track_{track_num:02d}_{dna.genre_hint}"
        
        midi_path = MIDI_DIR / f"{clean_tag}.mid"
        wav_path = AUDIO_DIR / f"{clean_tag}.wav"
        
        meta, metrics = compose_original_from_youtube_dna(
            dna=dna,
            bars=bars,
            custom_title=custom_title,
            output_mid_path=str(midi_path),
            output_wav_path=str(wav_path),
            track_number=track_num,
        )
        
        # Actualizar catalogo
        catalog_objects = []
        for item in catalog:
            catalog_objects.append(
                TrackMetadata(
                    title=item["title"],
                    artist=item["artist"],
                    genre=item["genre"],
                    bpm=item["bpm"],
                    scale=item["scale"],
                    duration_sec=item["duration_sec"],
                    isrc=item["isrc"],
                    creation_date=item["creation_date"],
                    content_id_certified=item["content_id_certified"],
                    sample_packs_used=item["sample_packs_used"],
                    composition_mode=item["composition_mode"],
                    midi_filename=item["midi_filename"],
                    audio_filename=item["audio_filename"],
                    peak_dbfs=item.get("peak_dbfs"),
                    estimated_lufs=item.get("estimated_lufs"),
                )
            )
        catalog_objects.append(meta)
        
        export_distribution_catalog(
            catalog_objects,
            str(META_DIR / "catalog_content_id.csv"),
            str(META_DIR / "catalog_content_id.json"),
        )
        
        return jsonify({
            "success": True,
            "dna": {
                "detected_bpm": dna.detected_bpm,
                "detected_key": dna.detected_key,
                "confidence": dna.confidence,
                "genre_hint": dna.genre_hint,
            },
            "track": {
                "title": meta.title,
                "artist": meta.artist,
                "genre": meta.genre,
                "bpm": meta.bpm,
                "scale": meta.scale,
                "duration_sec": meta.duration_sec,
                "isrc": meta.isrc,
                "midi_filename": meta.midi_filename,
                "audio_filename": meta.audio_filename,
                "peak_dbfs": meta.peak_dbfs,
                "estimated_lufs": meta.estimated_lufs,
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/license/<isrc>", methods=["GET"])
def get_license_contract(isrc):
    tier_str = request.args.get("tier", "premium_wav")
    buyer_name = request.args.get("buyer", "Artista Licenciatario")
    
    tier_map = {
        "basic_mp3": LicenseTier.BASIC_MP3,
        "premium_wav": LicenseTier.PREMIUM_WAV,
        "trackout_stems": LicenseTier.TRACKOUT_STEMS,
        "exclusive_rights": LicenseTier.EXCLUSIVE_RIGHTS,
    }
    tier = tier_map.get(tier_str, LicenseTier.PREMIUM_WAV)
    
    catalog = _load_catalog()
    target_track = next((t for t in catalog if t["isrc"] == isrc), None)
    
    if not target_track:
        return jsonify({"success": False, "error": "Pista no encontrada"}), 404
        
    contract_text = generate_beat_license_agreement(
        beat_title=target_track["title"],
        buyer_name=buyer_name,
        tier=tier,
        bpm=target_track["bpm"],
        key_name=target_track["scale"],
        isrc=target_track["isrc"],
    )
    
    return jsonify({
        "success": True,
        "contract": contract_text,
        "tier": tier.value,
        "isrc": isrc,
    })


@app.route("/api/mix-tracks", methods=["POST"])
def mix_tracks_api():
    data = request.get_json() or {}
    isrc_a = data.get("isrc_a")
    isrc_b = data.get("isrc_b")
    mode = data.get("mode", "crossfade")  # crossfade, blend, mashup
    balance = float(data.get("balance", 0.5))
    crossfade_sec = float(data.get("crossfade_sec", 4.0))
    custom_title = data.get("title", "").strip() or None
    
    catalog = _load_catalog()
    track_a = next((t for t in catalog if t["isrc"] == isrc_a), None)
    track_b = next((t for t in catalog if t["isrc"] == isrc_b), None)
    
    if not track_a or not track_b:
        return jsonify({"success": False, "error": "Debes seleccionar dos pistas validas"}), 400
        
    wav_a = str(AUDIO_DIR / track_a["audio_filename"])
    wav_b = str(AUDIO_DIR / track_b["audio_filename"])
    
    track_num = len(catalog) + 1
    clean_tag = f"mix_{track_num:02d}_{mode}"
    out_wav = str(AUDIO_DIR / f"{clean_tag}.wav")
    out_mid = str(MIDI_DIR / f"{clean_tag}.mid")
    
    if mode == "mashup":
        # Mashup de stems MIDI
        bundle_a = generate_track_midi(genre=track_a["genre"], bars=16, seed=10)
        bundle_b = generate_track_midi(genre=track_b["genre"], bars=16, seed=20)
        title = custom_title or f"Mashup {track_a['title'][:15]} x {track_b['title'][:15]}"
        meta, metrics = stem_mashup_remix(
            bundle_a, bundle_b, out_mid, out_wav, custom_title=title, track_number=track_num
        )
    elif mode == "blend":
        # Dual Deck paralelo
        metrics = blend_audio_tracks(wav_a, wav_b, out_wav, balance_a_to_b=balance)
        title = custom_title or f"Dual Blend ({track_a['title'][:12]} + {track_b['title'][:12]})"
        # Usar MIDI de A
        shutil.copyfile(str(MIDI_DIR / track_a["midi_filename"]), out_mid)
        meta = generate_track_metadata(
            genre="DJ Blend",
            bpm=track_a["bpm"],
            scale=track_a["scale"],
            duration_sec=metrics.duration_sec,
            track_number=track_num,
            midi_filename=Path(out_mid).name,
            audio_filename=Path(out_wav).name,
            peak_dbfs=metrics.peak_dbfs,
            estimated_lufs=metrics.estimated_lufs,
            custom_title=title,
        )
    else:  # crossfade
        metrics = crossfade_audio_tracks(wav_a, wav_b, out_wav, crossfade_sec=crossfade_sec)
        title = custom_title or f"DJ Medley ({track_a['title'][:12]} ➔ {track_b['title'][:12]})"
        shutil.copyfile(str(MIDI_DIR / track_a["midi_filename"]), out_mid)
        meta = generate_track_metadata(
            genre="DJ Medley",
            bpm=track_a["bpm"],
            scale=track_a["scale"],
            duration_sec=metrics.duration_sec,
            track_number=track_num,
            midi_filename=Path(out_mid).name,
            audio_filename=Path(out_wav).name,
            peak_dbfs=metrics.peak_dbfs,
            estimated_lufs=metrics.estimated_lufs,
            custom_title=title,
        )
        
    catalog_objects = []
    for item in catalog:
        catalog_objects.append(
            TrackMetadata(
                title=item["title"],
                artist=item["artist"],
                genre=item["genre"],
                bpm=item["bpm"],
                scale=item["scale"],
                duration_sec=item["duration_sec"],
                isrc=item["isrc"],
                creation_date=item["creation_date"],
                content_id_certified=item["content_id_certified"],
                sample_packs_used=item["sample_packs_used"],
                composition_mode=item["composition_mode"],
                midi_filename=item["midi_filename"],
                audio_filename=item["audio_filename"],
                peak_dbfs=item.get("peak_dbfs"),
                estimated_lufs=item.get("estimated_lufs"),
            )
        )
    catalog_objects.append(meta)
    
    export_distribution_catalog(
        catalog_objects,
        str(META_DIR / "catalog_content_id.csv"),
        str(META_DIR / "catalog_content_id.json"),
    )
    
    return jsonify({
        "success": True,
        "track": {
            "title": meta.title,
            "artist": meta.artist,
            "genre": meta.genre,
            "bpm": meta.bpm,
            "scale": meta.scale,
            "duration_sec": meta.duration_sec,
            "isrc": meta.isrc,
            "midi_filename": meta.midi_filename,
            "audio_filename": meta.audio_filename,
            "peak_dbfs": meta.peak_dbfs,
            "estimated_lufs": meta.estimated_lufs,
        }
    })


@app.route("/api/flstudio-package/<isrc>", methods=["GET"])
def get_flstudio_package_api(isrc):
    catalog = _load_catalog()
    target = next((t for t in catalog if t["isrc"] == isrc), None)
    if not target:
        return jsonify({"success": False, "error": "Pista no encontrada"}), 404
        
    midi_file = MIDI_DIR / target["midi_filename"]
    if not midi_file.exists():
        return jsonify({"success": False, "error": "Archivo MIDI no encontrado"}), 404
        
    clean_name = f"Track_{target['isrc'].replace('-', '_')}"
    zip_path = FL_PACKAGES_DIR / f"{clean_name}_FLStudio_Project.zip"
    
    if not zip_path.exists():
        # Reconstruir bundle para empaquetado de stems
        bundle = generate_track_midi(
            genre=target["genre"] if target["genre"] in GENRES else "hard_rock",
            bars=16,
            seed=42,
        )
        create_flstudio_editable_project(bundle, clean_name, str(FL_PACKAGES_DIR))
        
    return jsonify({
        "success": True,
        "zip_url": f"/flpackages/{zip_path.name}",
        "project_name": clean_name,
    })


@app.route("/flpackages/<path:filename>")
def serve_flpackage(filename):
    return send_from_directory(str(FL_PACKAGES_DIR), filename, as_attachment=True)


@app.route("/audio/<path:filename>")
def serve_audio(filename):
    return send_from_directory(str(AUDIO_DIR), filename, mimetype="audio/wav")


@app.route("/midi/<path:filename>")
def serve_midi(filename):
    return send_from_directory(str(MIDI_DIR), filename, as_attachment=True, mimetype="audio/midi")


@app.route("/scripts/<path:filename>")
def serve_script(filename):
    return send_from_directory(str(FL_SCRIPTS_DIR), filename, as_attachment=True, mimetype="text/plain")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5055))
    print(f"\n[+] Panel de Control Visual disponible en: http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)
