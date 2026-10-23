"""Pruebas del extractor de ADN musical y generador Markov."""

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from motor_musica.midi_generator import generate_track_midi
from motor_musica.dna_extractor import extract_dna_from_midi, mutate_dna_melody


class TestDNAExtractor(unittest.TestCase):
    def test_extract_and_mutate(self):
        # 1. Generar un MIDI de prueba
        bundle = generate_track_midi("epic_cinematic", bars=4, seed=10)
        with tempfile.TemporaryDirectory() as tmpdir:
            ref_midi = str(Path(tmpdir) / "reference.mid")
            bundle.midi_file.save(ref_midi)

            # 2. Extraer ADN musical
            dna = extract_dna_from_midi(ref_midi)
            self.assertTrue(len(dna.pitch_transitions) > 0)
            self.assertEqual(dna.estimated_tempo, 120)

            # 3. Generar variacion mutada
            variation = mutate_dna_melody(dna, length_notes=16, mutation_rate=0.3)
            self.assertEqual(len(variation), 16)
            for pitch, dur in variation:
                self.assertTrue(0 <= pitch <= 127)
                self.assertGreater(dur, 0)


if __name__ == "__main__":
    unittest.main()
