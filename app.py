"""Servidor Web y Panel de Control Visual para el Motor de Musica Content ID.

Permite reproducir temas generados, visualizar audio en tiempo real con Web Audio API,
lanzar nuevas composiciones algoritmicas en vivo y descargar MIDIs, WAVs y metadatos ISRC.
"""

import json
import os
from pathlib import Path
import random
import re
import shutil
import sys
import tempfile
import threading
import uuid

# Agregar la ruta raiz del proyecto a sys.path
PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from flask import Flask, jsonify, render_template, request, send_from_directory
from werkzeug.utils import secure_filename

from motor_musica.theory import GENRES
from motor_musica.midi_generator import MidiTrackBundle, generate_track_midi
from motor_musica.instruments import (
    DEFAULT_RACK,
    FAMILIES,
    INSTRUMENTS,
    ROLES,
    SOUND_PACKS,
    preview_events,
    resolve_rack,
)
from motor_musica.song_editor import (
    SongProject,
    apply_edits,
    build_project_bundle,
    current_key,
    piano_roll,
    project_for_fusion,
    project_for_generated,
    render_project,
)
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
from motor_musica.harmonic_fusion import (
    FUSION_GENRE,
    MAX_SOURCES,
    STYLES as FUSION_STYLES,
    FusionPlan,
    analyze_sources,
    build_fusion_bundle,
    create_harmonic_fusion,
)
from motor_musica.playlist_import import (
    DEFAULT_PLAYLIST_ITEMS,
    LIMITATION_NOTE,
    MAX_PLAYLIST_ITEMS,
    PlaylistTrack,
    analyze_playlist_entries,
    apply_classification,
    compose_from_target,
    group_by_genre,
    list_playlist_entries,
    target_from_tracks,
)

app = Flask(__name__, template_folder=str(PROJECT_DIR / "templates"))
app.config["MAX_CONTENT_LENGTH"] = 150 * 1024 * 1024  # 5 temas descargados en mp3/wav
UPLOAD_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".webm"}

OUTPUT_DIR = PROJECT_DIR / "output"
AUDIO_DIR = OUTPUT_DIR / "audio"
MIDI_DIR = OUTPUT_DIR / "midi"
META_DIR = OUTPUT_DIR / "metadata"
FL_SCRIPTS_DIR = OUTPUT_DIR / "flstudio_scripts"
FL_PACKAGES_DIR = OUTPUT_DIR / "fl_packages"
FUSION_PLANS_DIR = META_DIR / "fusion_plans"
PREVIEWS_DIR = OUTPUT_DIR / "previews"
PROJECTS_DIR = META_DIR / "projects"
PLAYLISTS_DIR = META_DIR / "playlists"

for d in [AUDIO_DIR, MIDI_DIR, META_DIR, FL_SCRIPTS_DIR, FL_PACKAGES_DIR, FUSION_PLANS_DIR, PREVIEWS_DIR, PROJECTS_DIR, PLAYLISTS_DIR]:
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


def _write_catalog(catalog):
    """Reescribe el catalogo JSON/CSV (lista de dicts del catalogo)."""
    fields = TrackMetadata.__dataclass_fields__.keys()
    catalog_objects = [TrackMetadata(**{k: item.get(k) for k in fields}) for item in catalog]
    export_distribution_catalog(
        catalog_objects,
        str(META_DIR / "catalog_content_id.csv"),
        str(META_DIR / "catalog_content_id.json"),
    )


def _append_to_catalog(catalog, new_meta):
    """Reescribe el catalogo JSON/CSV agregando una pista nueva."""
    _write_catalog(list(catalog) + [new_meta.__dict__])


def _track_json(meta):
    keys = ["title", "artist", "genre", "bpm", "scale", "duration_sec", "isrc",
            "midi_filename", "audio_filename", "peak_dbfs", "estimated_lufs"]
    src = meta if isinstance(meta, dict) else meta.__dict__
    return {k: src.get(k) for k in keys}


def _rack_from_request(data):
    """Rack pedido: paquete de sonido (un clic) + instrumentos sueltos que lo sobreescriben."""
    pack = SOUND_PACKS.get(data.get("pack") or "")
    rack = dict(pack.rack) if pack else {}
    rack.update(_parse_rack(data.get("instruments")))
    return rack, pack


def _project_path(isrc):
    return PROJECTS_DIR / f"{secure_filename(isrc)}.json"


def _save_project(project):
    with open(_project_path(project.isrc), "w", encoding="utf-8") as f:
        json.dump(project.to_dict(), f, indent=2, ensure_ascii=False)


def _load_project(isrc, catalog_entry=None):
    """Proyecto editable del tema; las fusiones antiguas se recuperan desde su plan guardado."""
    path = _project_path(isrc)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return SongProject.from_dict(json.load(f))
    plan_path = FUSION_PLANS_DIR / f"{secure_filename(isrc)}.json"
    if plan_path.exists():
        with open(plan_path, "r", encoding="utf-8") as f:
            plan = FusionPlan.from_dict(json.load(f)["plan"])
        title = (catalog_entry or {}).get("title") or plan.title
        return project_for_fusion(isrc, title, plan)
    return None


def _remove_fl_package(isrc):
    """Al editar un tema el paquete FL Studio queda viejo: se borra y se regenera al pedirlo."""
    name = _fl_package_name(isrc)
    (FL_PACKAGES_DIR / f"{name}_FLStudio_Project.zip").unlink(missing_ok=True)
    shutil.rmtree(FL_PACKAGES_DIR / f"FL_Project_{name}", ignore_errors=True)


def _project_view(project, bundle=None):
    bundle = bundle or build_project_bundle(project)
    return {
        "project": project.to_dict(),
        "key": current_key(project),
        "effective_bpm": project.effective_bpm,
        "piano_roll": piano_roll(bundle),
    }


def _parse_rack(raw):
    """Rack del request: dict {rol: id} o JSON en texto (multipart). 'auto' = elegir por timbre."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw) if raw.strip() else {}
        except ValueError:
            raw = {}
    if not isinstance(raw, dict):
        return {}
    return {r: v for r, v in raw.items() if r in ROLES and v in INSTRUMENTS and INSTRUMENTS[v].role == r}


def _fl_package_name(isrc):
    return f"Track_{isrc.replace('-', '_')}"


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
    
    rack, _ = _rack_from_request(data)
    seed = random.randrange(1, 2**31)
    project = project_for_generated("", custom_title or "", genre, seed, bars, rack)

    # 1-2. Componer MIDI con los programas GM del rack y renderizar WAV (proyecto editable)
    bundle, metrics, report = render_project(project, str(midi_path), str(wav_path))
    
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
        estimated_lufs=metrics.estimated_lufs, metrics=metrics,
        custom_title=custom_title,
    )
    
    project.isrc, project.title = new_meta.isrc, new_meta.title
    _save_project(project)

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
                content_id_checks=item.get("content_id_checks", "sin verificar"),
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
        "report": report,
        "track": _track_json(new_meta),
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
                    content_id_checks=item.get("content_id_checks", "sin verificar"),
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


@app.route("/api/harmonic-fusion", methods=["POST"])
def harmonic_fusion_api():
    """Uno o varios links -> tema original armonico (circulo de quintas) + checks de publicacion."""
    # Acepta JSON (solo links) o multipart/form-data (links + archivos descargados)
    if request.files:
        data = request.form.to_dict()
        raw_urls = data.get("urls", "")
        uploads = [f for f in request.files.getlist("files") if f and f.filename]
    else:
        data = request.get_json(silent=True) or {}
        raw_urls = data.get("urls", [])
        uploads = []
    if isinstance(raw_urls, str):
        raw_urls = raw_urls.splitlines()
    urls = [u.strip() for u in raw_urls if u and u.strip()]
    custom_title = (data.get("title") or "").strip() or None
    style = data.get("style", "pvz_gotico_swing")
    try:
        bars_per_section = int(data.get("bars_per_section", 8))
        variation = int(data.get("variation", 0))
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "Parametros numericos invalidos"}), 400

    if not urls and not uploads:
        return jsonify({"success": False, "error": "Pega al menos un link o sube un archivo de audio"}), 400
    if len(urls) + len(uploads) > MAX_SOURCES:
        return jsonify({"success": False, "error": f"Maximo {MAX_SOURCES} fuentes por fusion"}), 400
    bad = [u for u in urls if not (u.startswith("http://") or u.startswith("https://"))]
    if bad:
        return jsonify({"success": False, "error": f"Link invalido: {bad[0]}"}), 400
    bad_files = [f.filename for f in uploads if Path(f.filename).suffix.lower() not in UPLOAD_AUDIO_EXTENSIONS]
    if bad_files:
        return jsonify({"success": False, "error": f"Formato no soportado: {bad_files[0]}"}), 400
    if style not in FUSION_STYLES:
        style = "pvz_gotico_swing"
    rack_choice, pack = _rack_from_request(data)
    if pack and not data.get("style"):
        style = pack.style

    # Los archivos subidos viven solo durante el analisis (se miden y se borran)
    upload_dir = Path(tempfile.mkdtemp(prefix="fusion_upload_"))
    source_paths = list(urls)
    source_labels = [None] * len(urls)
    for i, f in enumerate(uploads):
        safe = secure_filename(f.filename) or f"audio_{i}"
        dest = upload_dir / f"{i:02d}_{safe}"
        f.save(str(dest))
        source_paths.append(str(dest))
        source_labels.append(safe)
    source_names = urls + [lbl for lbl in source_labels if lbl]

    try:
        sources = analyze_sources(source_paths, source_labels)

        catalog = _load_catalog()
        track_num = len(catalog) + 1
        clean_tag = f"fusion_{track_num:02d}_{len(urls)}src"
        midi_path = MIDI_DIR / f"{clean_tag}.mid"
        wav_path = AUDIO_DIR / f"{clean_tag}.wav"

        result = create_harmonic_fusion(
            sources,
            str(midi_path),
            str(wav_path),
            bars_per_section=bars_per_section,
            style=style,
            variation=variation,
            custom_title=custom_title,
            track_number=track_num,
            instruments=rack_choice,
        )
        meta = result.metadata

        # Plan + reporte para reconstruir el proyecto FL Studio con las mismas notas
        with open(FUSION_PLANS_DIR / f"{meta.isrc}.json", "w", encoding="utf-8") as f:
            json.dump(
                {"plan": result.plan.to_dict(), "report": result.report, "sources": source_names},
                f, indent=2, ensure_ascii=False,
            )
        create_flstudio_editable_project(
            result.bundle, _fl_package_name(meta.isrc), str(FL_PACKAGES_DIR), instruments=result.plan.instruments
        )
        _save_project(project_for_fusion(meta.isrc, meta.title, result.plan))
        _append_to_catalog(catalog, meta)

        plan = result.plan
        return jsonify({
            "success": True,
            "sources": [
                {
                    "url": s.dna.source_url,
                    "detected_bpm": s.dna.detected_bpm,
                    "detected_key": s.dna.detected_key,
                    "confidence": s.dna.confidence,
                }
                for s in sources
            ],
            "plan": {
                "home_key": plan.home_key,
                "bpm": plan.bpm,
                "style": plan.style,
                "circle_route": plan.circle_route,
                "source_keys": plan.source_keys,
                "sections": [
                    {"kind": sec.kind, "key": sec.key, "bars": sec.bars, "label": sec.label}
                    for sec in plan.sections
                ],
                "instruments": [
                    {
                        "role": role,
                        "id": plan.instruments[role],
                        "name": INSTRUMENTS[plan.instruments[role]].name,
                        "reason": plan.instrument_reasons.get(role, ""),
                    }
                    for role in ROLES
                ],
            },
            "report": result.report,
            "track": _track_json(meta),
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        shutil.rmtree(upload_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Importar playlist: clasificar por genero y componer temas parecidos
# ---------------------------------------------------------------------------

PLAYLIST_JOBS = {}
_jobs_lock = threading.Lock()


def _run_in_background(fn):
    threading.Thread(target=fn, daemon=True).start()


def _playlist_path(pid):
    return PLAYLISTS_DIR / f"{secure_filename(pid)}.json"


def _load_playlist(pid):
    path = _playlist_path(pid)
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["tracks"] = [PlaylistTrack.from_dict(t) for t in data["tracks"]]
    return data


def _save_playlist(data):
    out = dict(data, tracks=[t.to_dict() for t in data["tracks"]])
    with open(_playlist_path(data["id"]), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)


def _playlist_view(data):
    tracks = data["tracks"]
    return {
        "id": data["id"],
        "url": data["url"],
        "title": data["title"],
        "note": LIMITATION_NOTE,
        "tracks": [t.to_dict(with_fingerprint=False) for t in tracks],
        "groups": [
            {"genre": g, "name": GENRES[g].name, "indices": idx}
            for g, idx in group_by_genre(tracks).items()
        ],
        "generated": data.get("generated", []),
        "genres": [{"id": k, "name": v.name} for k, v in GENRES.items()],
    }


def _update_job(job_id, **fields):
    with _jobs_lock:
        PLAYLIST_JOBS[job_id].update(fields)


@app.route("/api/playlist/import", methods=["POST"])
def playlist_import_api():
    """Lista la playlist y mide cada tema en segundo plano. Se consulta con /api/playlist/job/<id>."""
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        return jsonify({"success": False, "error": "Pega el link de la playlist (https://...)"}), 400
    try:
        limit = max(1, min(int(data.get("limit", DEFAULT_PLAYLIST_ITEMS)), MAX_PLAYLIST_ITEMS))
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "Cantidad de temas invalida"}), 400
    shuffle = bool(data.get("shuffle"))

    job_id = uuid.uuid4().hex[:12]
    with _jobs_lock:
        PLAYLIST_JOBS[job_id] = {"status": "running", "done": 0, "total": 0, "current": "Leyendo la playlist..."}

    def work():
        try:
            title, entries = list_playlist_entries(url, limit, shuffle=shuffle)
            _update_job(job_id, total=len(entries), current=entries[0].title)

            def progress(done, total, track):
                nxt = entries[done].title if done < total else ""
                _update_job(job_id, done=done, current=nxt)

            tracks = analyze_playlist_entries(entries, progress)
            if all(t.error for t in tracks):
                raise ValueError(f"No se pudo medir ningun tema: {tracks[0].error}")
            pid = "pl_" + uuid.uuid4().hex[:10]
            _save_playlist({"id": pid, "url": url, "title": title, "tracks": tracks, "generated": []})
            _update_job(job_id, status="done", playlist_id=pid, current="")
        except Exception as e:
            _update_job(job_id, status="error", error=str(e)[:300])

    _run_in_background(work)
    return jsonify({"success": True, "job_id": job_id})


@app.route("/api/playlist/job/<job_id>", methods=["GET"])
def playlist_job_api(job_id):
    with _jobs_lock:
        job = dict(PLAYLIST_JOBS.get(job_id) or {})
    if not job:
        return jsonify({"success": False, "error": "Trabajo no encontrado"}), 404
    return jsonify({"success": True, **job})


@app.route("/api/playlist/<pid>", methods=["GET"])
def playlist_get_api(pid):
    data = _load_playlist(pid)
    if not data:
        return jsonify({"success": False, "error": "Playlist no encontrada"}), 404
    return jsonify({"success": True, "playlist": _playlist_view(data)})


@app.route("/api/playlist/<pid>/genre", methods=["POST"])
def playlist_set_genre_api(pid):
    """Corregir a mano el genero de un tema ('auto' vuelve a la clasificacion medida)."""
    data = _load_playlist(pid)
    if not data:
        return jsonify({"success": False, "error": "Playlist no encontrada"}), 404
    body = request.get_json(silent=True) or {}
    genre = body.get("genre")
    try:
        track = data["tracks"][int(body.get("index"))]
    except (TypeError, ValueError, IndexError):
        return jsonify({"success": False, "error": "Tema invalido"}), 400
    if track.error:
        return jsonify({"success": False, "error": "Ese tema no se pudo medir"}), 400
    if genre == "auto":
        apply_classification(track)
    elif genre in GENRES:
        track.genre, track.genre_overridden, track.ambiguous = genre, True, False
        track.genre_reason = "elegido a mano"
    else:
        return jsonify({"success": False, "error": "Genero desconocido"}), 400
    _save_playlist(data)
    return jsonify({"success": True, "playlist": _playlist_view(data)})


@app.route("/api/playlist/<pid>/compose", methods=["POST"])
def playlist_compose_api(pid):
    """Compone temas originales parecidos: uno por tema (per_track) o uno por genero (per_genre)."""
    data = _load_playlist(pid)
    if not data:
        return jsonify({"success": False, "error": "Playlist no encontrada"}), 404
    body = request.get_json(silent=True) or {}
    mode = body.get("mode", "per_track")
    try:
        bars = max(8, min(int(body.get("bars", 16)), 64))
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "Compases invalidos"}), 400
    tracks = [t for t in data["tracks"] if not t.error and t.genre]

    if mode == "per_genre":
        wanted = set(body.get("genres") or GENRES.keys())
        jobs = [(g, [data["tracks"][i] for i in idx]) for g, idx in group_by_genre(tracks).items() if g in wanted]
    else:
        indices = body.get("indices")
        selected = [t for t in tracks if indices is None or t.index in set(indices)]
        jobs = [(t.genre, [t]) for t in selected]
    if not jobs:
        return jsonify({"success": False, "error": "No hay temas seleccionados para componer"}), 400
    if len(jobs) > MAX_PLAYLIST_ITEMS:
        return jsonify({"success": False, "error": f"Maximo {MAX_PLAYLIST_ITEMS} temas por tanda"}), 400

    rack_choice, _ = _rack_from_request(body)
    results = []
    try:
        for genre, group in jobs:
            target = target_from_tracks(genre, group)
            catalog = _load_catalog()
            track_num = len(catalog) + 1
            tag = f"playlist_{track_num:02d}_{genre}"
            midi_path, wav_path = MIDI_DIR / f"{tag}.mid", AUDIO_DIR / f"{tag}.wav"
            project, bundle, metrics, report, reasons = compose_from_target(
                target, str(midi_path), str(wav_path), bars=bars, rack=rack_choice,
            )
            key = current_key(project)
            meta = generate_track_metadata(
                genre=genre, bpm=bundle.bpm, scale=key, duration_sec=metrics.duration_sec,
                track_number=track_num, midi_filename=midi_path.name, audio_filename=wav_path.name,
                peak_dbfs=metrics.peak_dbfs, estimated_lufs=metrics.estimated_lufs, metrics=metrics,
            )
            project.isrc, project.title = meta.isrc, meta.title
            _save_project(project)
            _append_to_catalog(catalog, meta)
            sources = [{"index": t.index, "title": t.title} for t in group]
            data.setdefault("generated", []).append({"isrc": meta.isrc, "genre": genre, "sources": sources})
            results.append({
                "genre": genre,
                "genre_name": GENRES[genre].name,
                "key": key,
                "sources": sources,
                "instruments": [
                    {"role": r, "id": project.rack[r], "name": INSTRUMENTS[project.rack[r]].name, "reason": reasons[r]}
                    for r in ROLES
                ],
                "report": report,
                "track": _track_json(meta),
            })
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "results": results}), 500
    finally:
        if results:
            _save_playlist(data)
    return jsonify({"success": True, "results": results, "note": LIMITATION_NOTE})


@app.route("/api/instruments", methods=["GET"])
def list_instruments():
    """Catalogo del rack de instrumentos procedurales, agrupado por rol."""
    return jsonify({
        "success": True,
        "default_rack": DEFAULT_RACK,
        "roles": {
            role: [
                {
                    "id": inst.id,
                    "name": inst.name,
                    "description": inst.description,
                    "gm_program": inst.gm_program,
                    "fl_plugin": inst.fl_plugin,
                    "family": FAMILIES.get(inst.id, "Otros"),
                }
                for inst in INSTRUMENTS.values() if inst.role == role
            ]
            for role in ROLES
        },
        "packs": [
            {"id": p.id, "name": p.name, "description": p.description, "rack": p.rack, "style": p.style}
            for p in SOUND_PACKS.values()
        ],
    })


@app.route("/api/project/<isrc>", methods=["GET"])
def get_project(isrc):
    """Proyecto editable de un tema: parametros de edicion + piano roll."""
    catalog = _load_catalog()
    entry = next((t for t in catalog if t["isrc"] == isrc), None)
    project = _load_project(isrc, entry) if entry else None
    if not project:
        return jsonify({"success": False, "error": "Este tema no tiene proyecto editable (creado con una version anterior)"}), 404
    return jsonify({"success": True, "track": _track_json(entry), **_project_view(project)})


@app.route("/api/project/<isrc>/render", methods=["POST"])
def render_project_api(isrc):
    """Aplica ediciones (instrumentos, mezcla, transponer, tempo, nueva melodia) y re-renderiza.

    as_new=true guarda el resultado como tema nuevo (ISRC nuevo); si no, crea la version _vN del mismo.
    """
    data = request.get_json(silent=True) or {}
    catalog = _load_catalog()
    entry = next((t for t in catalog if t["isrc"] == isrc), None)
    project = _load_project(isrc, entry) if entry else None
    if not project:
        return jsonify({"success": False, "error": "Tema no encontrado o sin proyecto editable"}), 404
    try:
        edited = apply_edits(project, data.get("edits") or {})
    except (TypeError, ValueError) as e:
        return jsonify({"success": False, "error": str(e)}), 400

    as_new = bool(data.get("as_new"))
    if as_new:
        track_num = len(catalog) + 1
        prefix = "fusion" if edited.kind == "fusion" else "track"
        tag = f"{prefix}_{track_num:02d}_edit"
        edited.version = 1
    else:
        edited.version += 1
        base = re.sub(r"_v\d+$", "", Path(entry["midi_filename"]).stem)
        tag = f"{base}_v{edited.version}"
    midi_path, wav_path = MIDI_DIR / f"{tag}.mid", AUDIO_DIR / f"{tag}.wav"

    bundle, metrics, report = render_project(edited, str(midi_path), str(wav_path))
    if as_new:
        title = (data.get("title") or "").strip() or f"{entry['title']} (edit)"
        meta = generate_track_metadata(
            genre=entry["genre"], bpm=bundle.bpm, scale=entry["scale"], duration_sec=metrics.duration_sec,
            track_number=track_num, midi_filename=midi_path.name, audio_filename=wav_path.name,
            peak_dbfs=metrics.peak_dbfs, estimated_lufs=metrics.estimated_lufs, custom_title=title, metrics=metrics,
        )
        edited.isrc, edited.title = meta.isrc, meta.title
        _append_to_catalog(catalog, meta)
        track = _track_json(meta)
    else:
        entry.update({
            "bpm": bundle.bpm,
            "duration_sec": round(metrics.duration_sec, 2),
            "midi_filename": midi_path.name,
            "audio_filename": wav_path.name,
            "peak_dbfs": round(metrics.peak_dbfs, 2),
            "estimated_lufs": round(metrics.estimated_lufs, 2),
        })
        _write_catalog(catalog)
        _remove_fl_package(isrc)
        track = _track_json(entry)
    _save_project(edited)
    return jsonify({"success": True, "track": track, "report": report, **_project_view(edited, bundle)})


@app.route("/api/instrument-preview/<instrument_id>", methods=["GET"])
def instrument_preview(instrument_id):
    """Frase corta sintetizada con el instrumento (se cachea en output/previews)."""
    if instrument_id not in INSTRUMENTS:
        return jsonify({"success": False, "error": "Instrumento desconocido"}), 404
    wav_name = f"preview_{instrument_id}.wav"
    wav_path = PREVIEWS_DIR / wav_name
    if not wav_path.exists():
        inst = INSTRUMENTS[instrument_id]
        events, duration = preview_events(instrument_id)
        bundle = MidiTrackBundle(GENRES["synthwave"], 2, 110, duration, None, events)
        render_midi_to_wav(
            bundle, str(wav_path), config=SynthConfig(sample_rate=44100, tail_sec=0.8),
            instruments={inst.role: instrument_id},
        )
    return send_from_directory(str(PREVIEWS_DIR), wav_name, mimetype="audio/wav")


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
            estimated_lufs=metrics.estimated_lufs, metrics=metrics,
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
            estimated_lufs=metrics.estimated_lufs, metrics=metrics,
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
                content_id_checks=item.get("content_id_checks", "sin verificar"),
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
        
    clean_name = _fl_package_name(target["isrc"])
    zip_path = FL_PACKAGES_DIR / f"{clean_name}_FLStudio_Project.zip"
    plan_path = FUSION_PLANS_DIR / f"{target['isrc']}.json"
    
    project = _load_project(target["isrc"], target) if not zip_path.exists() else None
    if project:
        # Temas con proyecto (incluidas sus ediciones): mismas notas e instrumentos que el WAV
        bundle = build_project_bundle(project)
        create_flstudio_editable_project(bundle, clean_name, str(FL_PACKAGES_DIR), instruments=resolve_rack(project.rack))
    elif not zip_path.exists() and target["genre"] == FUSION_GENRE and plan_path.exists():
        # Las fusiones se reconstruyen nota por nota desde su plan guardado
        with open(plan_path, "r", encoding="utf-8") as f:
            plan = FusionPlan.from_dict(json.load(f)["plan"])
        bundle, _ = build_fusion_bundle(plan)
        create_flstudio_editable_project(bundle, clean_name, str(FL_PACKAGES_DIR), instruments=plan.instruments or None)
    elif not zip_path.exists():
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
