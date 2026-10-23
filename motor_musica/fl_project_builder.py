"""Generador de Paquetes de Proyecto Completamente Editables en FL Studio.

Exporta archivos MIDI multipista, stems individuales por instrumento,
mapeo de canales VST para el Mixer y scripts de apertura directa en FL Studio.
"""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
from typing import Dict, List, Optional
import zipfile

import mido
from mido import MidiFile, MidiTrack, Message, MetaMessage

from .midi_generator import MidiTrackBundle, NoteEvent, _populate_midi_tracks
from .flstudio_cli import FLStudioCLI


@dataclass
class FLStudioPackageInfo:
    project_name: str
    folder_path: str
    zip_path: str
    stems: List[str]
    master_midi: str


def create_flstudio_editable_project(
    bundle: MidiTrackBundle,
    project_name: str,
    output_root_dir: str,
) -> FLStudioPackageInfo:
    """Crea una carpeta de proyecto 100% editable para FL Studio con MIDI multipista y stems."""
    project_dir = Path(output_root_dir) / f"FL_Project_{project_name}"
    stems_dir = project_dir / "stems"
    stems_dir.mkdir(parents=True, exist_ok=True)
    
    ticks_per_beat = bundle.midi_file.ticks_per_beat
    bpm = bundle.bpm
    tempo_val = mido.bpm2tempo(bpm)
    
    # 1. Guardar el Master MIDI multipista principal
    master_midi_path = project_dir / f"{project_name}_Master_MultiTrack.mid"
    bundle.midi_file.save(str(master_midi_path))
    
    # 2. Exportar cada pista individualmente como Stem MIDI para arrastrar a cualquier VST
    tracks_info = [
        ("01_Chords_Pads", "chords", 0, 89, "Sytrus / FLEX (Warm Pad)"),
        ("02_Melody_Lead", "melody", 1, 81, "Sytrus / Harmless (Pluck Lead)"),
        ("03_Bassline", "bass", 2, 38, "3xOSC / SubLab (Sub Bass)"),
        ("04_Drums_Kit", "drums", 9, 0, "FPC General MIDI Drumkit"),
    ]
    
    exported_stems: List[str] = []
    
    for filename_tag, track_name, ch, prog, vst_hint in tracks_info:
        stem_mid = MidiFile(type=0)
        stem_track = MidiTrack()
        stem_track.append(MetaMessage("set_tempo", tempo=tempo_val, time=0))
        stem_track.append(MetaMessage("track_name", name=f"{project_name} - {track_name}", time=0))
        if track_name != "drums":
            stem_track.append(Message("program_change", channel=ch, program=prog, time=0))
            
        track_events = [e for e in bundle.events if e.track_name == track_name]
        raw_msgs = []
        for ev in track_events:
            raw_msgs.append((ev.start_sec, "note_on", ev.pitch, ev.velocity, ev.channel))
            raw_msgs.append((ev.start_sec + ev.duration_sec, "note_off", ev.pitch, 0, ev.channel))
            
        raw_msgs.sort(key=lambda x: (x[0], 0 if x[1] == "note_off" else 1))
        curr_t = 0.0
        for msg_sec, m_type, pitch, vel, c in raw_msgs:
            delta = max(0.0, msg_sec - curr_t)
            beats = delta * (bpm / 60.0)
            ticks = max(0, int(round(beats * ticks_per_beat)))
            curr_t = msg_sec
            stem_track.append(Message(m_type, note=pitch, velocity=vel, time=ticks, channel=c))
            
        stem_track.append(MetaMessage("end_of_track", time=0))
        stem_mid.tracks.append(stem_track)
        
        stem_path = stems_dir / f"{filename_tag}.mid"
        stem_mid.save(str(stem_path))
        exported_stems.append(stem_path.name)
        
    # 3. Crear Guía de Ruteo en JSON
    routing = {
        "project_name": project_name,
        "bpm": bpm,
        "key_scale": bundle.profile.name,
        "instructions": (
            "Para editar en FL Studio:\n"
            "1. Abre FL Studio.\n"
            "2. Arrastra el archivo Master_MultiTrack.mid directamente a la lista de canales.\n"
            "3. En la ventana emergente, marca 'Split by tracks' para que cada instrumento cree su canal individual.\n"
            "4. Asigna los sintetizadores nativos sugeridos abajo a cada canal."
        ),
        "channel_rack_mapping": [
            {"channel_number": 1, "midi_channel": 1, "stem": "01_Chords_Pads.mid", "recommended_vst": "Sytrus / FLEX", "mixer_insert": 1},
            {"channel_number": 2, "midi_channel": 2, "stem": "02_Melody_Lead.mid", "recommended_vst": "Sytrus / Harmless", "mixer_insert": 2},
            {"channel_number": 3, "midi_channel": 3, "stem": "03_Bassline.mid", "recommended_vst": "3xOSC / BooBass", "mixer_insert": 3},
            {"channel_number": 4, "midi_channel": 10, "stem": "04_Drums_Kit.mid", "recommended_vst": "FPC", "mixer_insert": 4},
        ]
    }
    with open(project_dir / "FL_Studio_Routing_Guide.json", "w", encoding="utf-8") as f:
        json.dump(routing, f, indent=2, ensure_ascii=False)
        
    # 4. Crear Script de Apertura Inmediata (PowerShell)
    fl_cli = FLStudioCLI()
    fl_exe = fl_cli.executable_path or r"C:\Program Files\Image-Line\FL Studio 21\FL64.exe"
    
    ps1_content = f"""# Script para abrir el proyecto en FL Studio
$flExe = "{fl_exe}"
$midFile = Join-Path $PSScriptRoot "{master_midi_path.name}"

if (Test-Path $flExe) {{
    Write-Host "Abriendo proyecto editable en FL Studio..." -ForegroundColor Green
    Start-Process $flExe -ArgumentList "`"$midFile`""
}} else {{
    Write-Host "FL Studio no encontrado en ruta predeterminada." -ForegroundColor Yellow
    Write-Host "Arrastra $midFile directamente dentro de tu FL Studio."
    Start-Process explorer.exe -ArgumentList $PSScriptRoot
}}
"""
    with open(project_dir / "Open_In_FLStudio.ps1", "w", encoding="utf-8") as f:
        f.write(ps1_content)
        
    # 5. Comprimir paquete en ZIP para descarga desde la Web UI
    zip_path = Path(output_root_dir) / f"{project_name}_FLStudio_Project.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(project_dir):
            for file in files:
                full_p = os.path.join(root, file)
                rel_p = os.path.relpath(full_p, project_dir)
                zf.write(full_p, rel_p)
                
    return FLStudioPackageInfo(
        project_name=project_name,
        folder_path=str(project_dir),
        zip_path=str(zip_path),
        stems=exported_stems,
        master_midi=str(master_midi_path),
    )
