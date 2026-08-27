import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class PackagingTest(unittest.TestCase):
    def test_desktop_app_is_not_menu_bar_only(self):
        spec = (PROJECT_ROOT / "Zhichun.spec").read_text(encoding="utf-8")

        self.assertNotIn('"LSUIElement": True', spec)


if __name__ == "__main__":
    unittest.main()
