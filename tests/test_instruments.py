"""Pruebas del rack de instrumentos procedurales y su eleccion automatica por timbre."""

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import mido
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app as app_module
from motor_musica.fl_project_builder import create_flstudio_editable_project
from motor_musica.instruments import (
    INSTRUMENTS,
    ROLE_LEVEL,
    ROLES,
    TimbreProfile,
    resolve_rack,
    suggest_instruments,
)
from motor_musica.midi_generator import generate_track_midi
from motor_musica.synth_renderer import SynthConfig, render_midi_to_wav


class TestInstrumentCatalog(unittest.TestCase):
    def test_every_instrument_renders_clean_audio(self):
        sr = 22050
        for iid, inst in INSTRUMENTS.items():
            pitch = 38 if inst.role == "drums" else (45 if inst.role == "bass" else 69)
            left, right = inst.render(pitch, 100, 0.4, sr)
            with self.subTest(instrument=iid):
                self.assertEqual(len(left), len(right))
                self.assertTrue(np.all(np.isfinite(left)) and np.all(np.isfinite(right)))
                peak = float(max(np.max(np.abs(left)), np.max(np.abs(right))))
                self.assertGreater(peak, 1e-3)
                self.assertLessEqual(peak, ROLE_LEVEL[inst.role] * 1.25)

    def test_each_role_has_choices(self):
        for role in ROLES:
            self.assertGreaterEqual(len([i for i in INSTRUMENTS.values() if i.role == role]), 3)

    def test_resolve_rack_rejects_wrong_role(self):
        rack = resolve_rack({"lead": "tuba", "bass": "tuba", "pad": "no_existe"})
        self.assertEqual(rack["bass"], "tuba")
        self.assertNotEqual(rack["lead"], "tuba")
        self.assertEqual(set(rack), set(ROLES))


class TestAutoSelection(unittest.TestCase):
    def test_pvz_style_uses_gothic_palette(self):
        rack, reasons = suggest_instruments([TimbreProfile(1500, 0.4, 0.5)], 120, True, "pvz_gotico_swing")
        self.assertEqual(rack["pad"], "gothic_organ")
        self.assertEqual(rack["bass"], "upright_pluck")
        self.assertIn("brillo", reasons["lead"])

    def test_trap_source_gets_808(self):
        rack, _ = suggest_instruments([TimbreProfile(1200, 0.8, 0.6)], 140, True, "seguir_fuente")
        self.assertEqual(rack["bass"], "sub_808")
        self.assertEqual(rack["drums"], "trap_808_kit")

    def test_bright_light_source_gets_chip_sounds(self):
        rack, _ = suggest_instruments([TimbreProfile(3000, 0.1, 0.5)], 110, False, "seguir_fuente")
        self.assertEqual(rack["lead"], "saw_lead")
        self.assertEqual(rack["drums"], "chip_kit")


class TestRackInPipeline(unittest.TestCase):
    def test_render_with_rack_keeps_master_standard(self):
        bundle = generate_track_midi("synthwave", bars=4, seed=7)
        rack = {"lead": "pizzicato", "pad": "gothic_organ", "bass": "tuba", "drums": "chip_kit"}
        with tempfile.TemporaryDirectory() as tmpdir:
            metrics = render_midi_to_wav(bundle, os.path.join(tmpdir, "r.wav"), SynthConfig(sample_rate=22050), instruments=rack)
        self.assertLessEqual(metrics.peak_dbfs, -0.95)
        self.assertLessEqual(abs(metrics.estimated_lufs + 14.0), 2.0)

    def test_fl_package_carries_programs_and_plugins(self):
        bundle = generate_track_midi("lofi_chill", bars=2, seed=1)
        rack = {"lead": "flute", "pad": "choir", "bass": "upright_pluck", "drums": "acoustic_kit"}
        with tempfile.TemporaryDirectory() as tmpdir:
            info = create_flstudio_editable_project(bundle, "RackTest", tmpdir, instruments=rack)
            folder = Path(info.folder_path)
            guide = json.loads((folder / "FL_Studio_Routing_Guide.json").read_text(encoding="utf-8"))
            vsts = [c["recommended_vst"] for c in guide["channel_rack_mapping"]]
            self.assertIn("Flauta", vsts[1])
            lead = mido.MidiFile(str(folder / "stems" / "02_Melody_Lead.mid"))
            programs = [m.program for t in lead.tracks for m in t if m.type == "program_change"]
            self.assertEqual(programs, [INSTRUMENTS["flute"].gm_program])


class TestInstrumentApi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        dirs = {
            "AUDIO_DIR": root / "audio", "MIDI_DIR": root / "midi", "META_DIR": root / "meta",
            "FL_SCRIPTS_DIR": root / "scripts", "PREVIEWS_DIR": root / "previews",
            "PROJECTS_DIR": root / "projects",
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

    def test_catalog_and_preview(self):
        body = self.client.get("/api/instruments").get_json()
        self.assertEqual(set(body["roles"]), set(ROLES))
        res = self.client.get("/api/instrument-preview/fm_bell")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.mimetype, "audio/wav")
        res.close()
        self.assertEqual(self.client.get("/api/instrument-preview/nada").status_code, 404)

    def test_generate_with_rack_sets_midi_programs(self):
        res = self.client.post("/api/generate", json={
            "genre": "synthwave", "bars": 2, "instruments": {"lead": "nes_pulse", "bass": "acid_303"},
        })
        track = res.get_json()["track"]
        mid = mido.MidiFile(str(app_module.MIDI_DIR / track["midi_filename"]))
        programs = {m.channel: m.program for t in mid.tracks for m in t if m.type == "program_change"}
        self.assertEqual(programs[1], INSTRUMENTS["nes_pulse"].gm_program)
        self.assertEqual(programs[2], INSTRUMENTS["acid_303"].gm_program)


if __name__ == "__main__":
    unittest.main()
