"""Pruebas del generador de archivos MIDI."""

import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from motor_musica.midi_generator import generate_track_midi, MidiTrackBundle


class TestMidiGenerator(unittest.TestCase):
    def test_generate_epic_midi(self):
        bundle = generate_track_midi(genre="epic_cinematic", bars=4, seed=123)
        self.assertIsInstance(bundle, MidiTrackBundle)
        self.assertEqual(bundle.bars, 4)
        self.assertEqual(bundle.bpm, 120)
        self.assertTrue(len(bundle.events) > 50)
        # Comprobar canales
        channels = set(e.channel for e in bundle.events)
        self.assertIn(0, channels)  # Chords
        self.assertIn(1, channels)  # Melody
        self.assertIn(2, channels)  # Bass
        self.assertIn(9, channels)  # Drums

    def test_midi_file_export(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = os.path.join(tmpdir, "test.mid")
            bundle = generate_track_midi(genre="synthwave", bars=2, seed=99, output_mid_path=out_file)
            self.assertTrue(os.path.isfile(out_file))
            self.assertGreater(os.path.getsize(out_file), 500)
            # Debe tener pistas separadas
            self.assertEqual(len(bundle.midi_file.tracks), 5)


if __name__ == "__main__":
    unittest.main()
