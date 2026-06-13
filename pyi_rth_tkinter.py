"""PyInstaller runtime hook: Tcl/Tk paths for frozen macOS .app bundles."""

import os
import sys


def _resource_base() -> str:
    if hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return os.path.dirname(sys.executable)


if getattr(sys, "frozen", False):
    base = _resource_base()
    candidates = [
        (os.path.join(base, "lib", "tcl8.6"), os.path.join(base, "lib", "tk8.6")),
        (os.path.join(base, "tcl8.6"), os.path.join(base, "tk8.6")),
        (os.path.join(base, "_internal", "tcl8.6"), os.path.join(base, "_internal", "tk8.6")),
        (os.path.join(base, "_internal", "lib", "tcl8.6"), os.path.join(base, "_internal", "lib", "tk8.6")),
    ]
    for tcl_dir, tk_dir in candidates:
        if os.path.isdir(tcl_dir):
            os.environ["TCL_LIBRARY"] = tcl_dir
        if os.path.isdir(tk_dir):
            os.environ["TK_LIBRARY"] = tk_dir
        if os.path.isdir(tcl_dir) and os.path.isdir(tk_dir):
            break
