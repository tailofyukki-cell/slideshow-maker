# -*- coding: utf-8 -*-
"""SlideshowMakerの一括出力キューを扱うコアロジック。"""
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from file_scanner import scan_folder
from project_manager import load_project_file
from video_generator import (
    DEFAULT_PRESET,
    OUTPUT_FILENAME,
    RESOLUTION_PRESETS,
    GenerationConfig,
    find_folder_bgm,
)


STATUS_WAITING = "待機"
STATUS_RUNNING = "生成中"
STATUS_DONE = "完了"
STATUS_ERROR = "エラー"
STATUS_CANCELLED = "中止"


class QueueItemError(ValueError):
    """キュー項目の準備または検証中に発生するエラー。"""


@dataclass
class QueueItem:
    """キューに登録する1件のプロジェクト。"""
    project_path: str
    settings: Dict[str, object]
    display_name: str = ""
    status: str = STATUS_WAITING
    message: str = ""
    output_path: str = ""

    def __post_init__(self):
        self.project_path = os.path.abspath(self.project_path) if self.project_path else ""
        if not self.display_name:
            self.display_name = os.path.basename(self.project_path) or "未保存の設定"
        self.output_path = str(self.settings.get("output_path", "") or "")

    @classmethod
    def from_project_file(cls, project_path: str) -> "QueueItem":
        """保存済みプロジェクトを読み込み、待機中のキュー項目として生成する。"""
        path = os.path.abspath(project_path)
        settings = load_project_file(path)
        return cls(project_path=path, settings=settings, display_name=os.path.basename(path))

    @classmethod
    def from_settings(cls, settings: Dict[str, object], display_name: str = "現在の設定") -> "QueueItem":
        """現在のGUI設定のスナップショットをキュー項目として生成する。"""
        return cls(project_path="", settings=dict(settings), display_name=display_name)

    def reset(self):
        """再実行できるよう、項目の実行結果を待機状態に戻す。"""
        self.status = STATUS_WAITING
        self.message = ""


@dataclass
class PreparedQueueJob:
    """生成開始直前まで検証・変換済みのキュー項目。"""
    item: QueueItem
    config: GenerationConfig
    chapter_count: int


def prepare_queue_job(item: QueueItem) -> PreparedQueueJob:
    """キュー項目の設定を検証し、GenerationConfigへ変換する。"""
    settings = item.settings
    input_folder = str(settings.get("input_folder", "") or "").strip()
    if not input_folder:
        raise QueueItemError("入力フォルダが指定されていません。")
    if not os.path.isdir(input_folder):
        raise QueueItemError(f"入力フォルダが見つかりません: {input_folder}")

    try:
        scan_result = scan_folder(input_folder)
    except Exception as error:
        raise QueueItemError(f"入力フォルダをスキャンできません: {error}") from error

    if not scan_result.has_complete_pairs:
        raise QueueItemError("完全なペア（音声+画像/動画）が見つかりません。")

    output_path = str(settings.get("output_path", "") or "").strip()
    if not output_path:
        output_path = os.path.join(input_folder, OUTPUT_FILENAME)
    output_path = os.path.abspath(output_path)
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.isdir(output_dir):
        raise QueueItemError(f"出力先フォルダが見つかりません: {output_dir}")

    preset_name = str(settings.get("preset_name", "") or "")
    if preset_name not in RESOLUTION_PRESETS:
        preset_name = DEFAULT_PRESET
    width, height = RESOLUTION_PRESETS[preset_name]

    bgm_enabled = bool(settings.get("bgm_enabled", False))
    bgm_path = str(settings.get("bgm_path", "") or "").strip()
    if bgm_enabled and not bgm_path:
        bgm_path = find_folder_bgm(input_folder) or ""
    if bgm_enabled and not bgm_path:
        raise QueueItemError("BGMが有効ですが、BGMファイルが指定されていません。")
    if bgm_enabled and not os.path.isfile(bgm_path):
        raise QueueItemError(f"BGMファイルが見つかりません: {bgm_path}")

    config = GenerationConfig(
        pairs=scan_result.complete_pairs,
        output_path=output_path,
        width=width,
        height=height,
        title_overlay=bool(settings.get("title_overlay", True)),
        ken_burns=bool(settings.get("ken_burns", False)),
        visualizer_enabled=bool(settings.get("visualizer_enabled", False)),
        visualizer_style=str(settings.get("visualizer_style", "waveform") or "waveform"),
        visualizer_height=int(settings.get("visualizer_height", 80)),
        visualizer_opacity=float(settings.get("visualizer_opacity_percent", 60)) / 100.0,
        visualizer_color_mode=str(settings.get("visualizer_color_mode", "solid") or "solid"),
        visualizer_color=str(settings.get("visualizer_color", "#00ffff") or "#00ffff"),
        bgm_path=bgm_path if bgm_enabled else None,
        voice_volume=float(settings.get("voice_volume", 1.0)),
        bgm_volume=float(settings.get("bgm_volume", 0.5)),
        bgm_start_offset=float(settings.get("bgm_start_offset", 0.0)),
        bgm_fade_in=float(settings.get("bgm_fade_in", 1.0)),
        bgm_fade_out=float(settings.get("bgm_fade_out", 2.0)),
    )
    item.output_path = output_path
    return PreparedQueueJob(
        item=item,
        config=config,
        chapter_count=len(scan_result.complete_pairs),
    )


class OutputQueue:
    """順次実行するキュー項目のコンテナ。UIに依存しない状態管理を提供する。"""

    def __init__(self):
        self.items: List[QueueItem] = []
        self.current_index: Optional[int] = None
        self.stop_requested = False

    def add_project_files(self, project_paths: List[str]) -> List[QueueItem]:
        """複数のプロジェクトファイルを読み込んで末尾に追加する。"""
        added = []
        existing_paths = {item.project_path for item in self.items if item.project_path}
        for path in project_paths:
            absolute_path = os.path.abspath(path)
            if absolute_path in existing_paths:
                continue
            item = QueueItem.from_project_file(absolute_path)
            self.items.append(item)
            added.append(item)
            existing_paths.add(absolute_path)
        return added

    def add_settings_snapshot(self, settings: Dict[str, object], display_name: str = "現在の設定") -> QueueItem:
        """現在のGUI設定のスナップショットを末尾へ追加する。"""
        item = QueueItem.from_settings(settings, display_name)
        self.items.append(item)
        return item

    def remove_at(self, index: int) -> QueueItem:
        """指定位置の項目を削除する。生成中の項目は削除できない。"""
        if not 0 <= index < len(self.items):
            raise IndexError("キュー項目の位置が不正です。")
        if self.current_index == index:
            raise QueueItemError("生成中のキュー項目は削除できません。")
        return self.items.pop(index)

    def move(self, index: int, direction: int) -> bool:
        """項目を上下へ移動する。移動した場合はTrueを返す。"""
        target = index + direction
        if not (0 <= index < len(self.items) and 0 <= target < len(self.items)):
            return False
        if self.current_index is not None:
            return False
        self.items[index], self.items[target] = self.items[target], self.items[index]
        return True

    def clear_waiting(self):
        """待機・完了・エラー・中止の項目を削除する。生成中の項目は維持する。"""
        self.items = [item for item in self.items if item.status == STATUS_RUNNING]
        self.current_index = 0 if self.items else None

    def reset_for_run(self):
        """新しい一括出力の開始前に停止要求を解除し、過去の結果を待機へ戻す。"""
        self.stop_requested = False
        self.current_index = None
        for item in self.items:
            item.reset()

    def request_stop(self):
        """現在の処理後に新しい項目を開始しないよう停止要求を設定する。"""
        self.stop_requested = True

    def next_waiting_index(self) -> Optional[int]:
        """次に実行する待機項目のインデックスを返す。"""
        if self.stop_requested:
            return None
        start = 0 if self.current_index is None else self.current_index + 1
        for index in range(start, len(self.items)):
            if self.items[index].status == STATUS_WAITING:
                return index
        return None

    @property
    def is_running(self) -> bool:
        """いずれかの項目を実行中かを返す。"""
        return self.current_index is not None and 0 <= self.current_index < len(self.items) and self.items[self.current_index].status == STATUS_RUNNING

    def summary(self) -> Dict[str, int]:
        """状態別の件数を返す。"""
        counts = {
            STATUS_WAITING: 0,
            STATUS_RUNNING: 0,
            STATUS_DONE: 0,
            STATUS_ERROR: 0,
            STATUS_CANCELLED: 0,
        }
        for item in self.items:
            counts[item.status] = counts.get(item.status, 0) + 1
        return counts
