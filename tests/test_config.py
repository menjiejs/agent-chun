import unittest
from pathlib import Path

from app.config import (
    candidate_env_files,
    character_video_path,
    data_dir,
    log_dir,
    model_root,
)


class ConfigTest(unittest.TestCase):
    def test_user_application_support_config_has_priority(self):
        paths = candidate_env_files(
            home=Path("/Users/example"),
            project_root=Path("/project"),
            bundled_root=Path("/bundle"),
            desktop=True,
        )

        self.assertEqual(
            paths,
            [
                Path("/Users/example/Library/Application Support/Zhichun/.env"),
                Path("/project/.env"),
                Path("/bundle/.env"),
            ],
        )

    def test_server_prefers_project_config(self):
        paths = candidate_env_files(
            home=Path("/Users/example"),
            project_root=Path("/project"),
            bundled_root=Path("/bundle"),
        )

        self.assertEqual(
            paths[0],
            Path("/project/.env"),
        )

    def test_packaged_app_stores_models_in_application_support(self):
        root = model_root(
            packaged=True,
            home=Path("/Users/example"),
            project_root=Path("/project"),
        )

        self.assertEqual(
            root,
            Path("/Users/example/Library/Application Support/Zhichun/models"),
        )

    def test_packaged_app_stores_history_in_application_support(self):
        root = data_dir(
            packaged=True,
            home=Path("/Users/example"),
            project_root=Path("/project"),
        )

        self.assertEqual(
            root,
            Path("/Users/example/Library/Application Support/Zhichun/data"),
        )

    def test_packaged_app_reads_character_video_from_application_support(self):
        path = character_video_path(
            packaged=True,
            home=Path("/Users/example"),
            project_root=Path("/project"),
            environment={},
        )

        self.assertEqual(
            path,
            Path("/Users/example/Library/Application Support/Zhichun/media/zhichun.mp4"),
        )

    def test_packaged_app_stores_logs_in_application_support(self):
        root = log_dir(
            packaged=True,
            home=Path("/Users/example"),
            project_root=Path("/project"),
        )

        self.assertEqual(
            root,
            Path("/Users/example/Library/Application Support/Zhichun/logs"),
        )


if __name__ == "__main__":
    unittest.main()
