"""Pruebas de generacion de ISRC y exportacion de catalogos."""

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from motor_musica.metadata_manager import (
    generate_isrc,
    generate_track_metadata,
    export_distribution_catalog,
)


class TestMetadata(unittest.TestCase):
    def test_isrc_format(self):
        isrc = generate_isrc(1, country="US", registrant="SHM", year=26)
        self.assertEqual(isrc, "US-SHM-26-00001")
        # 12 caracteres mas 3 guiones = 15
        self.assertEqual(len(isrc), 15)

    def test_export_catalog(self):
        meta1 = generate_track_metadata("epic_cinematic", 120, "harmonic_minor", 32.0, 1, "t1.mid", "t1.wav")
        meta2 = generate_track_metadata("synthwave", 124, "dorian", 30.0, 2, "t2.mid", "t2.wav")

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "catalog.csv")
            json_path = os.path.join(tmpdir, "catalog.json")

            export_distribution_catalog([meta1, meta2], csv_path, json_path)

            self.assertTrue(os.path.isfile(csv_path))
            self.assertTrue(os.path.isfile(json_path))

            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.assertEqual(len(data), 2)
                self.assertEqual(data[0]["isrc"], "US-SHM-26-00001")
                self.assertTrue(data[0]["content_id_certified"])


if __name__ == "__main__":
    unittest.main()
