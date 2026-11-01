"""Pruebas del endpoint /api/harmonic-fusion (links + temas descargados)."""

import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import imageio_ffmpeg

import app as app_module
from motor_musica.midi_generator import generate_track_midi
from motor_musica.synth_renderer import SynthConfig, render_midi_to_wav


class TestFusionApi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        dirs = {
            "AUDIO_DIR": root / "audio",
            "MIDI_DIR": root / "midi",
            "META_DIR": root / "meta",
            "FL_PACKAGES_DIR": root / "fl",
            "FUSION_PLANS_DIR": root / "meta" / "fusion_plans",
            "PROJECTS_DIR": root / "meta" / "projects",
        }
        for d in dirs.values():
            d.mkdir(parents=True, exist_ok=True)
        # Aislar el catalogo real de output/ durante la prueba
        self.patches = [mock.patch.object(app_module, k, v) for k, v in dirs.items()]
        for p in self.patches:
            p.start()
        self.client = app_module.app.test_client()

        self.wav = str(root / "fuente.wav")
        render_midi_to_wav(generate_track_midi("epic_cinematic", bars=6, seed=4), self.wav, SynthConfig(sample_rate=22050))
        self.mp3 = str(root / "fuente.mp3")
        subprocess.run(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-v", "error", "-i", self.wav, self.mp3],
            check=True,
        )

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_upload_downloaded_tracks(self):
        with open(self.wav, "rb") as fw, open(self.mp3, "rb") as fm:
            data = {
                "style": "seguir_fuente",
                "bars_per_section": "4",
                "files": [(io.BytesIO(fw.read()), "tema_a.wav"), (io.BytesIO(fm.read()), "tema_b.mp3")],
            }
        res = self.client.post("/api/harmonic-fusion", data=data, content_type="multipart/form-data")
        body = res.get_json()
        self.assertEqual(res.status_code, 200, body)
        self.assertEqual([s["url"] for s in body["sources"]], ["tema_a.wav", "tema_b.mp3"])
        self.assertIn("aprobado", body["report"])
        self.assertTrue((app_module.AUDIO_DIR / body["track"]["audio_filename"]).exists())
        self.assertTrue((app_module.FUSION_PLANS_DIR / f"{body['track']['isrc']}.json").exists())
        self.assertTrue((app_module.PROJECTS_DIR / f"{body['track']['isrc']}.json").exists())

        # El tema de la fusion se puede editar desde la app (instrumentos + transponer)
        isrc = body["track"]["isrc"]
        res = self.client.post(f"/api/project/{isrc}/render",
                               json={"edits": {"rack": {"lead": "violin"}, "transpose": 2}})
        edited = res.get_json()
        self.assertEqual(res.status_code, 200, edited)
        self.assertTrue(edited["report"]["aprobado"], edited["report"])
        self.assertTrue(edited["track"]["audio_filename"].endswith("_v2.wav"))
        self.assertEqual(edited["project"]["rack"]["lead"], "violin")

    def test_rejects_bad_input(self):
        res = self.client.post("/api/harmonic-fusion", json={"urls": ["file:///etc/passwd"]})
        self.assertEqual(res.status_code, 400)
        res = self.client.post(
            "/api/harmonic-fusion",
            data={"files": [(io.BytesIO(b"x"), "virus.exe")]},
            content_type="multipart/form-data",
        )
        self.assertEqual(res.status_code, 400)
        res = self.client.post("/api/harmonic-fusion", json={})
        self.assertEqual(res.status_code, 400)


if __name__ == "__main__":
    unittest.main()
