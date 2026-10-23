"""Pruebas del puente FL Studio CLI."""

import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from motor_musica.flstudio_cli import FLStudioCLI


class TestFLStudioCLI(unittest.TestCase):
    def test_build_render_command(self):
        cli = FLStudioCLI(executable_path=r"C:\MockPath\FL64.exe")
        cmd = cli.build_render_command(
            project_flp=r"D:\Project\Template.flp",
            output_dir=r"D:\Project\output",
            audio_format="wav",
        )
        self.assertEqual(cmd[0], r"C:\MockPath\FL64.exe")
        self.assertIn("/R", cmd)
        self.assertIn("/Fwav", cmd)
        self.assertIn(r"/OD:\Project\output", cmd)
        self.assertIn(r"D:\Project\Template.flp", cmd)

    def test_generate_powershell_script(self):
        cli = FLStudioCLI(executable_path=r"C:\MockPath\FL64.exe")
        with tempfile.TemporaryDirectory() as tmpdir:
            ps1_path = os.path.join(tmpdir, "render.ps1")
            cli.generate_powershell_script(
                project_flp=r"D:\Template.flp",
                output_dir=r"D:\output",
                output_ps1_path=ps1_path,
            )
            self.assertTrue(os.path.isfile(ps1_path))
            with open(ps1_path, "r", encoding="utf-8") as f:
                content = f.read()
                self.assertIn("FL64.exe", content)
                self.assertIn("/R /Fwav", content)


if __name__ == "__main__":
    unittest.main()
