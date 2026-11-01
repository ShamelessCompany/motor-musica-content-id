"""Pruebas del motor de fusion armonica multi-link, el circulo de quintas y los checks."""

import os
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from motor_musica.content_id_checks import fingerprint_match_ratio, landmark_hashes
from motor_musica.harmonic_fusion import (
    FusionPlan,
    analyze_sources,
    blend_tempo,
    compose_fusion_events,
    create_harmonic_fusion,
    plan_fusion,
)
from motor_musica.midi_generator import generate_track_midi
from motor_musica.synth_renderer import SynthConfig, render_midi_to_wav
from motor_musica.theory import (
    circle_distance,
    dominant_seventh_pcs,
    fourths_path,
    key_center,
    parse_key_name,
)
from motor_musica.youtube_dna import ExtractedYouTubeDNA, estimate_bpm
from motor_musica.theory import ScaleType


def _dna(key: str, bpm: int, label: str) -> ExtractedYouTubeDNA:
    return ExtractedYouTubeDNA(
        source_url=label, detected_bpm=bpm, detected_key=key, root_midi=57,
        scale_type=ScaleType.NATURAL_MINOR, genre_hint="synthwave", confidence=0.8,
        analysis_duration_sec=30.0,
    )


class TestCircleOfFifths(unittest.TestCase):
    def test_relative_keys_share_position(self):
        self.assertEqual(circle_distance(parse_key_name("A minor"), parse_key_name("C major")), 0)
        self.assertEqual(circle_distance(parse_key_name("C major"), parse_key_name("F# major")), 6)

    def test_fourths_path_moves_by_fourths(self):
        path = fourths_path(parse_key_name("A minor"), parse_key_name("F minor"))
        self.assertEqual([k.name for k in path], ["D minor", "G minor", "C minor", "F minor"])
        # Cada V7 del puente resuelve una cuarta arriba hacia su tonica
        for k in path:
            self.assertEqual((dominant_seventh_pcs(k)[0] + 5) % 12, k.pitch_class)

    def test_key_center_and_tempo_blend(self):
        keys = [parse_key_name(n) for n in ("A minor", "E minor", "D minor")]
        self.assertEqual(key_center(keys).name, "A minor")
        self.assertEqual(blend_tempo([120, 62, 128]), 124)


class TestFusionPlan(unittest.TestCase):
    def test_plan_has_section_per_source_and_bridges(self):
        dnas = [_dna("A minor", 120, "a"), _dna("F minor", 124, "b")]
        plan = plan_fusion(dnas, bars_per_section=4)
        temas = [s for s in plan.sections if s.kind == "tema"]
        self.assertEqual([s.key for s in temas], ["A minor", "F minor"])
        self.assertTrue(any(s.kind == "puente" for s in plan.sections))
        self.assertEqual(plan.sections[-1].key, plan.home_key)
        # Determinista y serializable
        again = FusionPlan.from_dict(plan.to_dict())
        ev_a, dur_a, _ = compose_fusion_events(plan)
        ev_b, dur_b, _ = compose_fusion_events(again)
        self.assertEqual(len(ev_a), len(ev_b))
        self.assertAlmostEqual(dur_a, dur_b)

    def test_events_use_standard_channels(self):
        plan = plan_fusion([_dna("C major", 100, "x")], bars_per_section=4, style="seguir_fuente")
        events, _, _ = compose_fusion_events(plan)
        channels = {(e.track_name, e.channel) for e in events}
        self.assertEqual(channels, {("chords", 0), ("melody", 1), ("bass", 2), ("drums", 9)})


class TestFusionPipelineAndChecks(unittest.TestCase):
    def test_fusion_from_two_sources_passes_checks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sources = []
            for genre in ("epic_cinematic", "dark_trap"):
                path = os.path.join(tmpdir, f"{genre}.wav")
                render_midi_to_wav(generate_track_midi(genre, bars=8, seed=3), path, SynthConfig(sample_rate=22050))
                sources.append(path)
            analyzed = analyze_sources(sources)
            self.assertEqual(analyzed[0].dna.detected_bpm, 120)

            result = create_harmonic_fusion(
                analyzed, os.path.join(tmpdir, "f.mid"), os.path.join(tmpdir, "f.wav"),
                bars_per_section=4, sample_rate=22050,
            )
            self.assertTrue(os.path.isfile(os.path.join(tmpdir, "f.mid")))
            self.assertLessEqual(result.metrics.peak_dbfs, -0.95)
            failed = [c for c in result.report["checks"] if not c["passed"]]
            self.assertEqual(failed, [], msg=str(failed))
            self.assertTrue(result.report["aprobado"])

    def test_fingerprint_detects_copy_but_not_original(self):
        sr = 22050
        with tempfile.TemporaryDirectory() as tmpdir:
            a, b = os.path.join(tmpdir, "a.wav"), os.path.join(tmpdir, "b.wav")
            render_midi_to_wav(generate_track_midi("synthwave", bars=6, seed=1), a, SynthConfig(sample_rate=sr))
            render_midi_to_wav(generate_track_midi("epic_cinematic", bars=6, seed=2), b, SynthConfig(sample_rate=sr))
            from motor_musica.harmonic_fusion import _read_wav_mono

            mono_a, _ = _read_wav_mono(a)
            mono_b, _ = _read_wav_mono(b)
            self.assertTrue(landmark_hashes(mono_a, sr))
            copy_ratio = fingerprint_match_ratio(mono_a[sr * 2:], sr, mono_a, sr)
            original_ratio = fingerprint_match_ratio(mono_b, sr, mono_a, sr)
            self.assertGreater(copy_ratio, 0.3)
            self.assertLess(original_ratio, 0.15)

    def test_estimate_bpm_click_track(self):
        sr = 22050
        audio = np.zeros(sr * 12, dtype=np.float32)
        for beat in np.arange(0, 12, 60.0 / 128):
            i = int(beat * sr)
            audio[i:i + 300] += np.hanning(600)[300:].astype(np.float32)
        self.assertAlmostEqual(estimate_bpm(audio, sr), 128, delta=2)


if __name__ == "__main__":
    unittest.main()
