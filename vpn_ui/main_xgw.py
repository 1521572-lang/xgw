"""Рабочее окно из checkout: python3 vpn_ui/main_xgw.py [--theme light]."""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Новое окно XGW с настоящим API панели")
    parser.add_argument("--theme", choices=("light", "dark"), default="dark")
    parser.add_argument("--native-titlebar", action="store_true")
    args = parser.parse_args(argv)
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        parser.error("окно запускается от пользователя графической сессии, не от root")
    root = Path(__file__).resolve().parent.parent
    sys.path[:0] = [str(root / "src"), str(root)]
    # Существующие функциональные страницы XGW и ApiClient написаны на PyQt6.
    # Смешивать PySide6 и PyQt6 в одном QApplication нельзя.
    os.environ["XGW_UI_QT"] = "PyQt6"
    from vpn_ui.qt import QtWidgets
    from vpn_ui.views.main_window import prepare_application
    from vpn_ui.xgw.backend import GuardedApiClient, XgwBridge
    from vpn_ui.xgw.window import XgwWindow
    from xgw.gui import login, model
    from xgw.gui.app import SingleInstance, _watch_exit, code_stamp, server_name

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([sys.argv[0]])
    app.setApplicationName("XGW")
    prepare_application(app)
    digest = hashlib.sha256(code_stamp().encode())
    for path in sorted((root / "vpn_ui").rglob("*.py")):
        digest.update(path.read_bytes())
    single = SingleInstance(server_name() + "-proton", digest.hexdigest()[:16])
    if single.notify_running():
        return 0
    session_path = model.session_file()
    api = GuardedApiClient(model.load_session(session_path))
    flow = login.LoginFlow(api.exchange)
    bridge = XgwBridge(api)
    window = XgwWindow(bridge, flow, session_path, use_custom_titlebar=not args.native_titlebar,
                       theme_name=args.theme)
    bridge.settings.theme = args.theme
    _watch_exit(window, app)
    single.listen(window.bring_to_front, window.close)
    window.show()
    api.start()
    return int(app.exec())


if __name__ == "__main__":
    raise SystemExit(main())
