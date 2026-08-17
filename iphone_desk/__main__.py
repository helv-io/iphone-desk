"""Launch the iPhone Desk window.

    python -m iphone_desk
"""

from __future__ import annotations

import logging
import sys


def main(argv: list[str] | None = None) -> int:
    _ = argv
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    from PySide6.QtWidgets import QApplication

    from iphone_desk.window import DeskWindow

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("iPhone Desk")
    app.setOrganizationName("helv-io")
    window = DeskWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
