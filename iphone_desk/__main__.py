"""Launch the iPhone Desk window.

    python -m iphone_desk
"""

from __future__ import annotations

import logging
import sys
import traceback
from pathlib import Path


def _crash_log_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).with_name("iPhoneDesk.log")
    return Path.cwd() / "iPhoneDesk.log"


def main(argv: list[str] | None = None) -> int:
    _ = argv
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if getattr(sys, "frozen", False):
        try:
            import faulthandler

            log = _crash_log_path().open("a", encoding="utf-8")
            faulthandler.enable(file=log, all_threads=True)
        except Exception:
            pass
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from iphone_desk.assets import app_icon_path
    from iphone_desk.window import DeskWindow

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("iPhone Desk")
    app.setOrganizationName("helv-io")
    icon = app_icon_path()
    if icon is not None:
        app.setWindowIcon(QIcon(str(icon)))
    window = DeskWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        text = traceback.format_exc()
        try:
            _crash_log_path().write_text(text, encoding="utf-8")
        except Exception:
            pass
        print(text, file=sys.stderr)
        raise
