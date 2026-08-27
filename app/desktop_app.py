import sys
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QMenu,
    QMessageBox,
    QStyle,
    QSystemTrayIcon,
)

from app.audio_output import play_wav
from app.config import character_video_path, load_configuration, model_root
from app.desktop_controller import DesktopController
from app.desktop_service import ConversationService
from app.desktop_ui import MainWindow
from app.model_installer import install_models
from app.offline_speech import (
    MicrophoneStream,
    ModelFiles,
    SpeechWorker,
    create_sherpa_router,
)
from app.voice_session import VoiceSession


PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODEL_ROOT = model_root(project_root=PROJECT_ROOT)
ICON_PATH = Path(__file__).resolve().parent / "assets" / "zhichun-icon.png"
DISPLAYABLE_HISTORY_ROLES = {"assistant", "system", "user"}


def restore_conversation_history(window, loader, session_id):
    try:
        messages = loader(session_id)
    except Exception:
        return

    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if role not in DISPLAYABLE_HISTORY_ROLES:
            continue
        if not isinstance(content, str) or not content.strip():
            continue
        window.add_message(role, content)


class TaskSignals(QObject):
    success = Signal(object)
    error = Signal(object)


class Task(QRunnable):
    def __init__(self, work):
        super().__init__()
        self.work = work
        self.signals = TaskSignals()

    @Slot()
    def run(self):
        try:
            result = self.work()
        except Exception as exc:
            self.signals.error.emit(exc)
        else:
            self.signals.success.emit(result)


class QtScheduler:
    def __init__(self):
        self.pool = QThreadPool.globalInstance()
        self._tasks = set()

    def __call__(self, work, on_success, on_error):
        task = Task(work)
        self._tasks.add(task)

        def finish_success(result):
            try:
                on_success(result)
            finally:
                self._tasks.discard(task)

        def finish_error(error):
            try:
                on_error(error)
            finally:
                self._tasks.discard(task)

        task.signals.success.connect(finish_success)
        task.signals.error.connect(finish_error)
        self.pool.start(task)


class SpeechBridge(QObject):
    wake = Signal()
    transcript = Signal(str)
    no_speech = Signal()
    microphone_error = Signal(str)


class InactiveSpeechRouter:
    def __init__(self):
        self.paused = True

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False


class DesktopRuntime:
    def __init__(self, app):
        load_configuration(desktop=True)
        self.app = app
        self.window = MainWindow(video_path=character_video_path())
        self.bridge = SpeechBridge()
        self.scheduler = QtScheduler()
        self.microphone = None
        self.speech_router = InactiveSpeechRouter()

        from app.agent import run_conversation
        from app.history_store import load_messages
        from app.tts_client import synthesize_speech

        self.conversation_service = ConversationService(
            run_conversation,
            synthesize_speech,
        )
        self.controller = DesktopController(
            self.window,
            VoiceSession(),
            self.speech_router,
            self.conversation_service,
            play_wav,
            self.scheduler,
            QApplication.beep,
        )
        restore_conversation_history(
            self.window,
            load_messages,
            self.conversation_service.session_id,
        )
        self.bridge.wake.connect(self.controller.handle_wake)
        self.bridge.transcript.connect(self.controller.handle_transcript)
        self.bridge.no_speech.connect(self.controller.handle_no_speech)
        self.bridge.microphone_error.connect(self._microphone_error)
        self.window.message_submitted.connect(self.controller.send_text)
        self.window.voice_toggled.connect(self.controller.set_voice_enabled)
        self.window.hide_requested.connect(self.window.hide)
        self.window.quit_requested.connect(self.quit)

        self._build_tray()
        self.window.enter_immersive()
        QTimer.singleShot(0, self.prepare_speech)

    def _build_tray(self):
        icon = self.app.windowIcon()
        if icon.isNull():
            icon = self.app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.tray = QSystemTrayIcon(icon, self.app)
        self.tray.setToolTip("芷春")
        menu = QMenu()
        open_action = menu.addAction("打开芷春")
        open_action.triggered.connect(self.show_window)
        self.voice_action = menu.addAction("语音唤醒")
        self.voice_action.setCheckable(True)
        self.voice_action.setChecked(True)
        self.voice_action.toggled.connect(self.window.voice_button.setChecked)
        self.window.voice_toggled.connect(self.voice_action.setChecked)
        prepare_action = menu.addAction("准备语音模型")
        prepare_action.triggered.connect(self.prepare_speech)
        menu.addSeparator()
        quit_action = menu.addAction("退出")
        quit_action.triggered.connect(self.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_window()

    def show_window(self):
        self.window.enter_immersive()
        self.window.raise_()
        self.window.activateWindow()

    def prepare_speech(self):
        files = ModelFiles.from_root(MODEL_ROOT)
        if not files.missing():
            self._start_microphone(files)
            return

        self.window.voice_button.setChecked(False)
        answer = QMessageBox.question(
            self.window,
            "准备离线语音模型",
            "首次使用需要下载中文唤醒和识别模型。下载完成后，语音识别会在本机运行。现在开始吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.window.add_message("system", "语音模型尚未准备，文字聊天仍可使用")
            return


        self.window.set_status("正在准备离线语音模型…")
        self.window.set_busy(True)
        self.scheduler(
            lambda: install_models(MODEL_ROOT),
            self._models_ready,
            self._models_failed,
        )

    def _models_ready(self, result):
        del result
        self.window.set_busy(False)
        files = ModelFiles.from_root(MODEL_ROOT)
        if files.missing():
            self._models_failed(RuntimeError("downloaded model files are incomplete"))
            return
        self._start_microphone(files)

    def _models_failed(self, error):
        del error
        self.window.set_busy(False)
        self.window.set_status("语音模型准备失败")
        self.window.add_message("system", "语音模型下载失败，请检查网络后重试")

    def _start_microphone(self, files):
        if self.microphone is not None:
            return
        try:
            router = create_sherpa_router(
                files,
                self.bridge.wake.emit,
                self.bridge.transcript.emit,
                self.bridge.no_speech.emit,
            )
            speech_worker = SpeechWorker(router)
            microphone = MicrophoneStream(
                speech_worker,
                on_error=self.bridge.microphone_error.emit,
            )
            microphone.start()
        except Exception:
            self.window.voice_button.setChecked(False)
            self.window.set_status("麦克风不可用")
            self.window.add_message(
                "system",
                "无法启动语音，请在系统设置中允许芷春使用麦克风",
            )
            return

        self.speech_router = speech_worker
        self.microphone = microphone
        self.controller.speech_router = speech_worker
        self.window.voice_button.setChecked(True)
        self.controller.set_voice_enabled(True)
        self.window.set_status("等待“芷春”")

    def _microphone_error(self, message):
        del message
        self.speech_router.pause()
        self.controller.session.set_voice_enabled(False)
        self.window.voice_button.setChecked(False)
        self.window.set_status("麦克风不可用")
        self.window.add_message("system", "麦克风连接已中断，请重新打开应用")

    def quit(self):
        if self.microphone is not None:
            self.microphone.stop()
        self.tray.hide()
        self.app.quit()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("芷春")
    app.setWindowIcon(QIcon(str(ICON_PATH)))
    app.setQuitOnLastWindowClosed(False)
    runtime = DesktopRuntime(app)
    app._desktop_runtime = runtime
    return app.exec()
