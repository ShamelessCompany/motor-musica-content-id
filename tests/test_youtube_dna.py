"""Pruebas del extractor de ADN de audio y YouTube."""

import os
from pathlib import Path
import sys
import tempfile
import unittest
import wave

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from motor_musica.youtube_dna import (
    analyze_audio_buffer,
    analyze_youtube_dna,
    compose_original_from_youtube_dna,
    ExtractedYouTubeDNA,
)
from motor_musica.theory import ScaleType


class TestYouTubeDNA(unittest.TestCase):
    def test_analyze_audio_buffer_key_detection(self):
        sr = 22050
        dur = 3.0
        t = np.linspace(0, dur, int(sr * dur), endpoint=False)
        # Acorde de A menor (La = 440 Hz, Do = 523.25 Hz, Mi = 659.25 Hz)
        audio = (
            np.sin(2 * np.pi * 440.0 * t)
            + np.sin(2 * np.pi * 523.25 * t)
            + np.sin(2 * np.pi * 659.25 * t)
        )
        audio = audio.astype(np.float32)

        bpm, key_name, scale_type, root_midi, conf = analyze_audio_buffer(audio, sr)
        self.assertIn("A", key_name)
        self.assertIn("minor", key_name)
        self.assertEqual(scale_type, ScaleType.NATURAL_MINOR)
        self.assertGreater(conf, 0.5)

    def test_compose_from_dna(self):
        dna = ExtractedYouTubeDNA(
            source_url="local_test.wav",
            detected_bpm=140,
            detected_key="D minor",
            root_midi=50,
            scale_type=ScaleType.PHRYGIAN,
            genre_hint="dark_trap",
            confidence=0.85,
            analysis_duration_sec=30.0,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            out_mid = os.path.join(tmpdir, "out.mid")
            out_wav = os.path.join(tmpdir, "out.wav")
            meta, metrics = compose_original_from_youtube_dna(
                dna, bars=2, output_mid_path=out_mid, output_wav_path=out_wav
            )

            self.assertTrue(os.path.isfile(out_mid))
            self.assertTrue(os.path.isfile(out_wav))
            self.assertEqual(meta.genre, "dark_trap")
            self.assertLessEqual(metrics.peak_dbfs, -0.9)


if __name__ == "__main__":
    unittest.main()
