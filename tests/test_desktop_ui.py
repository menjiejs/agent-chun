import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QWidget
from PySide6.QtTest import QTest

import app.desktop_ui as desktop_ui
from app.desktop_ui import MainWindow


class DesktopUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()

    def tearDown(self):
        self.window.deleteLater()

    def _message_bubbles(self):
        return [
            (label.property("role"), label.text())
            for label in self.window.messages.findChildren(QLabel)
            if label.property("role")
        ]

    def test_preloaded_messages_keep_history_collapsed(self):
        self.window.add_message("user", "你好")
        self.window.add_message("assistant", "BOSS，您好。")

        self.assertTrue(self.window.history_panel.isHidden())
        self.assertEqual(
            self._message_bubbles(),
            [("user", "你好"), ("assistant", "BOSS，您好。")],
        )

    def test_latest_preloaded_assistant_message_is_stage_subtitle(self):
        self.window.add_message("assistant", "第一条回复")
        self.window.add_message("user", "继续")
        self.window.add_message("assistant", "最近的回复")

        self.assertEqual(self.window.subtitle_label.text(), "最近的回复")

    def test_send_button_emits_trimmed_message(self):
        messages = []
        self.window.message_submitted.connect(messages.append)
        self.window.input.setText("  你好，芷春  ")

        self.window.send_button.click()

        self.assertEqual(messages, ["你好，芷春"])
        self.assertEqual(self.window.input.text(), "")

    def test_status_text_can_be_updated(self):
        self.window.set_status("正在聆听")

        self.assertEqual(self.window.status_indicator.toolTip(), "正在聆听")

    def test_history_panel_is_hidden_until_expand_button_is_clicked(self):
        self.assertTrue(self.window.history_panel.isHidden())

        self.window.history_button.click()

        self.assertFalse(self.window.history_panel.isHidden())
        self.assertEqual(self.window.main_layout.stretch(0), 1)
        self.assertEqual(self.window.main_layout.stretch(1), 1)

    def test_interface_has_no_visible_branding_heading(self):
        visible_text = " ".join(
            label.text() for label in self.window.findChildren(QLabel)
        )

        self.assertNotIn("本地语音 AI 助手", visible_text)
        self.assertNotIn("你好，我是芷春", visible_text)

    def test_window_can_enter_immersive_fullscreen(self):
        self.window.enter_immersive()
        QTest.qWait(400)

        self.assertTrue(self.window.isFullScreen())

    def test_immersive_mode_is_deferred_until_the_event_loop(self):
        with patch.object(desktop_ui, "QTimer", create=True) as timer:
            self.window.enter_immersive()

        timer.singleShot.assert_called_once_with(350, self.window.showFullScreen)

    def test_window_controls_request_hide_and_quit(self):
        events = []
        self.window.hide_requested.connect(lambda: events.append("hide"))
        self.window.quit_requested.connect(lambda: events.append("quit"))

        self.window.hide_button.click()
        self.window.quit_button.click()

        self.assertEqual(events, ["hide", "quit"])

    def test_video_does_not_cover_the_chat_composer(self):
        self.window.resize(1120, 760)
        self.window.show()
        self.app.processEvents()
        stage_bottom = self.window.findChild(QWidget, "stageBottom")

        self.assertLess(
            self.window.character_display.geometry().bottom(),
            stage_bottom.geometry().top(),
        )

    def test_current_voice_status_is_visible(self):
        label_text = " ".join(
            label.text() for label in self.window.findChildren(QLabel)
        )

        self.assertIn("等待“芷春”", label_text)


if __name__ == "__main__":
    unittest.main()
