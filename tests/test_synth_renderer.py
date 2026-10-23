"""Pruebas del motor de sintesis procedural de audio."""

import os
from pathlib import Path
import sys
import tempfile
import unittest
import wave

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from motor_musica.midi_generator import generate_track_midi
from motor_musica.synth_renderer import render_midi_to_wav, SynthConfig, calculate_loudness_stats


class TestSynthRenderer(unittest.TestCase):
    def test_render_short_audio(self):
        bundle = generate_track_midi(genre="lofi_chill", bars=2, seed=42)
        with tempfile.TemporaryDirectory() as tmpdir:
            wav_file = os.path.join(tmpdir, "test.wav")
            cfg = SynthConfig(sample_rate=22050, tail_sec=0.5, bit_depth=16)
            metrics = render_midi_to_wav(bundle, wav_file, config=cfg)

            self.assertTrue(os.path.isfile(wav_file))
            self.assertGreater(os.path.getsize(wav_file), 1000)

            # Validar encabezado WAV
            with wave.open(wav_file, "rb") as wf:
                self.assertEqual(wf.getnchannels(), 2)
                self.assertEqual(wf.getsampwidth(), 2)
                self.assertEqual(wf.getframerate(), 22050)

            # Validar que no hay saturacion digital extrema
            self.assertLessEqual(metrics.peak_dbfs, -0.90)
            self.assertEqual(metrics.clipped_samples, 0)


if __name__ == "__main__":
    unittest.main()
