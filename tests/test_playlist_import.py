"""Pruebas de Importar Playlist: rasgos abstractos, clasificacion por genero y composicion."""

from pathlib import Path
import random
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

import app as app_module
from motor_musica.content_id_checks import detect_key, fingerprint_match_ratio, hash_match_ratio, landmark_hashes
from motor_musica.midi_generator import generate_track_midi
from motor_musica.playlist_import import (
    PlaylistEntry,
    StyleFeatures,
    StyleTarget,
    classify_genre,
    fitted_transpose,
    list_playlist_entries,
    note_chroma,
    target_bpm_for,
    transpose_for,
)
from motor_musica.synth_renderer import SynthConfig, render_midi_to_wav
from motor_musica.theory import circle_distance, parse_key_name
from motor_musica.youtube_dna import MINOR_PROFILE


def features(bpm, mode, bright, bass, perc, onsets):
    return StyleFeatures(bpm, f"A {mode}", mode, 0.8, bright, bass, perc, onsets, -14.0, [0.5] * 12)


class TestClassification(unittest.TestCase):
    def test_typical_genres(self):
        self.assertEqual(classify_genre(features(142, "minor", 1700, 0.65, 0.5, 4.8))[0], "dark_trap")
        self.assertEqual(classify_genre(features(78, "minor", 1200, 0.33, 0.4, 2.0))[0], "lofi_chill")
        self.assertEqual(classify_genre(features(92, "minor", 1600, 0.45, 0.56, 3.0))[0], "boom_bap")
        self.assertEqual(classify_genre(features(136, "major", 2800, 0.2, 0.48, 5.2))[0], "hard_rock")

    def test_half_time_trap(self):
        # Un trap se mide a veces a medio tiempo (70 BPM): graves y densidad deciden
        genre, _, ranking, reason, _ = classify_genre(features(70, "minor", 1700, 0.65, 0.5, 4.8))
        self.assertEqual(genre, "dark_trap")
        self.assertEqual(len(ranking), 6)
        self.assertIn("BPM", reason)

    def test_tempo_and_key_targets(self):
        self.assertEqual(target_bpm_for("dark_trap", 70), 140)
        self.assertEqual(target_bpm_for("lofi_chill", 160), 80)
        self.assertEqual(transpose_for("lofi_chill", "E minor"), 4)  # C -> E
        self.assertEqual(transpose_for("lofi_chill", "C major"), -3)  # relativa menor A, camino corto
        self.assertEqual(transpose_for("dark_trap", "D minor"), 0)

    def test_modal_composers_land_in_source_key(self):
        # Un dorico no suena en su tonica: la transposicion se ajusta a las notas compuestas
        source = parse_key_name("C# minor")
        target = StyleTarget("synthwave", 109, source.name, list(np.roll(MINOR_PROFILE, source.pitch_class)), [])
        for genre in ("synthwave", "boom_bap"):
            target.genre = genre
            for seed in (1, 2, 3):
                t = fitted_transpose(genre, seed, 16, target)
                key = detect_key(np.roll(note_chroma(genre, seed, 16), t))
                self.assertLessEqual(circle_distance(key, source), 1, f"{genre} seed {seed}: {key.name}")


class TestFingerprintFromHashes(unittest.TestCase):
    def test_same_ratio_as_audio_version(self):
        rng = np.random.default_rng(1)
        a = rng.standard_normal(11025 * 4).astype(np.float32)
        b = np.concatenate([np.zeros(5000, np.float32), a])[: len(a)]
        stored = [[list(h), t] for h, t in landmark_hashes(b, 11025)]  # como se guarda en JSON
        self.assertAlmostEqual(
            hash_match_ratio(landmark_hashes(a, 11025), stored), fingerprint_match_ratio(a, 11025, b, 11025)
        )


class TestListPlaylist(unittest.TestCase):
    def _fake_ydl(self, info):
        ydl = mock.MagicMock()
        ydl.__enter__.return_value.extract_info.return_value = info
        return mock.patch("yt_dlp.YoutubeDL", return_value=ydl)

    def test_flat_entries_and_single_video(self):
        info = {"title": "Mi lista", "entries": [{"id": "abc", "title": "Uno"}, None, {"url": "https://youtu.be/x", "title": "Dos"}]}
        with self._fake_ydl(info):
            title, entries = list_playlist_entries("https://www.youtube.com/playlist?list=PL1", 10)
        self.assertEqual(title, "Mi lista")
        self.assertEqual([e.url for e in entries], ["https://www.youtube.com/watch?v=abc", "https://youtu.be/x"])
        with self._fake_ydl({"title": "Video", "webpage_url": "https://www.youtube.com/watch?v=z"}):
            _, entries = list_playlist_entries("https://www.youtube.com/watch?v=z")
        self.assertEqual(len(entries), 1)

    def test_shuffle_picks_random_subset_in_order(self):
        info = {"title": "Larga", "entries": [{"id": f"v{i}", "title": f"T{i}"} for i in range(40)]}
        with self._fake_ydl(info):
            _, entries = list_playlist_entries("https://www.youtube.com/playlist?list=PL1", 20, shuffle=True, rng=random.Random(7))
        titles = [e.title for e in entries]
        self.assertEqual(len(titles), 20)
        self.assertEqual(len(set(titles)), 20)
        self.assertNotEqual(titles, [f"T{i}" for i in range(20)])
        self.assertEqual(titles, sorted(titles, key=lambda t: int(t[1:])))
        self.assertEqual([e.index for e in entries], list(range(20)))


class TestPlaylistApi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        dirs = {
            "AUDIO_DIR": root / "audio",
            "MIDI_DIR": root / "midi",
            "META_DIR": root / "meta",
            "PROJECTS_DIR": root / "meta" / "projects",
            "PLAYLISTS_DIR": root / "meta" / "playlists",
        }
        for d in dirs.values():
            d.mkdir(parents=True, exist_ok=True)
        self.patches = [mock.patch.object(app_module, k, v) for k, v in dirs.items()]
        # En la prueba el analisis corre en el mismo hilo
        self.patches.append(mock.patch.object(app_module, "_run_in_background", lambda fn: fn()))
        # Las "canciones" de la playlist son WAV locales (load_source_audio acepta rutas)
        entries = []
        for i, (genre, seed) in enumerate([("lofi_chill", 3), ("dark_trap", 5)]):
            wav = str(root / f"fuente_{i}.wav")
            render_midi_to_wav(generate_track_midi(genre, bars=6, seed=seed), wav, SynthConfig(sample_rate=22050))
            entries.append(PlaylistEntry(i, wav, f"Tema {i}"))
        entries.append(PlaylistEntry(2, str(root / "no_existe.wav"), "Borrado"))
        self.patches.append(mock.patch.object(app_module, "list_playlist_entries", return_value=("Lista", entries)))
        for p in self.patches:
            p.start()
        self.client = app_module.app.test_client()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_import_classify_and_compose(self):
        self.assertEqual(self.client.post("/api/playlist/import", json={"url": "no-es-link"}).status_code, 400)
        res = self.client.post("/api/playlist/import", json={"url": "https://www.youtube.com/playlist?list=PLx"}).get_json()
        job = self.client.get(f"/api/playlist/job/{res['job_id']}").get_json()
        self.assertEqual(job["status"], "done", job)
        pl = self.client.get(f"/api/playlist/{job['playlist_id']}").get_json()["playlist"]
        self.assertEqual(len(pl["tracks"]), 3)
        self.assertIsNotNone(pl["tracks"][2]["error"])  # un video caido no frena la playlist
        self.assertNotIn("fingerprint", pl["tracks"][0])
        for t in pl["tracks"][:2]:
            self.assertIn(t["genre"], [g["id"] for g in pl["genres"]])
            self.assertGreater(t["features"]["bpm"], 0)
        self.assertIn("No se transcribe", pl["note"])

        # Corregir el genero a mano
        pid = pl["id"]
        pl = self.client.post(f"/api/playlist/{pid}/genre", json={"index": 0, "genre": "boom_bap"}).get_json()["playlist"]
        self.assertEqual(pl["tracks"][0]["genre"], "boom_bap")
        self.assertTrue(pl["tracks"][0]["genre_overridden"])

        # Un tema nuevo por cancion, con proyecto editable y checks de huella por fuente
        out = self.client.post(f"/api/playlist/{pid}/compose", json={"mode": "per_track", "indices": [0], "bars": 8}).get_json()
        self.assertTrue(out["success"], out)
        result = out["results"][0]
        self.assertEqual(result["genre"], "boom_bap")
        names = {c["check"]: c for c in result["report"]["checks"]}
        self.assertTrue(names["huella_content_id[#1]"]["passed"])
        self.assertTrue(names["cero_samples"]["passed"])
        isrc = result["track"]["isrc"]
        project = self.client.get(f"/api/project/{isrc}").get_json()
        self.assertTrue(project["success"])
        self.assertEqual(project["project"]["genre"], "boom_bap")

        # Un tema por genero
        out = self.client.post(f"/api/playlist/{pid}/compose", json={"mode": "per_genre", "bars": 8}).get_json()
        self.assertTrue(out["success"], out)
        self.assertEqual(len(out["results"]), len(pl["groups"]))
        pl = self.client.get(f"/api/playlist/{pid}").get_json()["playlist"]
        self.assertEqual(len(pl["generated"]), 1 + len(out["results"]))


if __name__ == "__main__":
    unittest.main()
