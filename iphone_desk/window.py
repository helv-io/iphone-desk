"""PySide6 window: first-run checklist, live screen, tap and drag."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QIcon,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRegion,
    QWheelEvent,
)
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
from iphone_desk.keyboard import hid_usages_for_qt_key
from iphone_desk.coords import Size, fitted_image_rect, phone_corner_radius, widget_to_hid
from iphone_desk.device import ConnectedDevice
from iphone_desk.errors import humanize_device_error
from iphone_desk.worker import DeviceWorker


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
QWidget#phoneStage {
    background: transparent;
}
QLabel#screen {
    background: #0a0c10;
    border: none;
}
QFrame#stepok { color: #7ee2a8; }
"""


class ScreenView(QLabel):
    """Phone-shaped screenshot surface that turns mouse events into HID points."""

    def __init__(self, worker: DeviceWorker, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("screen")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setMouseTracking(True)
        self._worker = worker
        self._on_key = None
        self._display = Size(390, 844)
        self._press: Optional[QPoint] = None
        self._press_hid: Optional[tuple[int, int]] = None
        self._last_hid: Optional[tuple[int, int]] = None
        self._pixmap: Optional[QPixmap] = None
        self._gesture = False

    def set_key_handler(self, handler) -> None:
        self._on_key = handler

    def set_display(self, size: Size) -> None:
        self._display = size
        self.update()

    def show_png(self, data: bytes) -> None:
        image = QImage.fromData(data)
        if image.isNull():
            return
        self._pixmap = QPixmap.fromImage(image)
        self.update()

    def show_bgra(self, width: int, height: int, data: bytes) -> None:
        if width <= 0 or height <= 0:
            return
        expected = width * height * 4
        if len(data) < expected:
            return
        image = QImage(data, width, height, width * 4, QImage.Format.Format_ARGB32)
        if image.isNull():
            return
        self._pixmap = QPixmap.fromImage(image.copy())
        self.update()

    def _radius(self) -> float:
        return phone_corner_radius(float(self.width()), float(self.height()))

    def _screen_path(self) -> QPainterPath:
        path = QPainterPath()
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = self._radius()
        path.addRoundedRect(rect, radius, radius)
        return path

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        path = self._screen_path()
        painter.setClipPath(path)
        painter.fillRect(self.rect(), QColor("#0a0c10"))
        if self._pixmap is not None and not self._pixmap.isNull():
            scaled = self._pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        painter.setClipping(False)
        painter.setPen(QPen(QColor("#2c3344"), 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

    def _hid_at(self, pos: QPoint) -> Optional[tuple[int, int]]:
        if not self._screen_path().contains(QPointF(pos)):
            return None
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
        if self._on_key is not None and self._on_key(int(event.key()), True):
            event.accept()
            return
        event.ignore()

    def keyReleaseEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        if event.isAutoRepeat():
            return
        if self._on_key is not None and self._on_key(int(event.key()), False):
            event.accept()
            return
        event.ignore()

    def wheelEvent(self, event: QWheelEvent) -> None:
        hid = self._hid_at(event.position().toPoint()) or self._last_hid
        if hid is None:
            return
        from iphone_desk.coords import scroll_wheel_to_drag

        x1, y1, x2, y2 = scroll_wheel_to_drag(hid[0], hid[1], int(event.angleDelta().y()))
        if (x1, y1) != (x2, y2):
            self._worker.drag(x1, y1, x2, y2)


class PhoneStage(QWidget):
    """Keeps the child phone screen at the device aspect ratio."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("phoneStage")
        self._aspect_w = 1290
        self._aspect_h = 2796
        self.screen = None

    def set_display(self, size: Size) -> None:
        if size.width > 0 and size.height > 0:
            self._aspect_w = size.width
            self._aspect_h = size.height
        if self.screen is not None:
            self.screen.set_display(size)
        self._place()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._place()

    def _place(self) -> None:
        dest = fitted_image_rect(
            float(self.width()),
            float(self.height()),
            float(self._aspect_w),
            float(self._aspect_h),
        )
        geo = QRect(int(dest.x), int(dest.y), max(1, int(dest.width)), max(1, int(dest.height)))
        radius = phone_corner_radius(float(geo.width()), float(geo.height()))
        if self.screen is not None:
            self.screen.setGeometry(geo)
            path = QPainterPath()
            path.addRoundedRect(QRectF(0, 0, geo.width(), geo.height()), radius, radius)
            self.screen.setMask(QRegion(path.toFillPolygon().toPolygon()))


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
        self._qt_keys: set[int] = set()
        self._home_siri_fired = False

        self.worker = DeviceWorker()
        self.worker.status.connect(self._on_status)
        self.worker.checklist.connect(self._on_checklist)
        self.worker.connected.connect(self._on_connected)
        self.worker.frame.connect(self._on_frame)
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

        self._scan = QTimer(self)
        self._scan.setInterval(1500)
        self._scan.timeout.connect(self.worker.refresh_checklist)
        self._scan.start()
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

        self._stage = PhoneStage()
        self._screen = ScreenView(self.worker, self._stage)
        self._screen.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._screen.set_key_handler(self._note_key)
        self._stage.screen = self._screen
        self._live_timer = QTimer(self)
        self._live_timer.setInterval(16)
        self._live_timer.timeout.connect(self._paint_live)

        self._vol_up_btn = self._hw_button("+", "volume-up", width=28, height=80)
        self._vol_down_btn = self._hw_button("-", "volume-down", width=28, height=80)
        left = QVBoxLayout()
        left.setSpacing(6)
        left.addStretch(2)
        left.addWidget(self._vol_up_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        left.addWidget(self._vol_down_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        left.addStretch(5)

        self._power_btn = self._hw_button("\u23fb", "lock", width=28, height=104)
        right = QVBoxLayout()
        right.addStretch(2)
        right.addWidget(self._power_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        right.addStretch(5)

        mid = QHBoxLayout()
        mid.setSpacing(6)
        mid.addLayout(left)
        mid.addWidget(self._stage, 1)
        mid.addLayout(right)

        self._home_btn = QPushButton("")
        self._home_btn.setObjectName("home")
        self._home_btn.setFixedSize(140, 28)
        self._home_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._home_hold = QTimer(self)
        self._home_hold.setSingleShot(True)
        self._home_hold.setInterval(550)
        self._home_hold.timeout.connect(self._home_long_press)
        self._home_btn.pressed.connect(self._home_pressed)
        self._home_btn.released.connect(self._home_released)

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
        self._scan.stop()
        self.worker.connect_device(True)

    def _on_checklist(self, status) -> None:
        self._render_steps(status)

    def _on_connected(self, summary: ConnectedDevice) -> None:
        self._connect_btn.setEnabled(True)
        self._scan.stop()
        self._stage.set_display(summary.display)
        extra = "" if summary.touch_available else "  taps blocked"
        self._info.setText(
            f"{summary.name}  iOS {summary.product_version}  "
            f"{summary.display.width}x{summary.display.height}  {summary.mode}{extra}"
        )
        self._stack.setCurrentIndex(1)
        self._screen.show()
        if summary.mode == "hevc":
            self._live_timer.start()
        else:
            self._live_timer.stop()
        self._screen.setFocus(Qt.FocusReason.OtherFocusReason)

    def _paint_live(self) -> None:
        item = self.worker.take_live()
        if item is None:
            return
        self._screen.show_bgra(item[0], item[1], item[2])

    def _on_frame(self, png: bytes) -> None:
        if self._screen.isVisible():
            self._screen.show_png(png)

    def _on_status(self, message: str) -> None:
        self._set_status(message)

    def _on_failed(self, message: str) -> None:
        self._connect_btn.setEnabled(True)
        if self._stack.currentIndex() == 0:
            self._scan.start()
        shown = humanize_device_error(Exception(message)) if message else message
        self._set_status(shown)
        QMessageBox.warning(self, "iPhone Desk", shown)

    def _note_key(self, key: int, down: bool) -> bool:
        usages = hid_usages_for_qt_key(int(key))
        if not usages:
            return False
        if down:
            self._qt_keys.add(int(key))
        else:
            self._qt_keys.discard(int(key))
        held: set[int] = set()
        for item in self._qt_keys:
            held.update(hid_usages_for_qt_key(item))
        self.worker.keys_replace(sorted(held))
        return True

    def _home_pressed(self) -> None:
        self._home_siri_fired = False
        self._home_hold.start()

    def _home_released(self) -> None:
        self._home_hold.stop()
        if not self._home_siri_fired:
            self.worker.button("home")

    def _home_long_press(self) -> None:
        self._home_siri_fired = True
        self.worker.button("siri")

    def _forward_key(self, event: QKeyEvent, down: bool) -> bool:
        if self._stack.currentIndex() != 1 or event.isAutoRepeat():
            return False
        if not self._note_key(int(event.key()), down):
            return False
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
            self._qt_keys.clear()
            self.worker.keys_clear()

    def _on_disconnected(self) -> None:
        self._live_timer.stop()
        self._screen.cancel_gesture()
        self._qt_keys.clear()
        self._connect_btn.setEnabled(True)
        self._stack.setCurrentIndex(0)
        self._scan.start()
        self.worker.refresh_checklist()

    def _set_status(self, message: str) -> None:
        self.statusBar().showMessage(message)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._live_timer.stop()
        self._screen.cancel_gesture()
        self.worker.stop()
        super().closeEvent(event)
