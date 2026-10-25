"""PyInstaller entry point: imports the app as a package so its relative imports resolve."""

import multiprocessing

from crane_statics.qml_app.app import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
