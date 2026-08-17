"""PySide6 window: first-run checklist, live screen, tap and drag."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPoint, Qt, QTimer, QUrl
from PySide6.QtGui import QCloseEvent, QImage, QMouseEvent, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from iphone_desk import __version__
from iphone_desk.checklist import WHAT_THIS_IS, format_step_state
from iphone_desk.coords import Size, widget_to_hid
from iphone_desk.device import ConnectedDevice
from iphone_desk.hid_actions import drag_is_tap
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
QCheckBox { color: #d7dce8; spacing: 8px; }
QToolBar {
    background: #1b1f2a;
    border: none;
    spacing: 8px;
    padding: 6px;
}
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
            Qt.TransformationMode.SmoothTransformation,
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

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        hid = self._hid_at(event.position().toPoint())
        if hid is not None:
            self._last_hid = hid

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._press_hid is None:
            return
        end = self._hid_at(event.position().toPoint()) or self._last_hid or self._press_hid
        start = self._press_hid
        self._press = None
        self._press_hid = None
        if drag_is_tap(start[0], start[1], end[0], end[1]):
            self._worker.tap(start[0], start[1])
        else:
            self._worker.drag(start[0], start[1], end[0], end[1])

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
        self.resize(480, 860)
        self.setMinimumSize(360, 640)
        self.setStyleSheet(STYLE)

        self.worker = DeviceWorker()
        self.worker.status.connect(self._on_status)
        self.worker.checklist.connect(self._on_checklist)
        self.worker.connected.connect(self._on_connected)
        self.worker.frame.connect(self._on_frame)
        self.worker.hevc_ready.connect(self._on_hevc)
        self.worker.failed.connect(self._on_failed)
        self.worker.disconnected.connect(self._on_disconnected)
        self.worker.start()
        self._reconnect_screenshot = False

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_setup_page())
        self._stack.addWidget(self._build_screen_page())
        self.setCentralWidget(self._stack)

        self._toolbar = QToolBar()
        self._toolbar.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._toolbar)
        self._home_btn = QPushButton("Home")
        self._lock_btn = QPushButton("Lock")
        self._vol_up_btn = QPushButton("Vol +")
        self._vol_down_btn = QPushButton("Vol -")
        self._fallback_btn = QPushButton("Screenshot fallback")
        self._disconnect_btn = QPushButton("Disconnect")
        for button in (
            self._home_btn,
            self._lock_btn,
            self._vol_up_btn,
            self._vol_down_btn,
            self._fallback_btn,
            self._disconnect_btn,
        ):
            button.setObjectName("secondary")
            self._toolbar.addWidget(button)
        self._home_btn.clicked.connect(lambda: self.worker.button("home"))
        self._lock_btn.clicked.connect(lambda: self.worker.button("lock"))
        self._vol_up_btn.clicked.connect(lambda: self.worker.button("volume-up"))
        self._vol_down_btn.clicked.connect(lambda: self.worker.button("volume-down"))
        self._fallback_btn.clicked.connect(self._use_screenshot_fallback)
        self._disconnect_btn.clicked.connect(self.worker.disconnect_device)
        self._toolbar.setVisible(False)

        bar = QStatusBar()
        self.setStatusBar(bar)
        self._set_status("Ready. Work through the checklist, then Connect.")

        QTimer.singleShot(200, self.worker.refresh_checklist)

    def _build_setup_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("iPhone Desk")
        title.setObjectName("title")
        subtitle = QLabel("See and tap your own iPhone from this Windows PC.")
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        blurb = QLabel(WHAT_THIS_IS)
        blurb.setObjectName("hint")
        blurb.setWordWrap(True)

        self._steps = QTextEdit()
        self._steps.setReadOnly(True)
        self._steps.setMinimumHeight(220)
        self._render_steps(None)

        self._hevc_box = QCheckBox("Try live HEVC (serve-web) first. Fall back to screenshots if the picture is black.")
        self._hevc_box.setChecked(HAS_WEBENGINE)
        if not HAS_WEBENGINE:
            self._hevc_box.setEnabled(False)
            self._hevc_box.setText(
                "Live HEVC needs PySide6-QtWebEngine. Screenshot loop will be used (usable FPS, documented fallback)."
            )

        buttons = QHBoxLayout()
        self._refresh_btn = QPushButton("Refresh status")
        self._refresh_btn.setObjectName("secondary")
        self._connect_btn = QPushButton("Connect")
        self._refresh_btn.clicked.connect(self.worker.refresh_checklist)
        self._connect_btn.clicked.connect(self._connect)
        buttons.addWidget(self._refresh_btn)
        buttons.addWidget(self._connect_btn)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(blurb)
        layout.addWidget(self._steps, 1)
        layout.addWidget(self._hevc_box)
        layout.addLayout(buttons)
        return page

    def _build_screen_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        self._info = QLabel("Not connected")
        self._info.setObjectName("subtitle")
        self._info.setWordWrap(True)
        self._screen = ScreenView(self.worker)
        self._web: Optional[QWidget] = None
        if HAS_WEBENGINE:
            self._web = QWebEngineView()
            self._web.setMinimumSize(280, 500)
            self._web.hide()
        layout.addWidget(self._info)
        layout.addWidget(self._screen, 1)
        if self._web is not None:
            layout.addWidget(self._web, 1)
        hint = QLabel("Click to tap. Click-drag to drag. Scroll wheel sends a short swipe.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
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
        lines = ["First-run checklist", ""]
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
        self.worker.connect_device(self._hevc_box.isChecked())

    def _use_screenshot_fallback(self) -> None:
        self._set_status("Reconnecting with the screenshot loop...")
        self._reconnect_screenshot = True
        self.worker.disconnect_device()

    def _on_checklist(self, status) -> None:
        self._render_steps(status)

    def _on_connected(self, summary: ConnectedDevice) -> None:
        self._connect_btn.setEnabled(True)
        self._screen.set_display(summary.display)
        self._info.setText(
            f"{summary.name}  iOS {summary.product_version}  "
            f"{summary.display.width}x{summary.display.height}  mode={summary.mode}"
        )
        self._toolbar.setVisible(True)
        self._fallback_btn.setVisible(summary.mode == "hevc")
        self._stack.setCurrentIndex(1)
        if summary.mode != "hevc":
            self._show_screenshot_surface()

    def _on_hevc(self, url: str) -> None:
        if self._web is None:
            self._set_status("HEVC URL is ready but Qt WebEngine is missing. Use screenshot fallback.")
            return
        self._screen.hide()
        self._web.show()
        self._web.load(QUrl(url))
        self._set_status(f"Live HEVC at {url}. If the picture stays black, use Screenshot fallback.")

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
        self._set_status(message)
        QMessageBox.warning(self, "iPhone Desk", message)

    def _on_disconnected(self) -> None:
        self._connect_btn.setEnabled(True)
        self._toolbar.setVisible(False)
        self._stack.setCurrentIndex(0)
        if self._reconnect_screenshot:
            self._reconnect_screenshot = False
            self.worker.connect_device(False)
            return
        self.worker.refresh_checklist()

    def _set_status(self, message: str) -> None:
        self.statusBar().showMessage(message)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.worker.stop()
        super().closeEvent(event)
