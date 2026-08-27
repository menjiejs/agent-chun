import hashlib
import tempfile
import unittest
from pathlib import Path

from app.model_installer import install_models


class ModelInstallerTest(unittest.TestCase):
    def setUp(self):
        self.contents = {
            "encoder.int8.onnx": b"encoder",
            "decoder.int8.onnx": b"decoder",
            "tokens.txt": b"tokens",
        }
        self.hashes = {
            name: hashlib.sha256(content).hexdigest()
            for name, content in self.contents.items()
        }

    def _downloader(self, calls):
        def download(url, destination):
            calls.append((url, destination.name))
            model = destination / "model"
            model.mkdir(parents=True)
            for name, content in self.contents.items():
                (model / name).write_bytes(content)

        return download

    def test_installs_verified_model_atomically(self):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "models"

            install_models(
                root,
                downloader=self._downloader(calls),
                expected_hashes=self.hashes,
            )

            installed = root / "asr" / "model"
            self.assertEqual((installed / "encoder.int8.onnx").read_bytes(), b"encoder")

        self.assertEqual([name for _, name in calls], ["asr"])
        self.assertTrue(all(url.startswith("https://") for url, _ in calls))

    def test_failed_download_preserves_existing_directory(self):
        def fail_download(url, destination):
            raise OSError("network failed")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "models"
            existing = root / "asr"
            existing.mkdir(parents=True)
            marker = existing / "keep.txt"
            marker.write_text("keep", encoding="utf-8")

            with self.assertRaises(OSError):
                install_models(
                    root,
                    downloader=fail_download,
                    expected_hashes=self.hashes,
                )

            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_valid_existing_model_skips_duplicate_download(self):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "models"
            install_models(
                root,
                downloader=self._downloader(calls),
                expected_hashes=self.hashes,
            )
            install_models(
                root,
                downloader=self._downloader(calls),
                expected_hashes=self.hashes,
            )

        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
