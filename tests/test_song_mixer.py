"""Pruebas del mezclador de canciones, crossfades y mashups."""

import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from motor_musica.midi_generator import generate_track_midi
from motor_musica.synth_renderer import render_midi_to_wav, SynthConfig
from motor_musica.song_mixer import (
    crossfade_audio_tracks,
    blend_audio_tracks,
    stem_mashup_remix,
)


class TestSongMixer(unittest.TestCase):
    def test_crossfade_and_blend(self):
        bundle_a = generate_track_midi("epic_cinematic", bars=2, seed=1)
        bundle_b = generate_track_midi("synthwave", bars=2, seed=2)

        with tempfile.TemporaryDirectory() as tmpdir:
            wav_a = os.path.join(tmpdir, "a.wav")
            wav_b = os.path.join(tmpdir, "b.wav")
            cfg = SynthConfig(sample_rate=22050, bit_depth=16)

            render_midi_to_wav(bundle_a, wav_a, config=cfg)
            render_midi_to_wav(bundle_b, wav_b, config=cfg)

            # 1. Probar Crossfade
            out_crossfade = os.path.join(tmpdir, "crossfade.wav")
            m_cross = crossfade_audio_tracks(wav_a, wav_b, out_crossfade, crossfade_sec=1.0)
            self.assertTrue(os.path.isfile(out_crossfade))
            self.assertLessEqual(m_cross.peak_dbfs, -0.9)

            # 2. Probar Blend simultaneo
            out_blend = os.path.join(tmpdir, "blend.wav")
            m_blend = blend_audio_tracks(wav_a, wav_b, out_blend, balance_a_to_b=0.5)
            self.assertTrue(os.path.isfile(out_blend))
            self.assertLessEqual(m_blend.peak_dbfs, -0.9)

            # 3. Probar Mashup Hibrido
            out_mashup_mid = os.path.join(tmpdir, "mashup.mid")
            out_mashup_wav = os.path.join(tmpdir, "mashup.wav")
            meta, m_mash = stem_mashup_remix(
                bundle_a, bundle_b, out_mashup_mid, out_mashup_wav, custom_title="Epic Wave Mashup"
            )
            self.assertTrue(os.path.isfile(out_mashup_mid))
            self.assertTrue(os.path.isfile(out_mashup_wav))
            self.assertEqual(meta.title, "Epic Wave Mashup")


if __name__ == "__main__":
    unittest.main()
