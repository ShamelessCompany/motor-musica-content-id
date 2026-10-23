"""Motor Procedural de Musica para Content ID (Shameless Company)."""

from .theory import MusicalProfile, GENRES, ScaleType
from .midi_generator import generate_track_midi, MidiTrackBundle
from .synth_renderer import render_midi_to_wav, SynthConfig
from .flstudio_cli import FLStudioCLI
from .metadata_manager import generate_track_metadata, export_distribution_catalog
from .dna_extractor import extract_dna_from_midi, mutate_dna_melody, SongDNA

__all__ = [
    "MusicalProfile",
    "GENRES",
    "ScaleType",
    "generate_track_midi",
    "MidiTrackBundle",
    "render_midi_to_wav",
    "SynthConfig",
    "FLStudioCLI",
    "generate_track_metadata",
    "export_distribution_catalog",
    "extract_dna_from_midi",
    "mutate_dna_melody",
    "SongDNA",
]
