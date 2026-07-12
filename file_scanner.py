# -*- coding: utf-8 -*-
"""
File scanner module - Detects audio/image/video pairs by matching base filenames

Supported audio formats:
    .mp3, .wav, .aac, .m4a, .flac, .ogg, .wma

Supported image formats:
    .jpg, .jpeg, .png, .gif (animated GIF included),
    .bmp, .tiff, .tif, .webp, .avif

Supported video formats (used as visual track, audio stripped):
    .mp4, .mov, .avi, .mkv, .webm, .flv, .wmv

Multi-image mode:
    If no exact-match visual file exists for an audio file, files named
    {base_name}_{001}.ext, {base_name}_{002}.ext, ... are collected as
    multiple visual items for that chapter.
    The audio duration is split equally among the visual items.
    Exact match always takes priority over suffix-based multi-image mode.

Priority when same base name exists in multiple visual formats:
    jpg=jpeg > png > webp > avif > bmp > tiff=tif > gif > (video formats)
"""
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple

# ========== 対応形式定義 ==========

AUDIO_EXTENSIONS = {
    '.mp3',
    '.wav',
    '.aac',
    '.m4a',
    '.flac',
    '.ogg',
    '.wma',
}

IMAGE_PRIORITY: Dict[str, int] = {
    '.jpg':  0,
    '.jpeg': 0,
    '.png':  1,
    '.webp': 2,
    '.avif': 3,
    '.bmp':  4,
    '.tiff': 5,
    '.tif':  5,
    '.gif':  6,
}

VIDEO_PRIORITY: Dict[str, int] = {
    '.mp4':  10,
    '.mov':  11,
    '.avi':  12,
    '.mkv':  13,
    '.webm': 14,
    '.flv':  15,
    '.wmv':  16,
}

VISUAL_PRIORITY: Dict[str, int] = {**IMAGE_PRIORITY, **VIDEO_PRIORITY}

AUDIO_FORMAT_NAMES: Dict[str, str] = {
    '.mp3':  'MP3',
    '.wav':  'WAV',
    '.aac':  'AAC',
    '.m4a':  'M4A',
    '.flac': 'FLAC',
    '.ogg':  'OGG',
    '.wma':  'WMA',
}

IMAGE_FORMAT_NAMES: Dict[str, str] = {
    '.jpg':  'JPEG',
    '.jpeg': 'JPEG',
    '.png':  'PNG',
    '.webp': 'WebP',
    '.avif': 'AVIF',
    '.bmp':  'BMP',
    '.tiff': 'TIFF',
    '.tif':  'TIFF',
    '.gif':  'GIF',
}

VIDEO_FORMAT_NAMES: Dict[str, str] = {
    '.mp4':  'MP4',
    '.mov':  'MOV',
    '.avi':  'AVI',
    '.mkv':  'MKV',
    '.webm': 'WebM',
    '.flv':  'FLV',
    '.wmv':  'WMV',
}

# サフィックスパターン: _001, _002, _01, _1 など（アンダースコア + 数字のみ）
_SUFFIX_RE = re.compile(r'^(.+)_(\d+)$')


@dataclass
class VisualItem:
    """複数画像チャプター内の1つの視覚素材"""
    path: str
    index: int                  # サフィックス番号（1始まり）
    is_animated_gif: bool = False

    @property
    def ext(self) -> str:
        return os.path.splitext(self.path)[1].lower()

    @property
    def is_video_input(self) -> bool:
        return self.ext in VIDEO_PRIORITY

    @property
    def format_name(self) -> str:
        ext = self.ext
        if ext in IMAGE_FORMAT_NAMES:
            return IMAGE_FORMAT_NAMES[ext]
        if ext in VIDEO_FORMAT_NAMES:
            return VIDEO_FORMAT_NAMES[ext]
        return ext.upper()


@dataclass
class FilePair:
    """音声ファイルと視覚素材（画像または動画）のペア

    single_mode=True  : 従来の1対1モード（image_path に単一ファイル）
    single_mode=False : 複数画像モード（visual_items にリスト）
    """
    base_name: str
    audio_path: Optional[str] = None
    image_path: Optional[str] = None       # single_mode 用
    is_animated_gif: bool = False          # single_mode 用
    visual_items: List[VisualItem] = field(default_factory=list)  # multi_mode 用

    @property
    def single_mode(self) -> bool:
        """True = 1対1モード、False = 複数画像モード"""
        return self.image_path is not None

    @property
    def is_complete(self) -> bool:
        if self.audio_path is None:
            return False
        if self.single_mode:
            return self.image_path is not None
        return len(self.visual_items) > 0

    @property
    def audio_only(self) -> bool:
        return self.audio_path is not None and not self.is_complete

    @property
    def image_only(self) -> bool:
        if self.audio_path is not None:
            return False
        if self.single_mode:
            return self.image_path is not None
        return len(self.visual_items) > 0

    @property
    def audio_ext(self) -> str:
        if self.audio_path:
            return os.path.splitext(self.audio_path)[1].lower()
        return ""

    @property
    def image_ext(self) -> str:
        """single_mode 時の視覚素材拡張子"""
        if self.image_path:
            return os.path.splitext(self.image_path)[1].lower()
        return ""

    @property
    def is_video_input(self) -> bool:
        """single_mode 時に視覚素材が動画かどうか"""
        return self.image_ext in VIDEO_PRIORITY

    @property
    def audio_format_name(self) -> str:
        return AUDIO_FORMAT_NAMES.get(self.audio_ext, self.audio_ext.upper())

    @property
    def image_format_name(self) -> str:
        ext = self.image_ext
        if ext in IMAGE_FORMAT_NAMES:
            return IMAGE_FORMAT_NAMES[ext]
        if ext in VIDEO_FORMAT_NAMES:
            return VIDEO_FORMAT_NAMES[ext]
        return ext.upper()

    @property
    def visual_count(self) -> int:
        """視覚素材の枚数（single_mode なら 1）"""
        if self.single_mode:
            return 1 if self.image_path else 0
        return len(self.visual_items)

    @property
    def status_text(self) -> str:
        if not self.is_complete:
            if self.audio_only:
                return f"⚠ 音声のみ [{self.audio_format_name}]（画像/動画なし）"
            if self.image_only:
                if self.single_mode:
                    return f"⚠ 画像/動画のみ [{self.image_format_name}]（音声なし）"
                fmts = "/".join(sorted({v.format_name for v in self.visual_items}))
                return f"⚠ 画像/動画のみ [{fmts}]（音声なし）"
            return "? 不明"

        if self.single_mode:
            if self.is_animated_gif:
                tag = " [アニメGIF]"
            elif self.is_video_input:
                tag = " [動画]"
            else:
                tag = ""
            return f"✓ ペア成立 [{self.audio_format_name} + {self.image_format_name}]{tag}"
        else:
            fmts = "/".join(sorted({v.format_name for v in self.visual_items}))
            return (
                f"✓ ペア成立 [{self.audio_format_name} + {fmts}] "
                f"[複数画像: {len(self.visual_items)}枚]"
            )


def _check_animated_gif(path: str) -> bool:
    """GIFファイルがアニメーションかどうかを判定する"""
    try:
        with open(path, 'rb') as f:
            data = f.read(1024 * 64)
        if not data.startswith(b'GIF89a'):
            return False
        if b'NETSCAPE2.0' in data:
            return True
        return data.count(b'\x21\xF9\x04') > 1
    except Exception:
        return False


@dataclass
class ScanResult:
    """スキャン結果"""
    complete_pairs: List[FilePair] = field(default_factory=list)
    audio_only: List[FilePair] = field(default_factory=list)
    image_only: List[FilePair] = field(default_factory=list)
    folder_path: str = ""

    @property
    def all_pairs(self) -> List[FilePair]:
        all_items = self.complete_pairs + self.audio_only + self.image_only
        return sorted(all_items, key=lambda p: p.base_name)

    @property
    def has_complete_pairs(self) -> bool:
        return len(self.complete_pairs) > 0

    @property
    def summary(self) -> str:
        gif_count = sum(1 for p in self.complete_pairs
                        if p.single_mode and p.is_animated_gif)
        vid_count = sum(1 for p in self.complete_pairs
                        if p.single_mode and p.is_video_input)
        multi_count = sum(1 for p in self.complete_pairs if not p.single_mode)
        notes = []
        if multi_count > 0:
            notes.append(f"複数画像: {multi_count}件")
        if gif_count > 0:
            notes.append(f"アニメGIF: {gif_count}件")
        if vid_count > 0:
            notes.append(f"動画: {vid_count}件")
        note_str = f" ({', '.join(notes)})" if notes else ""
        return (
            f"完全ペア: {len(self.complete_pairs)}件{note_str} / "
            f"音声のみ: {len(self.audio_only)}件 / "
            f"画像/動画のみ: {len(self.image_only)}件"
        )

    @property
    def audio_format_stats(self) -> str:
        from collections import Counter
        counts = Counter(
            p.audio_format_name for p in self.complete_pairs + self.audio_only
            if p.audio_path
        )
        return ", ".join(f"{fmt}:{n}" for fmt, n in sorted(counts.items()))

    @property
    def image_format_stats(self) -> str:
        from collections import Counter
        counts: Counter = Counter()
        for p in self.complete_pairs + self.image_only:
            if p.single_mode and p.image_path:
                counts[p.image_format_name] += 1
            else:
                for v in p.visual_items:
                    counts[v.format_name] += 1
        return ", ".join(f"{fmt}:{n}" for fmt, n in sorted(counts.items()))


def scan_folder(folder_path: str) -> ScanResult:
    """
    指定フォルダをスキャンしてファイルペアを検出する

    ペア検出ルール:
      1. 完全一致: {base}.mp3 + {base}.jpg など → 従来の1対1モード（優先）
      2. サフィックス: {base}.mp3 + {base}_001.png + {base}_002.jpg など
         → 完全一致する視覚素材が存在しない場合のみ複数画像モードを適用

    Args:
        folder_path: スキャン対象フォルダのパス

    Returns:
        ScanResult

    Raises:
        FileNotFoundError, NotADirectoryError, PermissionError
    """
    if not os.path.exists(folder_path):
        raise FileNotFoundError(f"フォルダが見つかりません: {folder_path}")
    if not os.path.isdir(folder_path):
        raise NotADirectoryError(f"フォルダではありません: {folder_path}")

    try:
        entries = os.listdir(folder_path)
    except PermissionError:
        raise PermissionError(f"フォルダにアクセスできません: {folder_path}")

    # --- ファイルを分類 ---
    # audio_files:  base_name -> path
    # visual_exact: base_name -> (path, priority)  完全一致の視覚素材
    # visual_multi: base_name -> {suffix_num -> (path, priority)}  サフィックス付き視覚素材

    audio_files: Dict[str, str] = {}
    visual_exact: Dict[str, Tuple[str, int]] = {}
    visual_multi: Dict[str, Dict[int, Tuple[str, int]]] = {}

    # BGMファイル名として認識するベース名（スキャン対象から除外）
    BGM_BASE_NAMES = {'_bgm', '_BGM', 'bgm', 'BGM'}

    for entry in entries:
        full_path = os.path.join(folder_path, entry)
        if not os.path.isfile(full_path):
            continue

        name, ext = os.path.splitext(entry)
        ext_lower = ext.lower()

        # BGMファイルはチャプターペアの対象外にする
        if name in BGM_BASE_NAMES:
            continue

        if ext_lower in AUDIO_EXTENSIONS:
            if name not in audio_files:
                audio_files[name] = full_path
            else:
                existing_ext = os.path.splitext(audio_files[name])[1].lower()
                if ext_lower < existing_ext:
                    audio_files[name] = full_path

        elif ext_lower in VISUAL_PRIORITY:
            priority = VISUAL_PRIORITY[ext_lower]

            # サフィックスパターンか確認
            m = _SUFFIX_RE.match(name)
            if m:
                parent_base = m.group(1)
                suffix_num = int(m.group(2))
                if parent_base not in visual_multi:
                    visual_multi[parent_base] = {}
                existing = visual_multi[parent_base].get(suffix_num)
                if existing is None or priority < existing[1]:
                    visual_multi[parent_base][suffix_num] = (full_path, priority)
            else:
                # 完全一致の視覚素材
                if name not in visual_exact or priority < visual_exact[name][1]:
                    visual_exact[name] = (full_path, priority)

    # --- ペアを構築 ---
    all_base_names = (
        set(audio_files.keys())
        | set(visual_exact.keys())
        | set(visual_multi.keys())
    )
    result = ScanResult(folder_path=folder_path)

    for base_name in sorted(all_base_names):
        audio_path = audio_files.get(base_name)

        # 完全一致の視覚素材が存在するか
        if base_name in visual_exact:
            vis_path = visual_exact[base_name][0]
            animated = False
            if vis_path.lower().endswith('.gif'):
                animated = _check_animated_gif(vis_path)
            pair = FilePair(
                base_name=base_name,
                audio_path=audio_path,
                image_path=vis_path,
                is_animated_gif=animated,
            )
        elif base_name in visual_multi and audio_path is not None:
            # 完全一致なし + 音声あり + サフィックス付き視覚素材あり → 複数画像モード
            suffix_dict = visual_multi[base_name]
            sorted_items = sorted(suffix_dict.items(), key=lambda x: x[0])
            visual_items = []
            for idx, (path, _) in sorted_items:
                animated = False
                if path.lower().endswith('.gif'):
                    animated = _check_animated_gif(path)
                visual_items.append(VisualItem(
                    path=path,
                    index=idx,
                    is_animated_gif=animated,
                ))
            pair = FilePair(
                base_name=base_name,
                audio_path=audio_path,
                visual_items=visual_items,
            )
        elif base_name in visual_multi and audio_path is None:
            # 音声なし + サフィックス付き視覚素材のみ → image_only
            suffix_dict = visual_multi[base_name]
            sorted_items = sorted(suffix_dict.items(), key=lambda x: x[0])
            visual_items = []
            for idx, (path, _) in sorted_items:
                animated = False
                if path.lower().endswith('.gif'):
                    animated = _check_animated_gif(path)
                visual_items.append(VisualItem(
                    path=path,
                    index=idx,
                    is_animated_gif=animated,
                ))
            pair = FilePair(
                base_name=base_name,
                audio_path=None,
                visual_items=visual_items,
            )
        else:
            # 音声のみ
            pair = FilePair(
                base_name=base_name,
                audio_path=audio_path,
            )

        if pair.is_complete:
            result.complete_pairs.append(pair)
        elif pair.audio_only:
            result.audio_only.append(pair)
        elif pair.image_only:
            result.image_only.append(pair)

    result.complete_pairs.sort(key=lambda p: p.base_name)
    result.audio_only.sort(key=lambda p: p.base_name)
    result.image_only.sort(key=lambda p: p.base_name)

    return result
