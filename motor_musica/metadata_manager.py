"""Gestion de Metadatos ISRC y Catalogacion para Distribuidoras de Content ID.

Produce archivos JSON y CSV compatibles con plataformas como Identifyy,
Soundrop, Songtradr, y TuneCore, garantizando la trazabilidad de los derechos de autor.
"""

import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import random
from typing import List, Optional


TITLE_POOLS = {
    "epic_cinematic": [
        "Vanguard of the Fallen",
        "Aethelgard Overture",
        "Chronicles of the Iron Titan",
        "Ascension of the Valkyrie",
        "Shadow of the Monolith",
        "Kingdom of the Northern Sea",
        "The Last Citadel",
        "Echoes of Valhalla",
    ],
    "synthwave": [
        "Neon Horizon 2084",
        "Midnight Cyber Drive",
        "Outrun Overdrive",
        "Laser Grid Sunset",
        "Tokyo Drift Velocity",
        "Analog Dreams in Shibuya",
        "Cassette Tape Memories",
        "Chrome Boulevard",
    ],
    "lofi_chill": [
        "Coffee at 2AM",
        "Raindrops on Old Vinyl",
        "Midnight Study Session",
        "Cat by the Windowpane",
        "Tokyo Backstreet Breeze",
        "Dusty Keys & Warm Tea",
        "Late Autumn Solitude",
        "Bonsai Rooftop Garden",
    ],
    "hard_rock": [
        "Thunderstruck Velocity",
        "Overdrive Rebellion",
        "Electric Wasteland Riff",
        "Highway of Shadows",
        "Iron Fury Ignition",
        "Ashes & Nitro",
        "Rumble in the Canyon",
        "Black Smoke Anthem",
    ],
    "dark_trap": [
        "Midnight Phantom 808",
        "Savage Dynasty Trap",
        "Metro Obsidian Beat",
        "Astroworld Nocturne",
        "Sinister Slime Drift",
        "Cortege of Kings",
        "Grim Reaper Glide",
        "VVS Diamond Frost",
    ],
    "boom_bap": [
        "Brooklyn Rooftop Cypher",
        "Queensbridge Renaissance",
        "Crate Digger Chronicles",
        "Concrete Jazz Theory",
        "Subway Graffiti Vibe",
        "Spitfire Microphone 96",
        "Harlem Brownstone Soul",
        "Raw Vinyl Boom Bap",
    ],
}


@dataclass
class TrackMetadata:
    title: str
    artist: str
    genre: str
    bpm: int
    scale: str
    duration_sec: float
    isrc: str
    creation_date: str
    content_id_certified: bool
    sample_packs_used: bool
    composition_mode: str
    midi_filename: str
    audio_filename: str
    peak_dbfs: Optional[float] = None
    estimated_lufs: Optional[float] = None


def generate_isrc(track_number: int, country: str = "US", registrant: str = "SHM", year: int = 26) -> str:
    """Genera un codigo ISRC valido bajo la norma ISO 3901 (ej. US-SHM-26-00001)."""
    designation = f"{track_number:05d}"
    return f"{country}-{registrant}-{year:02d}-{designation}"


def generate_track_metadata(
    genre: str,
    bpm: int,
    scale: str,
    duration_sec: float,
    track_number: int,
    midi_filename: str,
    audio_filename: str,
    peak_dbfs: Optional[float] = None,
    estimated_lufs: Optional[float] = None,
    custom_title: Optional[str] = None,
) -> TrackMetadata:
    """Crea la ficha técnica y legal para registro en Content ID."""
    pool = TITLE_POOLS.get(genre, TITLE_POOLS["epic_cinematic"])
    title = custom_title or random.choice(pool)
    isrc = generate_isrc(track_number)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return TrackMetadata(
        title=title,
        artist="Shameless Music Engine",
        genre=genre,
        bpm=bpm,
        scale=scale,
        duration_sec=round(duration_sec, 2),
        isrc=isrc,
        creation_date=now_iso,
        content_id_certified=True,
        sample_packs_used=False,
        composition_mode="100% Algorithmic Pure Synthesis",
        midi_filename=midi_filename,
        audio_filename=audio_filename,
        peak_dbfs=round(peak_dbfs, 2) if peak_dbfs is not None else None,
        estimated_lufs=round(estimated_lufs, 2) if estimated_lufs is not None else None,
    )


def export_distribution_catalog(
    tracks: List[TrackMetadata],
    output_csv_path: str,
    output_json_path: str,
) -> None:
    """Exporta el catálogo de canciones en formato CSV (para distribuidoras) y JSON."""
    # 1. Exportar JSON
    catalog_data = [asdict(t) for t in tracks]
    with open(output_json_path, "w", encoding="utf-8") as jf:
        json.dump(catalog_data, jf, indent=2, ensure_ascii=False)

    # 2. Exportar CSV estandar para subida a Soundrop / Identifyy
    fieldnames = [
        "isrc",
        "title",
        "artist",
        "genre",
        "bpm",
        "scale",
        "duration_sec",
        "creation_date",
        "content_id_certified",
        "sample_packs_used",
        "audio_filename",
        "midi_filename",
        "peak_dbfs",
        "estimated_lufs",
    ]

    with open(output_csv_path, "w", newline="", encoding="utf-8") as cf:
        writer = csv.DictWriter(cf, fieldnames=fieldnames)
        writer.writeheader()
        for t in tracks:
            d = asdict(t)
            # Filtrar solo campos que van al CSV
            row = {k: d[k] for k in fieldnames}
            writer.writerow(row)
