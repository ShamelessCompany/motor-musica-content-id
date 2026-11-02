"""El sello content_id_certified tiene que salir de checks reales, no estar fijo en True."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from motor_musica.content_id_checks import CheckResult
from motor_musica.metadata_manager import generate_track_metadata
from motor_musica.synth_renderer import AudioMetrics


def metricas(lufs=-14.0, peak=-1.2, clipped=0):
    return AudioMetrics(duration_sec=40.0, sample_rate=44100, peak_dbfs=peak, rms_dbfs=-16.0,
                        estimated_lufs=lufs, clipped_samples=clipped)


def meta(**extra):
    return generate_track_metadata("synthwave", 120, "dorian", 40.0, 1, "t.mid", "t.wav", **extra)


class TestCertificacion(unittest.TestCase):
    def test_sin_checks_no_esta_certificado(self):
        m = meta()
        self.assertFalse(m.content_id_certified)
        self.assertEqual(m.content_id_checks, "sin verificar")

    def test_master_correcto_certifica(self):
        m = meta(metrics=metricas())
        self.assertTrue(m.content_id_certified)
        self.assertIn("sonoridad_lufs=ok", m.content_id_checks)

    def test_sonoridad_fuera_de_rango_no_certifica(self):
        # Caso real del catálogo: track_01 quedó a -18 LUFS
        m = meta(metrics=metricas(lufs=-18.07))
        self.assertFalse(m.content_id_certified)
        self.assertIn("sonoridad_lufs=falla", m.content_id_checks)

    def test_clipping_no_certifica(self):
        self.assertFalse(meta(metrics=metricas(clipped=12)).content_id_certified)

    def test_checks_explicitos_mandan(self):
        # La fusión pasa su propio informe (incluye la huella contra las fuentes)
        malos = [CheckResult("sonoridad_lufs", True, -14.0, ""),
                 CheckResult("huella_fuente_1", False, 0.4, "comparte audio con la fuente")]
        m = meta(metrics=metricas(), checks=malos)
        self.assertFalse(m.content_id_certified)
        self.assertIn("huella_fuente_1=falla", m.content_id_checks)


if __name__ == "__main__":
    unittest.main()
