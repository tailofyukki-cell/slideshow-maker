# -*- coding: utf-8 -*-
"""
Main window (PyQt5 GUI)
"""
import os
import sys
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QProgressBar, QTextEdit, QGroupBox, QSplitter,
    QMessageBox, QSizePolicy, QFrame,
    QComboBox, QCheckBox, QDoubleSpinBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt5.QtGui import QFont, QColor, QPalette, QIcon

from file_scanner import scan_folder, ScanResult, FilePair, AUDIO_EXTENSIONS, IMAGE_PRIORITY, VIDEO_PRIORITY
from telop_parser import find_telop_file, load_telop_file
from timing_parser import find_timing_file, get_timing_summary
from video_generator import (
    generate_video, GenerationConfig, OUTPUT_FILENAME,
    RESOLUTION_PRESETS, DEFAULT_PRESET, VIZUALIZER_STYLES, VIZUALIZER_COLOR_MODES,
    find_folder_bgm,
)


# ========== ワーカースレッド ==========

class VideoGeneratorWorker(QThread):
    """動画生成をバックグラウンドで実行するワーカースレッド"""
    progress = pyqtSignal(int, str)   # (percent, message)
    finished = pyqtSignal(str)         # output_path
    error = pyqtSignal(str)            # error_message
    cancelled = pyqtSignal()

    def __init__(self, config: GenerationConfig):
        super().__init__()
        self.config = config
        self._cancel_requested = False

    def request_cancel(self):
        self._cancel_requested = True

    def run(self):
        try:
            result_path = generate_video(
                config=self.config,
                progress_callback=lambda p, m: self.progress.emit(p, m),
                cancel_check=lambda: self._cancel_requested,
            )
            if self._cancel_requested:
                self.cancelled.emit()
            else:
                self.finished.emit(result_path)
        except InterruptedError:
            self.cancelled.emit()
        except Exception as e:
            self.error.emit(str(e))


# ========== メインウィンドウ ==========

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.scan_result: ScanResult = None
        self.worker: VideoGeneratorWorker = None

        self._init_ui()
        self._apply_style()

    def _init_ui(self):
        self.setWindowTitle("SlideshowMaker - 音声+画像/動画→MP4動画生成")
        self.setMinimumSize(900, 700)
        self.resize(1100, 780)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        # ---- フォルダ選択 ----
        folder_group = QGroupBox("① 入力フォルダ選択")
        folder_layout = QHBoxLayout(folder_group)

        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("mp3/wav/flac/aac/m4a/ogg/wma + jpg/png/gif/webp/bmp/tiff が入ったフォルダを選択してください...")
        self.folder_edit.setReadOnly(True)
        folder_layout.addWidget(self.folder_edit)

        self.browse_btn = QPushButton("フォルダを選択...")
        self.browse_btn.setFixedWidth(140)
        self.browse_btn.clicked.connect(self._on_browse_folder)
        folder_layout.addWidget(self.browse_btn)

        self.scan_btn = QPushButton("スキャン")
        self.scan_btn.setFixedWidth(80)
        self.scan_btn.clicked.connect(self._on_scan)
        self.scan_btn.setEnabled(False)
        folder_layout.addWidget(self.scan_btn)

        layout.addWidget(folder_group)

        # ---- ペア一覧 ----
        pairs_group = QGroupBox("② ファイルペア一覧")
        pairs_layout = QVBoxLayout(pairs_group)

        self.summary_label = QLabel("フォルダを選択してスキャンしてください。")
        self.summary_label.setStyleSheet("color: #555; font-size: 12px;")
        pairs_layout.addWidget(self.summary_label)

        self.pairs_table = QTableWidget()
        self.pairs_table.setColumnCount(6)
        self.pairs_table.setHorizontalHeaderLabels(["\u30d9\u30fc\u30b9\u540d", "\u97f3\u58f0\u30d5\u30a1\u30a4\u30eb", "\u753b\u50cf\u30d5\u30a1\u30a4\u30eb", "\u30c6\u30ed\u30c3\u30d7", "\u8868\u793a\u6642\u9593", "\u72b6\u614b"])
        self.pairs_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.pairs_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.pairs_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.pairs_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.pairs_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.pairs_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.pairs_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.pairs_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.pairs_table.setAlternatingRowColors(True)
        self.pairs_table.verticalHeader().setVisible(False)
        self.pairs_table.setMinimumHeight(200)
        pairs_layout.addWidget(self.pairs_table)

        layout.addWidget(pairs_group)

        # ---- 出力設定 ----
        output_group = QGroupBox("③ 出力設定")
        output_vbox = QVBoxLayout(output_group)

        # 解像度プリセット行
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("解像度:"))
        self.preset_combo = QComboBox()
        for preset_name in RESOLUTION_PRESETS.keys():
            self.preset_combo.addItem(preset_name)
        self.preset_combo.setCurrentText(DEFAULT_PRESET)
        self.preset_combo.setMinimumWidth(280)
        self.preset_combo.currentTextChanged.connect(self._on_preset_changed)
        preset_row.addWidget(self.preset_combo)
        self.resolution_label = QLabel()
        self._update_resolution_label()
        self.resolution_label.setStyleSheet("color: #555; font-size: 11px;")
        preset_row.addWidget(self.resolution_label)
        preset_row.addStretch()

        # ケン・バーンズ効果チェックボックス
        self.ken_burns_check = QCheckBox("ケン・バーンズ効果（静止画にズーム/パン動作を追加）")
        self.ken_burns_check.setChecked(False)
        self.ken_burns_check.setToolTip(
            "静止画チャプターにゆっくりとしたズームイン/アウト・パン効果を加えます。\n"
            "アニメーションGIFには適用されません。"
        )
        preset_row.addWidget(self.ken_burns_check)
        output_vbox.addLayout(preset_row)

        # ---- ビジュアライザー行 ----
        from PyQt5.QtWidgets import QSpinBox
        viz_row = QHBoxLayout()
        self.viz_check = QCheckBox("オーディオビジュアライザー（透かし）")
        self.viz_check.setChecked(False)
        self.viz_check.setToolTip(
            "音声の波形や周波数をリアルタイムに可視化して動画に透かしとして重ねます。"
        )
        self.viz_check.stateChanged.connect(self._on_viz_check_changed)
        viz_row.addWidget(self.viz_check)
        viz_row.addWidget(QLabel("スタイル:"))
        self.viz_style_combo = QComboBox()
        for key, label in VIZUALIZER_STYLES.items():
            self.viz_style_combo.addItem(label, key)
        self.viz_style_combo.setMinimumWidth(180)
        self.viz_style_combo.setEnabled(False)
        viz_row.addWidget(self.viz_style_combo)
        viz_row.addWidget(QLabel("高さ(px):"))
        self.viz_height_spin = QSpinBox()
        self.viz_height_spin.setRange(40, 400)
        self.viz_height_spin.setValue(80)
        self.viz_height_spin.setSingleStep(10)
        self.viz_height_spin.setEnabled(False)
        viz_row.addWidget(self.viz_height_spin)
        viz_row.addWidget(QLabel("不透明度:"))
        self.viz_opacity_spin = QSpinBox()
        self.viz_opacity_spin.setRange(10, 100)
        self.viz_opacity_spin.setValue(60)
        self.viz_opacity_spin.setSuffix("%")
        self.viz_opacity_spin.setSingleStep(5)
        self.viz_opacity_spin.setEnabled(False)
        viz_row.addWidget(self.viz_opacity_spin)
        viz_row.addWidget(QLabel("色:"))
        self.viz_color_mode_combo = QComboBox()
        for key, label in VIZUALIZER_COLOR_MODES.items():
            self.viz_color_mode_combo.addItem(label, key)
        self.viz_color_mode_combo.setMinimumWidth(100)
        self.viz_color_mode_combo.setEnabled(False)
        self.viz_color_mode_combo.currentIndexChanged.connect(self._on_viz_color_mode_changed)
        viz_row.addWidget(self.viz_color_mode_combo)
        # 単色選択ボタン（単色モード時のみ有効）
        self.viz_color_btn = QPushButton()
        self.viz_color_btn.setFixedSize(28, 28)
        self.viz_color_btn.setToolTip("単色モード時の色を選択")
        self._viz_color_value = "#00ffff"
        self._update_viz_color_btn()
        self.viz_color_btn.setEnabled(False)
        self.viz_color_btn.clicked.connect(self._on_viz_color_btn_clicked)
        viz_row.addWidget(self.viz_color_btn)
        viz_row.addStretch()
        output_vbox.addLayout(viz_row)

        # タイトルオーバーレイ行
        title_row = QHBoxLayout()
        self.title_overlay_check = QCheckBox("ファイル名タイトルを動画に表示する")
        self.title_overlay_check.setChecked(True)
        self.title_overlay_check.setToolTip(
            "各チャプターの先頭にファイル名をタイトルとして表示します。\n"
            "オフにするとタイトルオーバーレイなしで動画を生成します。"
        )
        title_row.addWidget(self.title_overlay_check)
        title_row.addStretch()
        output_vbox.addLayout(title_row)

        # ---- BGM設定行 ----
        bgm_row1 = QHBoxLayout()
        self.bgm_check = QCheckBox("BGMをミックスする")
        self.bgm_check.setChecked(False)
        self.bgm_check.setToolTip(
            "BGMファイルを音声とミックスします。\n"
            "入力フォルダに _bgm.mp3 等を置くか、BGMファイルを指定してください。"
        )
        self.bgm_check.stateChanged.connect(self._on_bgm_check_changed)
        bgm_row1.addWidget(self.bgm_check)
        bgm_row1.addWidget(QLabel("BGMファイル:"))
        self.bgm_edit = QLineEdit()
        self.bgm_edit.setPlaceholderText("ファイルを選択、または入力フォルダに _bgm.mp3 を配置すると自動認識")
        self.bgm_edit.setEnabled(False)
        bgm_row1.addWidget(self.bgm_edit)
        self.bgm_browse_btn = QPushButton("参照...")
        self.bgm_browse_btn.setFixedWidth(80)
        self.bgm_browse_btn.setEnabled(False)
        self.bgm_browse_btn.clicked.connect(self._on_browse_bgm)
        bgm_row1.addWidget(self.bgm_browse_btn)
        output_vbox.addLayout(bgm_row1)

        bgm_row2 = QHBoxLayout()
        bgm_row2.addWidget(QLabel("音声音量:"))
        self.voice_vol_spin = QDoubleSpinBox()
        self.voice_vol_spin.setRange(0.0, 2.0)
        self.voice_vol_spin.setValue(1.0)
        self.voice_vol_spin.setSingleStep(0.1)
        self.voice_vol_spin.setDecimals(1)
        self.voice_vol_spin.setSuffix("x")
        self.voice_vol_spin.setFixedWidth(70)
        self.voice_vol_spin.setEnabled(False)
        self.voice_vol_spin.setToolTip("音声ファイルの音量倍率 (1.0=元のまま, 0.5=半分, 2.0=2倍)")
        bgm_row2.addWidget(self.voice_vol_spin)
        bgm_row2.addWidget(QLabel("BGM音量:"))
        self.bgm_vol_spin = QDoubleSpinBox()
        self.bgm_vol_spin.setRange(0.0, 2.0)
        self.bgm_vol_spin.setValue(0.5)
        self.bgm_vol_spin.setSingleStep(0.1)
        self.bgm_vol_spin.setDecimals(1)
        self.bgm_vol_spin.setSuffix("x")
        self.bgm_vol_spin.setFixedWidth(70)
        self.bgm_vol_spin.setEnabled(False)
        self.bgm_vol_spin.setToolTip("BGMの音量倍率 (0.5=半分が標準)")
        bgm_row2.addWidget(self.bgm_vol_spin)
        bgm_row2.addWidget(QLabel("開始オフセット:"))
        self.bgm_offset_spin = QDoubleSpinBox()
        self.bgm_offset_spin.setRange(0.0, 3600.0)
        self.bgm_offset_spin.setValue(0.0)
        self.bgm_offset_spin.setSingleStep(1.0)
        self.bgm_offset_spin.setDecimals(1)
        self.bgm_offset_spin.setSuffix("秒")
        self.bgm_offset_spin.setFixedWidth(75)
        self.bgm_offset_spin.setEnabled(False)
        self.bgm_offset_spin.setToolTip("BGMファイルの再生開始位置(秒)。イントロをスキップする場合に使用")
        bgm_row2.addWidget(self.bgm_offset_spin)
        bgm_row2.addWidget(QLabel("フェードイン:"))
        self.bgm_fadein_spin = QDoubleSpinBox()
        self.bgm_fadein_spin.setRange(0.0, 30.0)
        self.bgm_fadein_spin.setValue(1.0)
        self.bgm_fadein_spin.setSingleStep(0.5)
        self.bgm_fadein_spin.setDecimals(1)
        self.bgm_fadein_spin.setSuffix("秒")
        self.bgm_fadein_spin.setFixedWidth(70)
        self.bgm_fadein_spin.setEnabled(False)
        bgm_row2.addWidget(self.bgm_fadein_spin)
        bgm_row2.addWidget(QLabel("フェードアウト:"))
        self.bgm_fadeout_spin = QDoubleSpinBox()
        self.bgm_fadeout_spin.setRange(0.0, 30.0)
        self.bgm_fadeout_spin.setValue(2.0)
        self.bgm_fadeout_spin.setSingleStep(0.5)
        self.bgm_fadeout_spin.setDecimals(1)
        self.bgm_fadeout_spin.setSuffix("秒")
        self.bgm_fadeout_spin.setFixedWidth(70)
        self.bgm_fadeout_spin.setEnabled(False)
        bgm_row2.addWidget(self.bgm_fadeout_spin)
        bgm_row2.addStretch()
        output_vbox.addLayout(bgm_row2)

        # 出力先行
        dest_row = QHBoxLayout()
        dest_row.addWidget(QLabel("出力先:"))
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("出力ファイルパス（空欄の場合は入力フォルダ内に output.mp4 を生成）")
        dest_row.addWidget(self.output_edit)
        self.output_btn = QPushButton("保存先を選択...")
        self.output_btn.setFixedWidth(140)
        self.output_btn.clicked.connect(self._on_browse_output)
        dest_row.addWidget(self.output_btn)
        output_vbox.addLayout(dest_row)

        layout.addWidget(output_group)

        # ---- 動画生成 ----
        generate_group = QGroupBox("④ 動画生成")
        generate_layout = QVBoxLayout(generate_group)

        btn_layout = QHBoxLayout()
        self.generate_btn = QPushButton("▶  動画を生成する")
        self.generate_btn.setFixedHeight(44)
        self.generate_btn.setEnabled(False)
        self.generate_btn.clicked.connect(self._on_generate)
        btn_layout.addWidget(self.generate_btn)

        self.cancel_btn = QPushButton("キャンセル")
        self.cancel_btn.setFixedHeight(44)
        self.cancel_btn.setFixedWidth(100)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self.cancel_btn)

        generate_layout.addLayout(btn_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        generate_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("待機中")
        self.status_label.setStyleSheet("color: #555; font-size: 12px;")
        generate_layout.addWidget(self.status_label)

        layout.addWidget(generate_group)

        # ---- ログ ----
        log_group = QGroupBox("ログ")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(120)
        self.log_text.setFont(QFont("Consolas", 9))
        log_layout.addWidget(self.log_text)
        layout.addWidget(log_group)

    def _apply_style(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
            }
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                border: 1px solid #ccc;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 8px;
                background-color: #ffffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
                color: #333;
            }
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
            QPushButton:disabled {
                background-color: #aaa;
                color: #eee;
            }
            QPushButton#generate_btn {
                background-color: #107c10;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton#generate_btn:hover {
                background-color: #0e6b0e;
            }
            QPushButton#cancel_btn {
                background-color: #c50f1f;
            }
            QPushButton#cancel_btn:hover {
                background-color: #a80f1a;
            }
            QLineEdit {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 5px 8px;
                font-size: 12px;
                background-color: #fafafa;
            }
            QTableWidget {
                border: 1px solid #ddd;
                gridline-color: #eee;
                font-size: 12px;
            }
            QHeaderView::section {
                background-color: #e8e8e8;
                padding: 5px;
                border: none;
                border-right: 1px solid #ccc;
                font-weight: bold;
            }
            QProgressBar {
                border: 1px solid #ccc;
                border-radius: 4px;
                text-align: center;
                height: 22px;
            }
            QProgressBar::chunk {
                background-color: #0078d4;
                border-radius: 3px;
            }
            QTextEdit {
                border: 1px solid #ddd;
                border-radius: 4px;
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
        """)
        self.generate_btn.setObjectName("generate_btn")
        self.cancel_btn.setObjectName("cancel_btn")

    # ---- イベントハンドラ ----

    def _on_browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "入力フォルダを選択", os.path.expanduser("~")
        )
        if folder:
            self.folder_edit.setText(folder)
            self.scan_btn.setEnabled(True)
            # 出力先のデフォルト設定
            default_output = os.path.join(folder, OUTPUT_FILENAME)
            self.output_edit.setText(default_output)
            self._log(f"フォルダを選択: {folder}")
            # 自動スキャン
            self._on_scan()

    def _on_scan(self):
        folder = self.folder_edit.text().strip()
        if not folder:
            QMessageBox.warning(self, "警告", "フォルダを選択してください。")
            return

        try:
            self.scan_result = scan_folder(folder)
            self._update_pairs_table()
            self._log(f"スキャン完了: {self.scan_result.summary}")
            if self.scan_result.audio_format_stats:
                self._log(f"音声形式: {self.scan_result.audio_format_stats}")
            if self.scan_result.image_format_stats:
                self._log(f"画像形式: {self.scan_result.image_format_stats}")
            # count telop files
            _telop_count = sum(
                1 for p in self.scan_result.complete_pairs
                if p.audio_path and find_telop_file(p.audio_path)
            )
            if _telop_count > 0:
                self._log(f"テロップファイル: {_telop_count}件 (.json) を検出しました")
            if self.scan_result.has_complete_pairs:
                self.generate_btn.setEnabled(True)
                self.summary_label.setText(
                    f"スキャン完了 — {self.scan_result.summary}"
                )
                self.summary_label.setStyleSheet("color: #107c10; font-size: 12px; font-weight: bold;")
            else:
                self.generate_btn.setEnabled(False)
                self.summary_label.setText(
                    "完全なペア（音声+画像）が見つかりませんでした。ファイル名を確認してください。"
                )
                self.summary_label.setStyleSheet("color: #c50f1f; font-size: 12px; font-weight: bold;")

        except FileNotFoundError as e:
            QMessageBox.critical(self, "エラー", str(e))
        except PermissionError as e:
            QMessageBox.critical(self, "エラー", str(e))
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"スキャン中にエラーが発生しました:\n{e}")

    def _update_pairs_table(self):
        if not self.scan_result:
            return

        all_pairs = self.scan_result.all_pairs
        self.pairs_table.setRowCount(len(all_pairs))

        # Row background colors
        COLOR_COMPLETE      = QColor(220, 255, 220)   # complete pair: light green
        COLOR_ANIMATED_GIF  = QColor(210, 235, 255)   # animated GIF: light blue
        COLOR_VIDEO         = QColor(255, 235, 210)   # video input: light orange
        COLOR_MULTI         = QColor(240, 220, 255)   # multi-image: light purple
        COLOR_INCOMPLETE    = QColor(255, 245, 200)   # incomplete: light yellow

        for row, pair in enumerate(all_pairs):
            # base name
            item_name = QTableWidgetItem(pair.base_name)
            item_name.setFont(QFont("", 11, QFont.Bold))
            self.pairs_table.setItem(row, 0, item_name)

            # audio file
            audio_text = os.path.basename(pair.audio_path) if pair.audio_path else "（なし）"
            item_audio = QTableWidgetItem(audio_text)
            if not pair.audio_path:
                item_audio.setForeground(QColor("#c50f1f"))
            self.pairs_table.setItem(row, 1, item_audio)

            # visual file(s) - with badge display
            if not pair.single_mode:
                # multi-image mode
                names = [os.path.basename(v.path) for v in pair.visual_items]
                if len(names) <= 3:
                    image_text = "  /  ".join(names) + f"  [{len(names)}枚]"
                else:
                    image_text = (
                        "  /  ".join(names[:2])
                        + f"  ...他{len(names)-2}枚  [{len(names)}枚合計]"
                    )
                item_image = QTableWidgetItem(image_text)
                item_image.setForeground(QColor("#5a0080"))  # purple for multi-image
            elif pair.image_path:
                img_basename = os.path.basename(pair.image_path)
                if pair.is_animated_gif:
                    image_text = f"{img_basename}  [アニメGIF]"
                elif pair.image_ext == '.gif':
                    image_text = f"{img_basename}  [静止GIF]"
                elif pair.is_video_input:
                    image_text = f"{img_basename}  [動画入力]"
                else:
                    image_text = img_basename
                item_image = QTableWidgetItem(image_text)
                if pair.is_animated_gif:
                    item_image.setForeground(QColor("#0050a0"))  # blue for animated GIF
                elif pair.is_video_input:
                    item_image.setForeground(QColor("#7a3800"))  # brown for video input
            else:
                item_image = QTableWidgetItem("（なし）")
                item_image.setForeground(QColor("#c50f1f"))
            self.pairs_table.setItem(row, 2, item_image)

            # telop column
            telop_json = find_telop_file(pair.audio_path) if pair.audio_path else None
            if telop_json:
                try:
                    entries = load_telop_file(telop_json)
                    telop_text = f"{len(entries)}件"
                    item_telop = QTableWidgetItem(telop_text)
                    item_telop.setForeground(QColor("#7b00d4"))
                except Exception as e:
                    item_telop = QTableWidgetItem(f"エラー")
                    item_telop.setForeground(QColor("#c50f1f"))
            else:
                item_telop = QTableWidgetItem("—")
                item_telop.setForeground(QColor("#888888"))
            self.pairs_table.setItem(row, 3, item_telop)
            # timing column (col 4) - only for multi-image mode
            if not pair.single_mode and pair.audio_path and pair.visual_items:
                timing_json = find_timing_file(pair.audio_path)
                if timing_json:
                    item_paths = [v.path for v in pair.visual_items]
                    try:
                        summary = get_timing_summary(item_paths, 0.0, timing_json)
                        item_timing = QTableWidgetItem(summary)
                        item_timing.setForeground(QColor("#005a9e"))
                    except Exception:
                        item_timing = QTableWidgetItem("JSONエラー")
                        item_timing.setForeground(QColor("#c50f1f"))
                else:
                    item_timing = QTableWidgetItem("均等分割")
                    item_timing.setForeground(QColor("#888888"))
            else:
                item_timing = QTableWidgetItem("—")
                item_timing.setForeground(QColor("#888888"))
            self.pairs_table.setItem(row, 4, item_timing)
            # status (col 5)
            item_status = QTableWidgetItem(pair.status_text)
            self.pairs_table.setItem(row, 5, item_status)
            # row background color
            if pair.is_complete and not pair.single_mode:
                bg_color = COLOR_MULTI
            elif pair.is_complete and pair.single_mode and pair.is_animated_gif:
                bg_color = COLOR_ANIMATED_GIF
            elif pair.is_complete and pair.single_mode and pair.is_video_input:
                bg_color = COLOR_VIDEO
            elif pair.is_complete:
                bg_color = COLOR_COMPLETE
            else:
                bg_color = COLOR_INCOMPLETE
            for col in range(6):
                item = self.pairs_table.item(row, col)
                if item:
                    item.setBackground(bg_color)

    def _update_resolution_label(self):
        """解像度ラベルを現在のプリセットに合わせて更新する"""
        preset_name = self.preset_combo.currentText() if hasattr(self, 'preset_combo') else DEFAULT_PRESET
        if preset_name in RESOLUTION_PRESETS:
            w, h = RESOLUTION_PRESETS[preset_name]
            self.resolution_label.setText(f"({w} x {h})")
        else:
            self.resolution_label.setText("")

    def _on_preset_changed(self, preset_name: str):
        """解像度プリセット変更時の処理"""
        self._update_resolution_label()
        if preset_name in RESOLUTION_PRESETS:
            w, h = RESOLUTION_PRESETS[preset_name]
            self._log(f"解像度を変更: {preset_name} ({w}x{h})")

    def _on_viz_check_changed(self, state: int):
        """ビジュアライザーチェックボックス変更時の処理"""
        enabled = (state == 2)  # Qt.Checked == 2
        self.viz_style_combo.setEnabled(enabled)
        self.viz_height_spin.setEnabled(enabled)
        self.viz_opacity_spin.setEnabled(enabled)
        self.viz_color_mode_combo.setEnabled(enabled)
        # 単色ボタンはカラーモードが solid のときのみ有効
        is_solid = (self.viz_color_mode_combo.currentData() == "solid")
        self.viz_color_btn.setEnabled(enabled and is_solid)

    def _on_viz_color_mode_changed(self, index: int):
        """カラーモードコンボボックス変更時の処理"""
        mode = self.viz_color_mode_combo.currentData()
        is_solid = (mode == "solid")
        viz_enabled = self.viz_check.isChecked()
        self.viz_color_btn.setEnabled(viz_enabled and is_solid)

    def _on_bgm_check_changed(self, state: int):
        """BGMミックスチェックボックス変更時の処理"""
        enabled = (state == 2)  # Qt.Checked == 2
        self.bgm_edit.setEnabled(enabled)
        self.bgm_browse_btn.setEnabled(enabled)
        self.voice_vol_spin.setEnabled(enabled)
        self.bgm_vol_spin.setEnabled(enabled)
        self.bgm_offset_spin.setEnabled(enabled)
        self.bgm_fadein_spin.setEnabled(enabled)
        self.bgm_fadeout_spin.setEnabled(enabled)
        # フォルダ内のBGMファイルを自動検出
        if enabled and not self.bgm_edit.text().strip():
            folder = self.folder_edit.text()
            if folder and os.path.isdir(folder):
                auto_bgm = find_folder_bgm(folder)
                if auto_bgm:
                    self.bgm_edit.setText(auto_bgm)
                    self._log(f"BGMファイルを自動検出: {os.path.basename(auto_bgm)}")

    def _on_browse_bgm(self):
        """BGMファイル選択ダイアログ"""
        default_dir = self.folder_edit.text() or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, "BGMファイルを選択", default_dir,
            "音声ファイル (*.mp3 *.wav *.flac *.ogg *.m4a *.aac *.wma)"
        )
        if path:
            self.bgm_edit.setText(path)

    def _update_viz_color_btn(self):
        """カラーボタンの背景色を現在の選択色に更新する"""
        c = self._viz_color_value
        self.viz_color_btn.setStyleSheet(
            f"background-color: {c}; border: 1px solid #888; border-radius: 3px;"
        )
        self.viz_color_btn.setToolTip(f"単色の色: {c}（クリックして変更）")

    def _on_viz_color_btn_clicked(self):
        """カラーボタンクリック時に色選択ダイアログを開く"""
        from PyQt5.QtWidgets import QColorDialog
        from PyQt5.QtGui import QColor
        current = QColor(self._viz_color_value)
        color = QColorDialog.getColor(current, self, "ビジュアライザーの色を選択")
        if color.isValid():
            self._viz_color_value = color.name()  # "#rrggbb"
            self._update_viz_color_btn()

    def _on_browse_output(self):
        default_dir = self.folder_edit.text() or os.path.expanduser("~")
        path, _ = QFileDialog.getSaveFileName(
            self, "出力ファイルを選択", os.path.join(default_dir, OUTPUT_FILENAME),
            "MP4動画 (*.mp4)"
        )
        if path:
            if not path.lower().endswith('.mp4'):
                path += '.mp4'
            self.output_edit.setText(path)

    def _on_generate(self):
        if not self.scan_result or not self.scan_result.has_complete_pairs:
            QMessageBox.warning(self, "警告", "完全なペアがありません。")
            return

        output_path = self.output_edit.text().strip()
        if not output_path:
            folder = self.folder_edit.text()
            output_path = os.path.join(folder, OUTPUT_FILENAME)
            self.output_edit.setText(output_path)

        # 出力先の確認
        if os.path.exists(output_path):
            reply = QMessageBox.question(
                self, "確認",
                f"出力ファイルが既に存在します:\n{output_path}\n\n上書きしますか？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        # 完全ペアのみ使用
        pairs = self.scan_result.complete_pairs

        # 解像度プリセットを取得
        preset_name = self.preset_combo.currentText()
        w, h = RESOLUTION_PRESETS.get(preset_name, RESOLUTION_PRESETS[DEFAULT_PRESET])
        ken_burns = self.ken_burns_check.isChecked()
        title_overlay = self.title_overlay_check.isChecked()
        viz_enabled = self.viz_check.isChecked()
        viz_style = self.viz_style_combo.currentData() or "waveform"
        viz_height = self.viz_height_spin.value()
        viz_opacity = self.viz_opacity_spin.value() / 100.0
        viz_color_mode = self.viz_color_mode_combo.currentData() or "solid"
        viz_color = self._viz_color_value
        # BGM設定
        bgm_enabled = self.bgm_check.isChecked()
        bgm_path_text = self.bgm_edit.text().strip() if bgm_enabled else ""
        # BGMファイルが指定されていない場合はフォルダ内を自動検出
        if bgm_enabled and not bgm_path_text:
            folder = self.folder_edit.text()
            bgm_path_text = find_folder_bgm(folder) or ""
        if bgm_enabled and not bgm_path_text:
            QMessageBox.warning(self, "警告",
                "BGMファイルが指定されていません。\n"
                "ファイルを選択するか、入力フォルダに _bgm.mp3 を配置してください。")
            return
        if bgm_enabled and bgm_path_text and not os.path.isfile(bgm_path_text):
            QMessageBox.warning(self, "警告", f"BGMファイルが見つかりません:\n{bgm_path_text}")
            return
        config = GenerationConfig(
            pairs=pairs,
            output_path=output_path,
            width=w,
            height=h,
            title_overlay=title_overlay,
            ken_burns=ken_burns,
            visualizer_enabled=viz_enabled,
            visualizer_style=viz_style,
            visualizer_height=viz_height,
            visualizer_opacity=viz_opacity,
            visualizer_color=viz_color,
            visualizer_color_mode=viz_color_mode,
            bgm_path=bgm_path_text if bgm_enabled else None,
            voice_volume=self.voice_vol_spin.value() if bgm_enabled else 1.0,
            bgm_volume=self.bgm_vol_spin.value() if bgm_enabled else 0.5,
            bgm_start_offset=self.bgm_offset_spin.value() if bgm_enabled else 0.0,
            bgm_fade_in=self.bgm_fadein_spin.value() if bgm_enabled else 1.0,
            bgm_fade_out=self.bgm_fadeout_spin.value() if bgm_enabled else 2.0,
        )
        kb_note = " + ケン・バーンズ効果" if ken_burns else ""
        title_note = " + タイトル表示" if title_overlay else " (タイトル非表示)"
        color_mode_label = VIZUALIZER_COLOR_MODES.get(viz_color_mode, viz_color_mode)
        viz_note = f" + ビジュアライザー({VIZUALIZER_STYLES.get(viz_style, viz_style)}/{color_mode_label})" if viz_enabled else ""
        bgm_note = f" + BGM({os.path.basename(bgm_path_text)}, 音声{config.voice_volume:.1f}x/BGM{config.bgm_volume:.1f}x)" if bgm_enabled and bgm_path_text else ""
        self._log(f"動画生成開始: {len(pairs)} チャプター | {preset_name} ({w}x{h}){title_note}{kb_note}{viz_note}{bgm_note} → {output_path}")
        self._set_generating_state(True)

        self.worker = VideoGeneratorWorker(config)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.cancelled.connect(self._on_cancelled)
        self.worker.start()

    def _on_cancel(self):
        if self.worker and self.worker.isRunning():
            self.worker.request_cancel()
            self.status_label.setText("キャンセル中...")
            self.cancel_btn.setEnabled(False)
            self._log("キャンセルを要求しました...")

    def _on_progress(self, percent: int, message: str):
        self.progress_bar.setValue(percent)
        self.status_label.setText(message)
        self._log(f"[{percent:3d}%] {message}")

    def _on_finished(self, output_path: str):
        self._set_generating_state(False)
        self.progress_bar.setValue(100)
        self.status_label.setText(f"✓ 完了: {output_path}")
        self.status_label.setStyleSheet("color: #107c10; font-size: 12px; font-weight: bold;")
        self._log(f"✓ 動画生成完了: {output_path}")

        QMessageBox.information(
            self, "完了",
            f"動画の生成が完了しました！\n\n出力ファイル:\n{output_path}"
        )

    def _on_error(self, error_message: str):
        self._set_generating_state(False)
        self.status_label.setText("✗ エラーが発生しました")
        self.status_label.setStyleSheet("color: #c50f1f; font-size: 12px; font-weight: bold;")
        self._log(f"✗ エラー: {error_message}")

        QMessageBox.critical(
            self, "エラー",
            f"動画生成中にエラーが発生しました:\n\n{error_message}"
        )

    def _on_cancelled(self):
        self._set_generating_state(False)
        self.progress_bar.setValue(0)
        self.status_label.setText("キャンセルされました")
        self.status_label.setStyleSheet("color: #555; font-size: 12px;")
        self._log("動画生成がキャンセルされました。")

    def _set_generating_state(self, generating: bool):
        self.generate_btn.setEnabled(not generating)
        self.cancel_btn.setEnabled(generating)
        self.browse_btn.setEnabled(not generating)
        self.scan_btn.setEnabled(not generating)
        self.output_btn.setEnabled(not generating)
        if not generating:
            self.status_label.setStyleSheet("color: #555; font-size: 12px;")

    def _log(self, message: str):
        self.log_text.append(message)
        # スクロールを末尾に
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            reply = QMessageBox.question(
                self, "確認",
                "動画生成中です。終了しますか？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.worker.request_cancel()
                self.worker.wait(3000)
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
