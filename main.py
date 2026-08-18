# -*- coding: utf-8 -*-
"""
SlideshowMaker - Entry point

Supports two modes:
  GUI mode (default): Launch PyQt5 GUI application
  CLI mode:           Run with --cli, or launch SlideshowMakerCLI.exe

CLI usage:
  python main.py --cli --input <folder> --output <file.mp4> [options]
  SlideshowMakerCLI.exe --input <folder> --output <file.mp4> [options]
  SlideshowMakerCLI.exe --list-presets
  SlideshowMakerCLI.exe --input <folder> --dry-run
  python main.py --help
"""
import sys
import os


def resource_path(relative_path):
    """PyInstaller実行時もソース実行時も正しいパスを返す"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


def is_cli_mode() -> bool:
    """引数またはCLI専用EXE名からCLIモードかどうかを判定する。"""
    if '--cli' in sys.argv:
        return True

    # PyInstallerで生成した SlideshowMakerCLI.exe は、--cli を付けずに
    # そのままコマンドライン専用アプリとして起動できるようにする。
    executable = sys.executable if getattr(sys, 'frozen', False) else sys.argv[0]
    return os.path.basename(executable).lower() == 'slideshowmakercli.exe'


def main():
    if is_cli_mode():
        # ---- CLI mode ----
        from cli import build_parser, run_cli
        parser = build_parser()
        args = parser.parse_args()
        exit_code = run_cli(args)
        sys.exit(exit_code)
    else:
        # ---- GUI mode ----
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import Qt
        from main_window import MainWindow

        # High DPI対応
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

        app = QApplication(sys.argv)
        app.setApplicationName("SlideshowMaker")
        app.setApplicationVersion("1.0.0")

        window = MainWindow()
        window.show()
        sys.exit(app.exec_())


if __name__ == "__main__":
    main()
