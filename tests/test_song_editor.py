"""Pruebas del editor de temas (motor + endpoints) y de los paquetes de sonido."""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

import app as app_module
from motor_musica.harmonic_fusion import plan_fusion
from motor_musica.instruments import INSTRUMENTS, ROLES, SOUND_PACKS, resolve_rack
from motor_musica.song_editor import (
    SongProject,
    apply_edits,
    build_project_bundle,
    current_key,
    project_for_fusion,
    project_for_generated,
)
from motor_musica.synth_renderer import calculate_loudness_stats
from tests.test_harmonic_fusion import _dna


class TestSongEditor(unittest.TestCase):
    def test_sound_packs_are_complete_racks(self):
        for pack in SOUND_PACKS.values():
            self.assertEqual(resolve_rack(pack.rack), pack.rack, pack.id)
            for role, inst_id in pack.rack.items():
                self.assertEqual(INSTRUMENTS[inst_id].role, role)

    def test_apply_edits_validates_without_mutating(self):
        project = project_for_generated("X", "t", "synthwave", 7, 4, {})
        edited = apply_edits(project, {"transpose": 40, "bpm": 500, "volumes": {"bass": 9}, "new_melody": True})
        self.assertEqual(edited.transpose, 12)
        self.assertEqual(edited.target_bpm, 180)
        self.assertEqual(edited.volumes["bass"], 2.0)
        self.assertEqual(edited.melody_variation, 1)
        self.assertEqual(project.transpose, 0)
        with self.assertRaises(ValueError):
            apply_edits(project, {"muted": {r: True for r in ROLES}})
        self.assertFalse(any(project.muted.values()))

    def test_transpose_tempo_and_new_melody(self):
        plan = plan_fusion([_dna("A minor", 120, "a"), _dna("C major", 100, "b")], bars_per_section=4)
        project = project_for_fusion("X", "t", plan)
        base = build_project_bundle(project)
        target = plan.bpm + 20
        edited = apply_edits(project, {"transpose": 2, "bpm": target})
        bundle = build_project_bundle(edited)
        self.assertEqual(current_key(edited), "B minor")
        self.assertAlmostEqual(bundle.duration_sec, base.duration_sec * plan.bpm / target, delta=0.05)
        lead = lambda b: [e.pitch for e in b.events if e.channel == 1]
        drums = lambda b: sorted(e.pitch for e in b.events if e.channel == 9)
        self.assertEqual([p + 2 for p in lead(base)], lead(bundle))
        self.assertEqual(drums(base), drums(bundle))  # la bateria no se transpone
        new_melody = build_project_bundle(apply_edits(project, {"new_melody": True}))
        self.assertNotEqual(lead(base), lead(new_melody))
        roundtrip = SongProject.from_dict(edited.to_dict())
        self.assertEqual(roundtrip, edited)


class TestLoudnessMeter(unittest.TestCase):
    def test_bs1770_reference_tone(self):
        # ITU-R BS.1770: seno de 997 Hz a 0 dBFS en un canal = -3.01 LKFS, a cualquier sample rate
        for sr in (48000, 44100, 22050):
            t = np.arange(sr * 3) / sr
            tone = np.sin(2 * np.pi * 997 * t)
            stereo = np.stack([tone, np.zeros_like(tone)], axis=1)
            self.assertAlmostEqual(calculate_loudness_stats(stereo, sr).estimated_lufs, -3.01, delta=0.1)


class TestEditorApi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        dirs = {
            "AUDIO_DIR": root / "audio",
            "MIDI_DIR": root / "midi",
            "META_DIR": root / "meta",
            "FL_SCRIPTS_DIR": root / "scripts",
            "FL_PACKAGES_DIR": root / "fl",
            "FUSION_PLANS_DIR": root / "meta" / "fusion_plans",
            "PROJECTS_DIR": root / "meta" / "projects",
        }
        for d in dirs.values():
            d.mkdir(parents=True, exist_ok=True)
        self.patches = [mock.patch.object(app_module, k, v) for k, v in dirs.items()]
        for p in self.patches:
            p.start()
        self.client = app_module.app.test_client()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_instruments_include_families_and_packs(self):
        body = self.client.get("/api/instruments").get_json()
        self.assertTrue(all("family" in i for insts in body["roles"].values() for i in insts))
        self.assertEqual({p["id"] for p in body["packs"]}, set(SOUND_PACKS))

    def test_generate_with_pack_then_edit(self):
        res = self.client.post("/api/generate", json={"genre": "lofi_chill", "bars": 4, "pack": "acustico"})
        body = res.get_json()
        self.assertEqual(res.status_code, 200, body)
        self.assertTrue(body["report"]["aprobado"], body["report"])
        isrc = body["track"]["isrc"]

        view = self.client.get(f"/api/project/{isrc}").get_json()
        self.assertEqual(view["project"]["rack"], SOUND_PACKS["acustico"].rack)
        self.assertTrue(view["piano_roll"]["notes"])

        res = self.client.post(f"/api/project/{isrc}/render", json={
            "edits": {"bpm": 100, "muted": {"drums": True}, "new_melody": True},
        })
        edited = res.get_json()
        self.assertEqual(res.status_code, 200, edited)
        self.assertTrue(edited["report"]["aprobado"], edited["report"])
        self.assertEqual(edited["track"]["isrc"], isrc)
        self.assertEqual(edited["track"]["bpm"], 100)
        self.assertEqual(edited["project"]["version"], 2)
        self.assertTrue((app_module.AUDIO_DIR / edited["track"]["audio_filename"]).exists())

        # Guardar como tema nuevo: ISRC nuevo y el original intacto
        res = self.client.post(f"/api/project/{isrc}/render", json={"edits": {"transpose": -3}, "as_new": True})
        new = res.get_json()
        self.assertEqual(res.status_code, 200, new)
        self.assertNotEqual(new["track"]["isrc"], isrc)
        tracks = self.client.get("/api/tracks").get_json()["tracks"]
        self.assertEqual(len(tracks), 2)

        pkg = self.client.get(f"/api/flstudio-package/{isrc}").get_json()
        self.assertTrue(pkg["success"])

    def test_edit_errors(self):
        self.assertEqual(self.client.get("/api/project/NOPE").status_code, 404)
        res = self.client.post("/api/generate", json={"genre": "synthwave", "bars": 4})
        isrc = res.get_json()["track"]["isrc"]
        res = self.client.post(f"/api/project/{isrc}/render", json={"edits": {"muted": {r: True for r in ROLES}}})
        self.assertEqual(res.status_code, 400)


if __name__ == "__main__":
    unittest.main()
