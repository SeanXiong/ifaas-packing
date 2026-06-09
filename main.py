from __future__ import annotations

import logging
from pathlib import Path
import sys

from PyQt6.QtWidgets import QApplication, QDialog


def setup_logging() -> None:
    log_dir = Path(__file__).resolve().parent / "logs"
    log_dir.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_dir / "ifaas-packing.log", encoding="utf-8"),
        ],
    )


def main() -> int:
    setup_logging()
    app = QApplication(sys.argv)
    from ifaas_packing.main_window import LoginDialog, MainWindow

    login_dialog = LoginDialog()
    if login_dialog.exec() != QDialog.DialogCode.Accepted or not login_dialog.api_client:
        return 0

    window = MainWindow(login_dialog.api_client)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
