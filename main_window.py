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
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer
from PyQt5.QtGui import QFont, QColor, QPalette, QIcon

from file_scanner import scan_folder, ScanResult, FilePair, AUDIO_EXTENSIONS, IMAGE_PRIORITY, VIDEO_PRIORITY
from telop_parser import find_telop_file, load_telop_file
from timing_parser import find_timing_file, get_timing_summary
from video_generator import (
    generate_video, GenerationConfig, OUTPUT_FILENAME,
    RESOLUTION_PRESETS, DEFAULT_PRESET, VIZUALIZER_STYLES, VIZUALIZER_COLOR_MODES,
    find_folder_bgm,
)
from project_manager import (
    PROJECT_FILE_EXTENSION, ProjectFileError,
    get_project_file_filter, load_project_file, project_default_path,
    save_project_file,
)
from output_queue import (
    OutputQueue, QueueItemError, STATUS_CANCELLED, STATUS_DONE,
    STATUS_ERROR, STATUS_RUNNING, STATUS_WAITING, prepare_queue_job,
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
        self.current_project_path: str = None
        self.output_queue = OutputQueue()
        self.queue_active = False

        self._init_ui()
        self._apply_style()

    def _init_ui(self):
        self.setWindowTitle("SlideshowMaker - 音声+画像/動画→MP4動画生成")
        self.setMinimumSize(980, 820)
        self.resize(1180, 900)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        # ---- プロジェクト操作 ----
        project_group = QGroupBox("プロジェクト")
        project_layout = QHBoxLayout(project_group)
        self.project_label = QLabel("未保存のプロジェクト")
        self.project_label.setStyleSheet("color: #555; font-size: 12px;")
        project_layout.addWidget(self.project_label)
        project_layout.addStretch()
        self.save_project_btn = QPushButton("プロジェクトを保存...")
        self.save_project_btn.setFixedWidth(150)
        self.save_project_btn.setToolTip(
            "現在の入力フォルダ・出力設定・BGM・ビジュアライザー設定を保存します。\n"
            "画像・音声などの素材ファイル自体は保存されません。"
        )
        self.save_project_btn.clicked.connect(self._on_save_project)
        project_layout.addWidget(self.save_project_btn)
        self.load_project_btn = QPushButton("プロジェクトを読込...")
        self.load_project_btn.setFixedWidth(150)
        self.load_project_btn.setToolTip("保存済みの .slideshow.json プロジェクトを読み込みます。")
        self.load_project_btn.clicked.connect(self._on_load_project)
        project_layout.addWidget(self.load_project_btn)
        layout.addWidget(project_group)

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

        # ---- 一括出力キュー ----
        queue_group = QGroupBox("④ 一括出力キュー")
        queue_layout = QVBoxLayout(queue_group)
        queue_hint = QLabel(
            "保存済みのプロジェクト（.slideshow.json）を登録し、上から順に連続生成します。"
        )
        queue_hint.setStyleSheet("color: #555; font-size: 11px;")
        queue_layout.addWidget(queue_hint)

        self.queue_table = QTableWidget()
        self.queue_table.setColumnCount(5)
        self.queue_table.setHorizontalHeaderLabels([
            "プロジェクト", "入力フォルダ", "出力ファイル", "状態", "詳細"
        ])
        self.queue_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.queue_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.queue_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.queue_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.queue_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.queue_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.queue_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.queue_table.setAlternatingRowColors(True)
        self.queue_table.verticalHeader().setVisible(False)
        self.queue_table.setMinimumHeight(130)
        self.queue_table.setMaximumHeight(170)
        queue_layout.addWidget(self.queue_table)

        queue_buttons = QHBoxLayout()
        self.queue_add_projects_btn = QPushButton("プロジェクトを追加...")
        self.queue_add_projects_btn.clicked.connect(self._on_queue_add_projects)
        queue_buttons.addWidget(self.queue_add_projects_btn)
        self.queue_add_current_btn = QPushButton("現在の設定を追加")
        self.queue_add_current_btn.clicked.connect(self._on_queue_add_current)
        queue_buttons.addWidget(self.queue_add_current_btn)
        self.queue_remove_btn = QPushButton("選択項目を削除")
        self.queue_remove_btn.clicked.connect(self._on_queue_remove)
        queue_buttons.addWidget(self.queue_remove_btn)
        self.queue_up_btn = QPushButton("▲")
        self.queue_up_btn.setFixedWidth(42)
        self.queue_up_btn.setToolTip("選択項目を上へ移動")
        self.queue_up_btn.clicked.connect(lambda: self._on_queue_move(-1))
        queue_buttons.addWidget(self.queue_up_btn)
        self.queue_down_btn = QPushButton("▼")
        self.queue_down_btn.setFixedWidth(42)
        self.queue_down_btn.setToolTip("選択項目を下へ移動")
        self.queue_down_btn.clicked.connect(lambda: self._on_queue_move(1))
        queue_buttons.addWidget(self.queue_down_btn)
        self.queue_clear_btn = QPushButton("キューをクリア")
        self.queue_clear_btn.clicked.connect(self._on_queue_clear)
        queue_buttons.addWidget(self.queue_clear_btn)
        queue_buttons.addStretch()
        self.queue_start_btn = QPushButton("▶ 一括出力を開始")
        self.queue_start_btn.setObjectName("queue_start_btn")
        self.queue_start_btn.setEnabled(False)
        self.queue_start_btn.clicked.connect(self._on_queue_start)
        queue_buttons.addWidget(self.queue_start_btn)
        self.queue_stop_btn = QPushButton("現在の出力後に停止")
        self.queue_stop_btn.setObjectName("queue_stop_btn")
        self.queue_stop_btn.setEnabled(False)
        self.queue_stop_btn.clicked.connect(self._on_queue_stop_after_current)
        queue_buttons.addWidget(self.queue_stop_btn)
        queue_layout.addLayout(queue_buttons)

        self.queue_summary_label = QLabel("キューは空です")
        self.queue_summary_label.setStyleSheet("color: #555; font-size: 11px;")
        queue_layout.addWidget(self.queue_summary_label)
        layout.addWidget(queue_group)

        # ---- 動画生成 ----
        generate_group = QGroupBox("⑤ 動画生成")
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
            QPushButton#queue_start_btn {
                background-color: #6b4c9a;
                font-weight: bold;
            }
            QPushButton#queue_start_btn:hover {
                background-color: #553b7a;
            }
            QPushButton#queue_stop_btn {
                background-color: #c50f1f;
            }
            QPushButton#queue_stop_btn:hover {
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

    # ---- プロジェクト保存・読込 ----

    def _collect_project_settings(self) -> dict:
        """現在のUI設定をプロジェクト保存用の辞書として取得する。"""
        return {
            "input_folder": self.folder_edit.text().strip(),
            "output_path": self.output_edit.text().strip(),
            "preset_name": self.preset_combo.currentText(),
            "ken_burns": self.ken_burns_check.isChecked(),
            "title_overlay": self.title_overlay_check.isChecked(),
            "visualizer_enabled": self.viz_check.isChecked(),
            "visualizer_style": self.viz_style_combo.currentData() or "waveform",
            "visualizer_height": self.viz_height_spin.value(),
            "visualizer_opacity_percent": self.viz_opacity_spin.value(),
            "visualizer_color_mode": self.viz_color_mode_combo.currentData() or "solid",
            "visualizer_color": self._viz_color_value,
            "bgm_enabled": self.bgm_check.isChecked(),
            "bgm_path": self.bgm_edit.text().strip(),
            "voice_volume": self.voice_vol_spin.value(),
            "bgm_volume": self.bgm_vol_spin.value(),
            "bgm_start_offset": self.bgm_offset_spin.value(),
            "bgm_fade_in": self.bgm_fadein_spin.value(),
            "bgm_fade_out": self.bgm_fadeout_spin.value(),
        }

    def _set_combo_data(self, combo: QComboBox, value: str, fallback: str):
        """コンボボックスをdata値で安全に設定する。"""
        index = combo.findData(value)
        if index < 0:
            index = combo.findData(fallback)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _update_project_label(self):
        """現在開いているプロジェクト名を画面上に表示する。"""
        if self.current_project_path:
            name = os.path.basename(self.current_project_path)
            self.project_label.setText(f"プロジェクト: {name}")
            self.project_label.setToolTip(self.current_project_path)
        else:
            self.project_label.setText("未保存のプロジェクト")
            self.project_label.setToolTip("")

    def _on_save_project(self):
        """現在の生成設定を .slideshow.json として保存する。"""
        default_path = (
            self.current_project_path
            or project_default_path(self.folder_edit.text().strip())
            or os.path.join(os.path.expanduser("~"), "slideshow_project" + PROJECT_FILE_EXTENSION)
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "プロジェクトを保存", default_path, get_project_file_filter()
        )
        if not path:
            return
        if not path.lower().endswith(PROJECT_FILE_EXTENSION):
            path += PROJECT_FILE_EXTENSION

        if os.path.exists(path) and os.path.abspath(path) != os.path.abspath(self.current_project_path or ""):
            reply = QMessageBox.question(
                self, "確認", f"プロジェクトファイルが既に存在します:\n{path}\n\n上書きしますか？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        try:
            saved_path = save_project_file(path, self._collect_project_settings())
            self.current_project_path = saved_path
            self._update_project_label()
            self._log(f"プロジェクトを保存: {saved_path}")
            self.status_label.setText(f"プロジェクトを保存しました: {os.path.basename(saved_path)}")
        except (ProjectFileError, OSError) as e:
            QMessageBox.critical(self, "保存エラー", f"プロジェクトを保存できませんでした:\n{e}")

    def _apply_project_settings(self, settings: dict):
        """読込済みのプロジェクト設定をUIへ反映する。"""
        self.folder_edit.setText(settings["input_folder"])
        self.scan_btn.setEnabled(bool(settings["input_folder"]))
        self.output_edit.setText(settings["output_path"])

        preset_name = settings["preset_name"]
        if preset_name in RESOLUTION_PRESETS:
            self.preset_combo.setCurrentText(preset_name)
        else:
            self.preset_combo.setCurrentText(DEFAULT_PRESET)
        self.ken_burns_check.setChecked(settings["ken_burns"])
        self.title_overlay_check.setChecked(settings["title_overlay"])

        self._set_combo_data(self.viz_style_combo, settings["visualizer_style"], "waveform")
        self.viz_height_spin.setValue(settings["visualizer_height"])
        self.viz_opacity_spin.setValue(settings["visualizer_opacity_percent"])
        self._set_combo_data(self.viz_color_mode_combo, settings["visualizer_color_mode"], "solid")
        self._viz_color_value = settings["visualizer_color"]
        self._update_viz_color_btn()
        self.viz_check.setChecked(settings["visualizer_enabled"])
        self._on_viz_check_changed(Qt.Checked if settings["visualizer_enabled"] else Qt.Unchecked)

        # BGMファイルパスを先に復元してから有効化し、自動検出で上書きしないようにする
        self.bgm_edit.setText(settings["bgm_path"])
        self.voice_vol_spin.setValue(settings["voice_volume"])
        self.bgm_vol_spin.setValue(settings["bgm_volume"])
        self.bgm_offset_spin.setValue(settings["bgm_start_offset"])
        self.bgm_fadein_spin.setValue(settings["bgm_fade_in"])
        self.bgm_fadeout_spin.setValue(settings["bgm_fade_out"])
        self.bgm_check.setChecked(settings["bgm_enabled"])
        self._on_bgm_check_changed(Qt.Checked if settings["bgm_enabled"] else Qt.Unchecked)

    def _on_load_project(self):
        """.slideshow.jsonを読み込み、設定を復元して入力フォルダを再スキャンする。"""
        default_dir = os.path.dirname(self.current_project_path) if self.current_project_path else os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, "プロジェクトを読込", default_dir, get_project_file_filter()
        )
        if not path:
            return

        try:
            settings = load_project_file(path)
            self._apply_project_settings(settings)
            self.current_project_path = os.path.abspath(path)
            self._update_project_label()
            self._log(f"プロジェクトを読込: {self.current_project_path}")

            folder = settings["input_folder"]
            if folder and os.path.isdir(folder):
                self._on_scan()
            else:
                self.scan_result = None
                self.pairs_table.setRowCount(0)
                self.generate_btn.setEnabled(False)
                self.summary_label.setText("入力フォルダが見つかりません。フォルダを選択し直してからスキャンしてください。")
                self.summary_label.setStyleSheet("color: #c50f1f; font-size: 12px; font-weight: bold;")
                if folder:
                    self._log(f"警告: 入力フォルダが見つかりません: {folder}")
                    QMessageBox.warning(
                        self, "入力フォルダが見つかりません",
                        "プロジェクト設定は読み込みましたが、入力フォルダが見つかりません。\n"
                        "フォルダを選択し直してからスキャンしてください。",
                    )

            if settings["bgm_enabled"] and settings["bgm_path"] and not os.path.isfile(settings["bgm_path"]):
                self._log(f"警告: BGMファイルが見つかりません: {settings['bgm_path']}")
        except (ProjectFileError, OSError) as e:
            QMessageBox.critical(self, "読込エラー", f"プロジェクトを読み込めませんでした:\n{e}")

    # ---- 一括出力キュー ----

    def _selected_queue_index(self):
        """キュー表で選択されている行番号を返す。"""
        index = self.queue_table.currentRow()
        return index if index >= 0 else None

    def _update_queue_table(self):
        """キューの状態を表と操作ボタンへ反映する。"""
        status_colors = {
            STATUS_WAITING: QColor("#666666"),
            STATUS_RUNNING: QColor("#0067b1"),
            STATUS_DONE: QColor("#107c10"),
            STATUS_ERROR: QColor("#c50f1f"),
            STATUS_CANCELLED: QColor("#8a6d3b"),
        }
        row_colors = {
            STATUS_RUNNING: QColor(220, 240, 255),
            STATUS_DONE: QColor(220, 255, 220),
            STATUS_ERROR: QColor(255, 225, 225),
            STATUS_CANCELLED: QColor(255, 245, 210),
        }
        self.queue_table.setRowCount(len(self.output_queue.items))
        for row, item in enumerate(self.output_queue.items):
            input_folder = str(item.settings.get("input_folder", "") or "")
            output_path = item.output_path or str(item.settings.get("output_path", "") or "")
            values = [
                item.display_name,
                input_folder,
                output_path or "（入力フォルダ内に output.mp4）",
                item.status,
                item.message or "—",
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 3:
                    cell.setForeground(status_colors.get(item.status, QColor("#666666")))
                    cell.setFont(QFont("", 10, QFont.Bold))
                if item.status in row_colors:
                    cell.setBackground(row_colors[item.status])
                self.queue_table.setItem(row, column, cell)

        counts = self.output_queue.summary()
        total = len(self.output_queue.items)
        if not total:
            self.queue_summary_label.setText("キューは空です")
        else:
            self.queue_summary_label.setText(
                f"登録: {total}件  |  待機: {counts[STATUS_WAITING]}  |  "
                f"生成中: {counts[STATUS_RUNNING]}  |  完了: {counts[STATUS_DONE]}  |  "
                f"エラー: {counts[STATUS_ERROR]}  |  中止: {counts[STATUS_CANCELLED]}"
            )
        self._set_queue_controls()

    def _set_queue_controls(self):
        """キュー実行中かどうかに応じてキュー操作ボタンを切り替える。"""
        editable = not self.queue_active
        has_items = bool(self.output_queue.items)
        for button in (
            self.queue_add_projects_btn,
            self.queue_add_current_btn,
            self.queue_remove_btn,
            self.queue_up_btn,
            self.queue_down_btn,
            self.queue_clear_btn,
        ):
            button.setEnabled(editable)
        self.queue_start_btn.setEnabled(editable and has_items)
        self.queue_stop_btn.setEnabled(self.queue_active and not self.output_queue.stop_requested)

    def _on_queue_add_projects(self):
        """保存済みプロジェクトを複数選択してキューへ追加する。"""
        default_dir = os.path.dirname(self.current_project_path) if self.current_project_path else os.path.expanduser("~")
        paths, _ = QFileDialog.getOpenFileNames(
            self, "キューへ追加するプロジェクトを選択", default_dir, get_project_file_filter()
        )
        if not paths:
            return

        added_count = 0
        errors = []
        for path in paths:
            try:
                added = self.output_queue.add_project_files([path])
                added_count += len(added)
            except Exception as error:
                errors.append(f"{os.path.basename(path)}: {error}")
        self._update_queue_table()
        if added_count:
            self._log(f"一括出力キューへ {added_count}件追加しました")
        if errors:
            QMessageBox.warning(
                self, "一部のプロジェクトを追加できません",
                "以下のプロジェクトを読み込めませんでした:\n\n" + "\n".join(errors),
            )

    def _on_queue_add_current(self):
        """現在の画面設定をスナップショットとしてキューへ追加する。"""
        settings = self._collect_project_settings()
        if not settings["input_folder"]:
            QMessageBox.warning(self, "警告", "キューへ追加する前に入力フォルダを選択してください。")
            return
        display_name = (
            os.path.basename(self.current_project_path)
            if self.current_project_path else "現在の設定"
        )
        self.output_queue.add_settings_snapshot(settings, display_name)
        self._update_queue_table()
        self._log(f"一括出力キューへ現在の設定を追加: {display_name}")

    def _on_queue_remove(self):
        """選択中のキュー項目を削除する。"""
        index = self._selected_queue_index()
        if index is None:
            QMessageBox.information(self, "確認", "削除するキュー項目を選択してください。")
            return
        try:
            removed = self.output_queue.remove_at(index)
            self._update_queue_table()
            self._log(f"キュー項目を削除: {removed.display_name}")
        except (QueueItemError, IndexError) as error:
            QMessageBox.warning(self, "削除できません", str(error))

    def _on_queue_move(self, direction: int):
        """選択中のキュー項目を上下へ移動する。"""
        index = self._selected_queue_index()
        if index is None:
            return
        if self.output_queue.move(index, direction):
            new_index = index + direction
            self._update_queue_table()
            self.queue_table.selectRow(new_index)

    def _on_queue_clear(self):
        """キューが停止中の場合に全項目を削除する。"""
        if self.queue_active:
            return
        if not self.output_queue.items:
            return
        reply = QMessageBox.question(
            self, "確認", "一括出力キューの全項目を削除しますか？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.output_queue.clear_waiting()
            self._update_queue_table()
            self._log("一括出力キューをクリアしました")

    def _on_queue_start(self):
        """一括出力を開始する。既存の完了・エラー状態は再実行対象として待機に戻す。"""
        if not self.output_queue.items:
            return

        # 単体出力と同様に、既存の出力ファイルは開始前に一度だけ確認する。
        existing_outputs = []
        for item in self.output_queue.items:
            settings = item.settings
            input_folder = str(settings.get("input_folder", "") or "")
            output_path = str(settings.get("output_path", "") or "")
            if not output_path and input_folder:
                output_path = os.path.join(input_folder, OUTPUT_FILENAME)
            if output_path and os.path.isfile(output_path):
                existing_outputs.append(output_path)
        if existing_outputs:
            preview = "\n".join(existing_outputs[:5])
            remaining = len(existing_outputs) - 5
            if remaining > 0:
                preview += f"\n...ほか {remaining}件"
            reply = QMessageBox.question(
                self, "出力ファイルの上書き確認",
                f"既に存在する出力ファイルが {len(existing_outputs)}件あります。\n"
                f"一括出力では、以下のファイルを上書きします。\n\n{preview}\n\n"
                "続行しますか？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        self.output_queue.reset_for_run()
        self.queue_active = True
        self.progress_bar.setValue(0)
        self._update_queue_table()
        self._log(f"一括出力を開始: {len(self.output_queue.items)}件")
        QTimer.singleShot(0, self._start_next_queue_item)

    def _on_queue_stop_after_current(self):
        """現在の動画の完了後、新しいキュー項目を開始しない。"""
        if not self.queue_active:
            return
        self.output_queue.request_stop()
        self._update_queue_table()
        self.status_label.setText("現在の動画の生成完了後に一括出力を停止します...")
        self._log("一括出力の停止を要求しました（現在の動画は完了まで処理します）")

    def _mark_waiting_queue_items_cancelled(self, message: str):
        """未開始の項目を中止状態へ更新する。"""
        for item in self.output_queue.items:
            if item.status == STATUS_WAITING:
                item.status = STATUS_CANCELLED
                item.message = message

    def _start_next_queue_item(self):
        """次の待機項目を検証してバックグラウンド生成を開始する。"""
        if not self.queue_active:
            return

        index = self.output_queue.next_waiting_index()
        if index is None:
            if self.output_queue.stop_requested:
                self._mark_waiting_queue_items_cancelled("停止要求により未実行")
            self._finish_queue_run()
            return

        self.output_queue.current_index = index
        item = self.output_queue.items[index]
        try:
            job = prepare_queue_job(item)
        except Exception as error:
            item.status = STATUS_ERROR
            item.message = str(error)
            self._log(f"キュー {index + 1}/{len(self.output_queue.items)} エラー: {item.display_name} — {error}")
            self._update_queue_table()
            QTimer.singleShot(0, self._start_next_queue_item)
            return

        item.status = STATUS_RUNNING
        item.message = f"{job.chapter_count}チャプターを生成中"
        self._update_queue_table()
        total = len(self.output_queue.items)
        self.status_label.setText(f"一括出力 {index + 1}/{total}: {item.display_name}")
        self._log(
            f"キュー {index + 1}/{total} を開始: {item.display_name} "
            f"({job.chapter_count}チャプター) → {job.config.output_path}"
        )
        self._set_generating_state(True)
        self.worker = VideoGeneratorWorker(job.config)
        self.worker.progress.connect(self._on_queue_progress)
        self.worker.finished.connect(self._on_queue_item_finished)
        self.worker.error.connect(self._on_queue_item_error)
        self.worker.cancelled.connect(self._on_queue_item_cancelled)
        self.worker.start()

    def _on_queue_progress(self, percent: int, message: str):
        """現在のキュー項目の進捗を個別・全体進捗として表示する。"""
        index = self.output_queue.current_index
        if index is None or not self.queue_active:
            return
        item = self.output_queue.items[index]
        item.message = message
        total = max(1, len(self.output_queue.items))
        overall_percent = int(((index + percent / 100.0) / total) * 100)
        self.progress_bar.setValue(overall_percent)
        self.status_label.setText(
            f"一括出力 {index + 1}/{total} [{percent:3d}%]: {message}"
        )
        self._update_queue_table()

    def _on_queue_item_finished(self, output_path: str):
        """1件の完了を記録して、必要なら次の項目を開始する。"""
        index = self.output_queue.current_index
        if index is None:
            return
        item = self.output_queue.items[index]
        item.status = STATUS_DONE
        item.message = f"完了: {os.path.basename(output_path)}"
        item.output_path = output_path
        self._log(f"キュー {index + 1}/{len(self.output_queue.items)} 完了: {output_path}")
        self._set_generating_state(False)
        self._update_queue_table()
        QTimer.singleShot(0, self._start_next_queue_item)

    def _on_queue_item_error(self, error_message: str):
        """1件のエラーを記録し、停止要求がなければ次項目へ進む。"""
        index = self.output_queue.current_index
        if index is None:
            return
        item = self.output_queue.items[index]
        item.status = STATUS_ERROR
        item.message = error_message
        self._log(f"キュー {index + 1}/{len(self.output_queue.items)} エラー: {item.display_name} — {error_message}")
        self._set_generating_state(False)
        self._update_queue_table()
        QTimer.singleShot(0, self._start_next_queue_item)

    def _on_queue_item_cancelled(self):
        """現在の出力をキャンセルした場合は、残りのキューも中止して終了する。"""
        index = self.output_queue.current_index
        if index is not None:
            item = self.output_queue.items[index]
            item.status = STATUS_CANCELLED
            item.message = "現在の出力をキャンセル"
        self.output_queue.request_stop()
        self._mark_waiting_queue_items_cancelled("現在の出力がキャンセルされたため未実行")
        self._set_generating_state(False)
        self._update_queue_table()
        self._finish_queue_run()

    def _finish_queue_run(self):
        """一括出力を終了し、結果サマリーを表示する。"""
        if not self.queue_active:
            return
        was_stopped = self.output_queue.stop_requested
        self.queue_active = False
        self.output_queue.current_index = None
        counts = self.output_queue.summary()
        total = len(self.output_queue.items)
        self.progress_bar.setValue(100 if counts[STATUS_DONE] + counts[STATUS_ERROR] + counts[STATUS_CANCELLED] == total else 0)
        self._set_generating_state(False)
        self._update_queue_table()

        result = (
            f"一括出力を{'停止しました' if was_stopped else '完了しました'}。\n\n"
            f"完了: {counts[STATUS_DONE]}件\n"
            f"エラー: {counts[STATUS_ERROR]}件\n"
            f"中止: {counts[STATUS_CANCELLED]}件"
        )
        if counts[STATUS_ERROR]:
            self.status_label.setText(f"一括出力完了（{counts[STATUS_DONE]}件完了 / {counts[STATUS_ERROR]}件エラー）")
            self.status_label.setStyleSheet("color: #c50f1f; font-size: 12px; font-weight: bold;")
            QMessageBox.warning(self, "一括出力の結果", result)
        else:
            self.status_label.setText(f"一括出力完了（{counts[STATUS_DONE]}件）")
            self.status_label.setStyleSheet("color: #107c10; font-size: 12px; font-weight: bold;")
            QMessageBox.information(self, "一括出力の結果", result)
        self._log(result.replace("\n", " | "))

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

        # 通常の単体生成中は、別のワーカーを起動しないようキュー操作も止める。
        # 一括出力中は _set_queue_controls() がキュー用の状態を管理する。
        if generating and not self.queue_active:
            for button in (
                self.queue_add_projects_btn,
                self.queue_add_current_btn,
                self.queue_remove_btn,
                self.queue_up_btn,
                self.queue_down_btn,
                self.queue_clear_btn,
                self.queue_start_btn,
                self.queue_stop_btn,
            ):
                button.setEnabled(False)
        elif not self.queue_active:
            self._set_queue_controls()

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
