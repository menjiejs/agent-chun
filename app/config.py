import os
import sys
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def candidate_env_files(
    home=None,
    project_root=None,
    bundled_root=None,
    desktop=False,
):
    home = Path.home() if home is None else Path(home)
    project_root = PROJECT_ROOT if project_root is None else Path(project_root)
    if bundled_root is None:
        bundled_root = Path(getattr(sys, "_MEIPASS", project_root))
    user_config = home / "Library" / "Application Support" / "Zhichun" / ".env"
    project_config = project_root / ".env"
    bundled_config = Path(bundled_root) / ".env"
    if desktop:
        return [user_config, project_config, bundled_config]
    return [project_config, bundled_config, user_config]


def model_root(packaged=None, home=None, project_root=None):
    if packaged is None:
        packaged = bool(getattr(sys, "frozen", False))
    home = Path.home() if home is None else Path(home)
    project_root = PROJECT_ROOT if project_root is None else Path(project_root)
    if packaged:
        return home / "Library" / "Application Support" / "Zhichun" / "models"
    return project_root / "models"


def data_dir(packaged=None, home=None, project_root=None):
    if packaged is None:
        packaged = bool(getattr(sys, "frozen", False))
    home = Path.home() if home is None else Path(home)
    project_root = PROJECT_ROOT if project_root is None else Path(project_root)
    if packaged:
        return home / "Library" / "Application Support" / "Zhichun" / "data"
    return project_root / "data"


def log_dir(packaged=None, home=None, project_root=None):
    if packaged is None:
        packaged = bool(getattr(sys, "frozen", False))
    home = Path.home() if home is None else Path(home)
    project_root = PROJECT_ROOT if project_root is None else Path(project_root)
    if packaged:
        return home / "Library" / "Application Support" / "Zhichun" / "logs"
    return project_root / "logs"


def character_video_path(
    packaged=None,
    home=None,
    project_root=None,
    environment=None,
):
    environment = os.environ if environment is None else environment
    configured = environment.get("ZHICHUN_VIDEO_PATH", "").strip()
    if configured:
        return Path(configured).expanduser()
    if packaged is None:
        packaged = bool(getattr(sys, "frozen", False))
    home = Path.home() if home is None else Path(home)
    project_root = PROJECT_ROOT if project_root is None else Path(project_root)
    if packaged:
        return (
            home
            / "Library"
            / "Application Support"
            / "Zhichun"
            / "media"
            / "zhichun.mp4"
        )
    return project_root / "media" / "zhichun.mp4"


def load_configuration(desktop=False):
    seen = set()
    for path in candidate_env_files(desktop=desktop):
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if path.is_file():
            load_dotenv(path, override=False)
