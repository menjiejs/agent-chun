from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)


ASSET_DIR = Path(__file__).resolve().parent / "assets"


class CharacterImage(QLabel):
    def __init__(self, path):
        super().__init__()
        self.source = QPixmap(str(path))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.source.isNull():
            self.setPixmap(
                self.source.scaled(
                    self.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )


class CharacterDisplay(QWidget):
    def __init__(self, video_path=None):
        super().__init__()
        self.player = None
        self.audio_output = None
        self.video_widget = None
        self.stack = QStackedLayout(self)
        self.stack.setContentsMargins(22, 30, 22, 58)
        self.placeholder = CharacterImage(ASSET_DIR / "zhichun-placeholder.png")
        self.stack.addWidget(self.placeholder)
        if video_path and Path(video_path).is_file():
            self._load_video(Path(video_path))

    def _load_video(self, path):
        self.video_widget = QVideoWidget()
        self.video_widget.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        self.audio_output = QAudioOutput()
        self.audio_output.setMuted(True)
        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_widget)
        self.player.setLoops(QMediaPlayer.Loops.Infinite)
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.player.errorOccurred.connect(self._video_failed)
        self.stack.addWidget(self.video_widget)
        self.stack.setCurrentWidget(self.video_widget)
        self.player.play()

    def _video_failed(self, error, error_string):
        del error, error_string
        self.stack.setCurrentWidget(self.placeholder)


class MainWindow(QMainWindow):
    message_submitted = Signal(str)
    voice_toggled = Signal(bool)
    hide_requested = Signal()
    quit_requested = Signal()

    def __init__(self, video_path=None):
        super().__init__()
        self.setWindowTitle("芷春")
        self.resize(1120, 760)
        self.setMinimumSize(760, 560)
        self._history_expanded = False
        self._build_ui(video_path)
        self._apply_style()

    def _build_ui(self, video_path):
        central = QWidget()
        central.setObjectName("root")
        self.main_layout = QHBoxLayout(central)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.stage = QFrame()
        self.stage.setObjectName("stage")
        stage_layout = QGridLayout(self.stage)
        stage_layout.setContentsMargins(0, 0, 0, 0)
        stage_layout.setSpacing(0)

        self.character_display = CharacterDisplay(video_path)
        stage_layout.addWidget(self.character_display, 1, 0, 1, 2)
        stage_layout.setRowStretch(1, 1)

        self.status_indicator = QLabel()
        self.status_indicator.setObjectName("statusIndicator")
        self.status_indicator.setFixedSize(8, 8)
        self.status_indicator.setAccessibleName("语音状态")
        self.status_text = QLabel()
        self.status_text.setObjectName("statusText")
        status_area = QWidget()
        status_layout = QHBoxLayout(status_area)
        status_layout.setContentsMargins(20, 0, 0, 0)
        status_layout.setSpacing(8)
        status_layout.addWidget(self.status_indicator)
        status_layout.addWidget(self.status_text)
        stage_layout.addWidget(
            status_area,
            0,
            0,
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
        )
        stage_layout.setContentsMargins(0, 18, 0, 18)

        window_controls = QWidget()
        window_controls.setObjectName("windowControls")
        controls_layout = QHBoxLayout(window_controls)
        controls_layout.setContentsMargins(0, 0, 18, 0)
        controls_layout.setSpacing(6)
        self.hide_button = QPushButton("−")
        self.hide_button.setObjectName("windowControl")
        self.hide_button.setAccessibleName("隐藏到菜单栏")
        self.hide_button.setToolTip("隐藏到菜单栏")
        self.hide_button.clicked.connect(self.hide_requested.emit)
        controls_layout.addWidget(self.hide_button)
        self.quit_button = QPushButton("×")
        self.quit_button.setObjectName("windowControl")
        self.quit_button.setAccessibleName("退出芷春")
        self.quit_button.setToolTip("退出芷春")
        self.quit_button.clicked.connect(self.quit_requested.emit)
        controls_layout.addWidget(self.quit_button)
        stage_layout.addWidget(
            window_controls,
            0,
            1,
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
        )

        self.history_button = QPushButton("‹")
        self.history_button.setObjectName("historyButton")
        self.history_button.setAccessibleName("展开聊天历史")
        self.history_button.setToolTip("展开聊天历史")
        self.history_button.setFixedSize(28, 68)
        self.history_button.clicked.connect(self.toggle_history)
        stage_layout.addWidget(
            self.history_button,
            1,
            1,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )

        bottom = QWidget()
        bottom.setObjectName("stageBottom")
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(60, 0, 60, 0)
        bottom_layout.setSpacing(11)
        self.subtitle_label = QLabel("")
        self.subtitle_label.setObjectName("currentSubtitle")
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle_label.setWordWrap(True)
        bottom_layout.addWidget(self.subtitle_label)
        self.stage_composer = self._create_composer(primary=True)
        bottom_layout.addWidget(self.stage_composer)
        stage_layout.addWidget(bottom, 2, 0, 1, 2)

        self.main_layout.addWidget(self.stage, 1)
        self.history_panel = self._create_history_panel()
        self.history_panel.hide()
        self.main_layout.addWidget(self.history_panel, 1)
        self.main_layout.setStretch(0, 1)
        self.main_layout.setStretch(1, 1)
        self.setCentralWidget(central)
        self.set_status("等待“芷春”")

    def _create_composer(self, primary=False):
        composer = QFrame()
        composer.setObjectName("composer")
        layout = QHBoxLayout(composer)
        layout.setContentsMargins(14, 7, 7, 7)
        layout.setSpacing(7)

        field = QLineEdit()
        field.setPlaceholderText("输入消息")
        field.setAccessibleName("消息输入框")
        field.returnPressed.connect(lambda f=field: self._submit_from(f))
        layout.addWidget(field, 1)

        voice = QPushButton("●")
        voice.setObjectName("voiceButton")
        voice.setCheckable(True)
        voice.setChecked(True)
        voice.setAccessibleName("语音唤醒")
        voice.setToolTip("暂停语音唤醒")
        voice.toggled.connect(self._voice_changed)
        layout.addWidget(voice)

        send = QPushButton("↑")
        send.setObjectName("sendButton")
        send.setAccessibleName("发送")
        send.clicked.connect(lambda checked=False, f=field: self._submit_from(f))
        layout.addWidget(send)

        if primary:
            self.input = field
            self.voice_button = voice
            self.send_button = send
        else:
            self.history_input = field
            self.history_voice_button = voice
            self.history_send_button = send
        return composer

    def _create_history_panel(self):
        panel = QFrame()
        panel.setObjectName("historyPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(28, 54, 28, 18)
        layout.setSpacing(12)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.messages = QWidget()
        self.messages.setObjectName("messages")
        self.message_layout = QVBoxLayout(self.messages)
        self.message_layout.setContentsMargins(0, 8, 0, 8)
        self.message_layout.setSpacing(12)
        self.message_layout.addStretch()
        self.scroll.setWidget(self.messages)
        layout.addWidget(self.scroll, 1)
        self.history_composer = self._create_composer(primary=False)
        layout.addWidget(self.history_composer)
        return panel

    def _apply_style(self):
        self.setStyleSheet(
            """
            QMainWindow, QWidget#root { background: #000; color: #eee; }
            QFrame#stage {
                background: qradialgradient(cx:0.5, cy:0.42, radius:0.72,
                            stop:0 #151b17, stop:0.48 #070907, stop:1 #000000);
                border: none;
            }
            QLabel#statusIndicator {
                background: #d9f7e2; border-radius: 4px;
            }
            QLabel#statusText {
                color: #a6a6a6; font-size: 12px;
            }
            QWidget#windowControls { background: transparent; }
            QPushButton#windowControl {
                min-width: 26px; max-width: 26px; min-height: 26px; max-height: 26px;
                border: 1px solid #343434; border-radius: 13px;
                background: rgba(12,12,12,170); color: #a0a0a0; font-size: 16px;
            }
            QPushButton#windowControl:hover {
                background: #252525; color: #ffffff; border-color: #606060;
            }
            QLabel#currentSubtitle {
                color: rgba(245,245,245,220); font-size: 15px;
                padding: 4px 12px; background: transparent;
            }
            QFrame#composer {
                background: #171717; border: 1px solid #4a4a4a;
                border-radius: 23px;
            }
            QLineEdit {
                color: #ededed; background: transparent; border: none;
                font-size: 14px; padding: 7px 5px;
                selection-background-color: #486151;
            }
            QLineEdit::placeholder { color: #555; }
            QPushButton { border: none; color: #d8d8d8; }
            QPushButton#sendButton {
                min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px;
                border-radius: 15px; background: #eeeeee; color: #111;
                font-size: 17px; font-weight: 600;
            }
            QPushButton#voiceButton {
                min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px;
                border-radius: 15px; background: #1d1d1d; color: #666; font-size: 8px;
            }
            QPushButton#voiceButton:checked { color: #bceac9; background: #19221c; }
            QPushButton#historyButton {
                background: rgba(18,18,18,235); border: 1px solid #343434;
                border-right: none; border-radius: 14px 0 0 14px;
                color: #a6a6a6; font-size: 20px;
            }
            QFrame#historyPanel {
                background: #080808; border-left: 1px solid #252525;
            }
            QScrollArea, QWidget#messages { background: transparent; border: none; }
            QLabel[role="assistant"] {
                background: #151515; color: #bdbdbd; border-radius: 15px;
                padding: 11px 14px; font-size: 14px;
            }
            QLabel[role="user"] {
                background: #202522; color: #ededed; border-radius: 15px;
                padding: 11px 14px; font-size: 14px;
            }
            QLabel[role="system"] {
                color: #9a6960; padding: 7px; font-size: 12px;
            }
            """
        )

    def _submit_from(self, field):
        text = field.text().strip()
        if not text:
            return
        field.clear()
        self.message_submitted.emit(text)

    def enter_immersive(self):
        QTimer.singleShot(350, self.showFullScreen)

    def _voice_changed(self, enabled):
        source = self.sender()
        other = (
            self.history_voice_button
            if source is self.voice_button
            else self.voice_button
        )
        other.blockSignals(True)
        other.setChecked(enabled)
        other.blockSignals(False)
        tip = "暂停语音唤醒" if enabled else "开启语音唤醒"
        self.voice_button.setToolTip(tip)
        self.history_voice_button.setToolTip(tip)
        self.voice_toggled.emit(enabled)

    def toggle_history(self):
        self._history_expanded = not self._history_expanded
        self.history_panel.setVisible(self._history_expanded)
        self.history_button.setText("›" if self._history_expanded else "‹")
        self.history_button.setAccessibleName(
            "收起聊天历史" if self._history_expanded else "展开聊天历史"
        )
        self.stage_composer.setVisible(not self._history_expanded)
        if self._history_expanded:
            self.history_input.setFocus()

    def set_status(self, text):
        self.status_text.setText(text)
        self.status_indicator.setToolTip(text)
        self.status_indicator.setAccessibleDescription(text)
        colors = {
            "正在聆听…": "#ffffff",
            "正在思考…": "#d6c792",
            "正在回答…": "#9edcaf",
            "语音唤醒已暂停": "#555555",
            "麦克风不可用": "#a85f56",
        }
        color = colors.get(text, "#bceac9")
        self.status_indicator.setStyleSheet(
            f"background:{color}; border-radius:4px; margin-right:20px;"
        )

    def set_busy(self, busy):
        for widget in (
            self.input,
            self.send_button,
            self.history_input,
            self.history_send_button,
        ):
            widget.setEnabled(not busy)

    def add_message(self, role, text):
        row = QHBoxLayout()
        bubble = QLabel(text)
        bubble.setProperty("role", role)
        bubble.setWordWrap(True)
        bubble.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        bubble.setMaximumWidth(430)
        if role == "user":
            row.addStretch()
            row.addWidget(bubble)
        elif role == "system":
            row.addStretch()
            row.addWidget(bubble)
            row.addStretch()
        else:
            row.addWidget(bubble)
            row.addStretch()
            self.subtitle_label.setText(text)
        self.message_layout.insertLayout(self.message_layout.count() - 1, row)
        self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()
        )

    def closeEvent(self, event):
        self.hide()
        event.ignore()
