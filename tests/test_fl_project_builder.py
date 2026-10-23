"""Pruebas del generador de proyectos editables para FL Studio."""

import os
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from motor_musica.midi_generator import generate_track_midi
from motor_musica.fl_project_builder import create_flstudio_editable_project


class TestFLProjectBuilder(unittest.TestCase):
    def test_create_flstudio_project(self):
        bundle = generate_track_midi("dark_trap", bars=2, seed=12)
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg = create_flstudio_editable_project(bundle, "TestTrapProject", tmpdir)

            self.assertTrue(os.path.isdir(pkg.folder_path))
            self.assertTrue(os.path.isfile(pkg.zip_path))
            self.assertTrue(os.path.isfile(pkg.master_midi))
            self.assertEqual(len(pkg.stems), 4)

            # Verificar contenido del ZIP
            with zipfile.ZipFile(pkg.zip_path, "r") as zf:
                namelist = zf.namelist()
                self.assertTrue(any("Master_MultiTrack.mid" in name for name in namelist))
                self.assertTrue(any("stems/01_Chords_Pads.mid" in name for name in namelist))
                self.assertTrue(any("FL_Studio_Routing_Guide.json" in name for name in namelist))


if __name__ == "__main__":
    unittest.main()
