"""Pruebas del generador de licencias de beats."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from motor_musica.license_generator import (
    LicenseTier,
    TIER_SPECS,
    generate_beat_license_agreement,
)


class TestLicenseGenerator(unittest.TestCase):
    def test_tiers_defined(self):
        for tier in LicenseTier:
            self.assertIn(tier, TIER_SPECS)
            self.assertTrue(TIER_SPECS[tier]["price_usd"] > 0)

    def test_generate_contract_text(self):
        contract = generate_beat_license_agreement(
            beat_title="Savage 808 Trap",
            buyer_name="MC Flow Latino",
            tier=LicenseTier.PREMIUM_WAV,
            bpm=140,
            key_name="D minor",
            isrc="US-SHM-26-00005",
        )
        self.assertIn("Savage 808 Trap", contract)
        self.assertIn("MC Flow Latino", contract)
        self.assertIn("US-SHM-26-00005", contract)
        self.assertIn("$49.00 USD", contract)
        self.assertIn("50%", contract)


if __name__ == "__main__":
    unittest.main()
