"""Pruebas del modulo de teoria musical."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from motor_musica.theory import (
    GENRES,
    ScaleType,
    build_scale_notes,
    get_chord_notes,
    get_bass_note,
)


class TestTheory(unittest.TestCase):
    def test_genres_defined(self):
        self.assertIn("epic_cinematic", GENRES)
        self.assertIn("synthwave", GENRES)
        self.assertIn("lofi_chill", GENRES)

    def test_scale_notes_in_midi_range(self):
        for scale_type in ScaleType:
            notes = build_scale_notes(root=57, scale_type=scale_type, octaves=3)
            self.assertTrue(len(notes) > 10)
            self.assertTrue(all(0 <= n <= 127 for n in notes))
            # Escala debe estar ordenada ascendentemente
            self.assertEqual(notes, sorted(notes))

    def test_get_chord_notes(self):
        chords = get_chord_notes(57, ScaleType.HARMONIC_MINOR, degree_index=0)
        self.assertEqual(len(chords), 3)
        self.assertTrue(all(0 <= c <= 127 for c in chords))
        # Acorde con extension de 7ma
        chords_ext = get_chord_notes(48, ScaleType.NATURAL_MINOR, degree_index=0, extended=True)
        self.assertEqual(len(chords_ext), 4)

    def test_get_bass_note_in_bass_register(self):
        for deg in range(7):
            bass = get_bass_note(57, ScaleType.HARMONIC_MINOR, deg)
            self.assertTrue(24 <= bass <= 55, f"Bass pitch {bass} fuera de registro")


if __name__ == "__main__":
    unittest.main()
