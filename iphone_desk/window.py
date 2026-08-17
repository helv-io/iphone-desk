"""PySide6 window: first-run checklist, live screen, tap and drag."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer, QUrl
from PySide6.QtGui import QCloseEvent, QIcon, QImage, QKeyEvent, QMouseEvent, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from iphone_desk import __version__
from iphone_desk.assets import app_icon_path
from iphone_desk.checklist import format_step_state
from iphone_desk.keyboard import hid_usage_for_qt_key
from iphone_desk.coords import Size, widget_to_hid
from iphone_desk.device import ConnectedDevice
from iphone_desk.errors import humanize_device_error
from iphone_desk.worker import DeviceWorker

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView

    HAS_WEBENGINE = True
except Exception:
    QWebEngineView = None  # type: ignore[misc, assignment]
    HAS_WEBENGINE = False


STYLE = """
QMainWindow, QWidget#root, QWidget#page {
    background: #12141a;
    color: #e8eaf0;
    font-size: 13px;
}
QLabel#title {
    font-size: 22px;
    font-weight: 600;
    color: #f4f6fb;
}
QLabel#subtitle, QLabel#hint {
    color: #a8b0c2;
}
QTextEdit {
    background: #1b1f2a;
    color: #d7dce8;
    border: 1px solid #2c3344;
    border-radius: 8px;
    padding: 8px;
}
QPushButton {
    background: #3b6df0;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 14px;
    font-weight: 600;
}
QPushButton:hover { background: #4b7cff; }
QPushButton:disabled { background: #3a3f4d; color: #8b93a7; }
QPushButton#secondary {
    background: #2a3142;
    color: #e8eaf0;
}
QPushButton#hw {
    background: #2a3142;
    color: #e8eaf0;
    border: none;
    border-radius: 8px;
    font-weight: 600;
    padding: 0;
}
QPushButton#hw:hover { background: #3a4256; }
QPushButton#hw:pressed { background: #1a1f2a; }
QPushButton#home {
    background: #2a3142;
    border: none;
    border-radius: 14px;
    min-height: 28px;
    max-height: 28px;
    min-width: 128px;
}
QPushButton#home:hover { background: #3a4256; }
QStatusBar {
    background: #0e1016;
    color: #a8b0c2;
}
QLabel#screen {
    background: #0a0c10;
    border: 1px solid #2c3344;
    border-radius: 10px;
}
QFrame#stepok { color: #7ee2a8; }
"""


class ScreenView(QLabel):
    """Letterboxed screenshot surface that turns mouse events into HID points."""

    def __init__(self, worker: DeviceWorker, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("screen")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(280, 500)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self._worker = worker
        self._display = Size(390, 844)
        self._press: Optional[QPoint] = None
        self._press_hid: Optional[tuple[int, int]] = None
        self._last_hid: Optional[tuple[int, int]] = None
        self._pixmap: Optional[QPixmap] = None
        self._gesture = False

    def set_display(self, size: Size) -> None:
        self._display = size

    def show_png(self, data: bytes) -> None:
        image = QImage.fromData(data)
        if image.isNull():
            return
        self._pixmap = QPixmap.fromImage(image)
        self._refresh()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._refresh()

    def _refresh(self) -> None:
        if self._pixmap is None:
            return
        scaled = self._pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        self.setPixmap(scaled)

    def _hid_at(self, pos: QPoint) -> Optional[tuple[int, int]]:
        return widget_to_hid(
            pos.x(),
            pos.y(),
            self.width(),
            self.height(),
            self._display.width,
            self._display.height,
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        hid = self._hid_at(event.position().toPoint())
        if hid is None:
            return
        self._press = event.position().toPoint()
        self._press_hid = hid
        self._last_hid = hid
        self._gesture = True
        self.grabMouse()
        self._worker.touch_down(hid[0], hid[1])

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        hid = self._hid_at(event.position().toPoint())
        if hid is not None:
            self._last_hid = hid
        if not self._gesture:
            return
        point = hid or self._last_hid
        if point is None:
            return
        self._worker.touch_move(point[0], point[1])

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or not self._gesture:
            return
        end = self._hid_at(event.position().toPoint()) or self._last_hid or self._press_hid
        self.cancel_gesture(send_release=False)
        if end is not None:
            self._worker.touch_up(end[0], end[1])

    def cancel_gesture(self, *, send_release: bool = True) -> None:
        if not self._gesture:
            return
        hid = self._last_hid or self._press_hid
        self._gesture = False
        self._press = None
        self._press_hid = None
        if self.mouseGrabber() is self:
            self.releaseMouse()
        if send_release and hid is not None:
            self._worker.touch_up(hid[0], hid[1])

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        if event.isAutoRepeat():
            return
        usage = hid_usage_for_qt_key(int(event.key()))
        if usage is None:
            event.ignore()
            return
        self._worker.key_down(usage)
        event.accept()

    def keyReleaseEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        if event.isAutoRepeat():
            return
        usage = hid_usage_for_qt_key(int(event.key()))
        if usage is None:
            event.ignore()
            return
        self._worker.key_up(usage)
        event.accept()

    def wheelEvent(self, event: QWheelEvent) -> None:
        hid = self._hid_at(event.position().toPoint()) or self._last_hid
        if hid is None:
            return
        from iphone_desk.coords import scroll_wheel_to_drag

        x1, y1, x2, y2 = scroll_wheel_to_drag(hid[0], hid[1], int(event.angleDelta().y()))
        if (x1, y1) != (x2, y2):
            self._worker.drag(x1, y1, x2, y2)


class DeskWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"iPhone Desk {__version__}")
        icon = app_icon_path()
        if icon is not None:
            self.setWindowIcon(QIcon(str(icon)))
        self.resize(480, 860)
        self.setMinimumSize(360, 640)
        self.setStyleSheet(STYLE)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.worker = DeviceWorker()
        self.worker.status.connect(self._on_status)
        self.worker.checklist.connect(self._on_checklist)
        self.worker.connected.connect(self._on_connected)
        self.worker.frame.connect(self._on_frame)
        self.worker.hevc_ready.connect(self._on_hevc)
        self.worker.failed.connect(self._on_failed)
        self.worker.disconnected.connect(self._on_disconnected)
        self.worker.start()

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_setup_page())
        self._stack.addWidget(self._build_screen_page())
        self.setCentralWidget(self._stack)

        bar = QStatusBar()
        self.setStatusBar(bar)
        self._set_status("Ready")

        QTimer.singleShot(200, self.worker.refresh_checklist)

    def _build_setup_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("iPhone Desk")
        title.setObjectName("title")

        self._steps = QTextEdit()
        self._steps.setReadOnly(True)
        self._steps.setMinimumHeight(220)
        self._render_steps(None)

        buttons = QHBoxLayout()
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setObjectName("secondary")
        self._connect_btn = QPushButton("Connect")
        self._refresh_btn.clicked.connect(self.worker.refresh_checklist)
        self._connect_btn.clicked.connect(self._connect)
        buttons.addWidget(self._refresh_btn)
        buttons.addWidget(self._connect_btn)

        layout.addWidget(title)
        layout.addWidget(self._steps, 1)
        layout.addLayout(buttons)
        return page

    def _hw_button(self, text: str, action: str, *, object_name: str = "hw", width: int, height: int) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName(object_name)
        button.setFixedSize(width, height)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.clicked.connect(lambda: self.worker.button(action))
        return button

    def _build_screen_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        top = QHBoxLayout()
        self._info = QLabel("Not connected")
        self._info.setObjectName("subtitle")
        self._info.setWordWrap(True)
        self._disconnect_btn = QPushButton("Disconnect")
        self._disconnect_btn.setObjectName("secondary")
        self._disconnect_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._disconnect_btn.clicked.connect(self.worker.disconnect_device)
        top.addWidget(self._info, 1)
        top.addWidget(self._disconnect_btn)

        self._screen = ScreenView(self.worker)
        self._screen.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._web: Optional[QWidget] = None
        if HAS_WEBENGINE:
            self._web = QWebEngineView()
            self._web.setMinimumSize(280, 500)
            self._web.hide()
        stage = QWidget()
        stage_layout = QVBoxLayout(stage)
        stage_layout.setContentsMargins(0, 0, 0, 0)
        stage_layout.setSpacing(0)
        stage_layout.addWidget(self._screen, 1)
        if self._web is not None:
            stage_layout.addWidget(self._web, 1)

        self._vol_up_btn = self._hw_button("+", "volume-up", width=28, height=40)
        self._vol_down_btn = self._hw_button("-", "volume-down", width=28, height=40)
        left = QVBoxLayout()
        left.setSpacing(6)
        left.addStretch(2)
        left.addWidget(self._vol_up_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        left.addWidget(self._vol_down_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        left.addStretch(5)

        self._power_btn = self._hw_button("\u23fb", "lock", width=28, height=52)
        right = QVBoxLayout()
        right.addStretch(2)
        right.addWidget(self._power_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        right.addStretch(5)

        mid = QHBoxLayout()
        mid.setSpacing(6)
        mid.addLayout(left)
        mid.addWidget(stage, 1)
        mid.addLayout(right)

        self._home_btn = self._hw_button("", "home", object_name="home", width=140, height=28)

        layout.addLayout(top)
        layout.addLayout(mid, 1)
        layout.addWidget(self._home_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        return page

    def _render_steps(self, status) -> None:
        if status is None:
            rows = format_step_state(False, False, None, None)
        else:
            rows = format_step_state(
                status.apple_mobile_device,
                status.usb_present,
                status.paired,
                status.developer_mode,
            )
        marks = {"ok": "[ok]", "wait": "[..]", "fail": "[!]"}
        lines = []
        for label, state in rows:
            lines.append(f"{marks.get(state, '[..]')} {label}")
        if status is not None and status.device_labels:
            lines.append("")
            lines.append("USB devices: " + ", ".join(status.device_labels))
        if status is not None and status.detail:
            lines.append("")
            lines.append(status.detail)
        self._steps.setPlainText("\n".join(lines))

    def _connect(self) -> None:
        self._connect_btn.setEnabled(False)
        self._set_status("Connecting...")
        self.worker.connect_device(HAS_WEBENGINE)

    def _on_checklist(self, status) -> None:
        self._render_steps(status)

    def _on_connected(self, summary: ConnectedDevice) -> None:
        self._connect_btn.setEnabled(True)
        self._screen.set_display(summary.display)
        touch = "touch on" if summary.touch_available else "taps blocked"
        self._info.setText(
            f"{summary.name}  iOS {summary.product_version}  "
            f"{summary.display.width}x{summary.display.height}  mode={summary.mode}  {touch}"
        )
        self._stack.setCurrentIndex(1)
        if summary.mode != "hevc":
            self._show_screenshot_surface()
        self._screen.setFocus(Qt.FocusReason.OtherFocusReason)

    def _on_hevc(self, url: str) -> None:
        if self._web is None:
            return
        self._screen.hide()
        self._web.show()
        self._web.load(QUrl(url))

    def _show_screenshot_surface(self) -> None:
        if self._web is not None:
            self._web.hide()
        self._screen.show()

    def _on_frame(self, png: bytes) -> None:
        if self._screen.isVisible():
            self._screen.show_png(png)

    def _on_status(self, message: str) -> None:
        self._set_status(message)

    def _on_failed(self, message: str) -> None:
        self._connect_btn.setEnabled(True)
        shown = humanize_device_error(Exception(message)) if message else message
        self._set_status(shown)
        QMessageBox.warning(self, "iPhone Desk", shown)

    def _forward_key(self, event: QKeyEvent, down: bool) -> bool:
        if self._stack.currentIndex() != 1 or event.isAutoRepeat():
            return False
        usage = hid_usage_for_qt_key(int(event.key()))
        if usage is None:
            return False
        if down:
            self.worker.key_down(usage)
        else:
            self.worker.key_up(usage)
        event.accept()
        return True

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        if not self._forward_key(event, True):
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        if not self._forward_key(event, False):
            super().keyReleaseEvent(event)

    def changeEvent(self, event: QEvent) -> None:  # type: ignore[override]
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange and not self.isActiveWindow():
            self._screen.cancel_gesture()
            self.worker.keys_clear()

    def _on_disconnected(self) -> None:
        self._screen.cancel_gesture()
        self._connect_btn.setEnabled(True)
        self._stack.setCurrentIndex(0)
        self.worker.refresh_checklist()

    def _set_status(self, message: str) -> None:
        self.statusBar().showMessage(message)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._screen.cancel_gesture()
        self.worker.stop()
        super().closeEvent(event)
