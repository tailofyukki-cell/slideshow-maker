# -*- coding: utf-8 -*-
"""
timing_parser.py
~~~~~~~~~~~~~~~~
複数画像モードにおける各画像の表示時間をJSONファイルから読み込み、
クリップごとの表示秒数リストを計算する。

ファイル命名規則:
  音声ファイル: 001.mp3
  タイミングJSON: 001_timing.json

JSONフォーマット:
  {
    "001_001.png": 10.0,
    "001_002.png": 15.0,
    "001_003.png": 5.0
  }

バリデーション:
  - 合計秒数が音声の長さと異なる場合 → 比率を保ちつつ正規化
  - 指定されていない画像がある場合 → 残り時間を均等分割
  - 合計が0以下の場合 → 均等分割にフォールバック
"""

from __future__ import annotations

import json
import os
import logging
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)


def find_timing_file(audio_path: str) -> Optional[str]:
    """
    音声ファイルのパスから対応するタイミングJSONファイルのパスを返す。
    存在しない場合は None を返す。

    例: /path/to/001.mp3 -> /path/to/001_timing.json
    """
    base = os.path.splitext(audio_path)[0]
    timing_path = base + "_timing.json"
    if os.path.isfile(timing_path):
        return timing_path
    return None


def load_timing_file(timing_path: str) -> Dict[str, float]:
    """
    タイミングJSONファイルを読み込み、{ファイル名: 秒数} の辞書を返す。
    ファイル名はベース名（パスなし）で正規化される。

    Raises:
        ValueError: JSONの形式が不正な場合
    """
    try:
        with open(timing_path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"タイミングJSONの解析に失敗しました: {e}")

    if not isinstance(raw, dict):
        raise ValueError("タイミングJSONはオブジェクト（辞書）形式である必要があります")

    result: Dict[str, float] = {}
    for key, val in raw.items():
        # キーはファイル名のみ（パスなし）に正規化
        filename = os.path.basename(key)
        try:
            seconds = float(val)
        except (TypeError, ValueError):
            raise ValueError(f"'{key}' の値 '{val}' は数値ではありません")
        if seconds <= 0:
            raise ValueError(f"'{key}' の表示時間 ({seconds}) は正の数値である必要があります")
        result[filename] = seconds

    return result


def calculate_clip_durations(
    visual_items: List[str],
    total_duration: float,
    timing_path: Optional[str],
) -> List[float]:
    """
    各ビジュアルアイテムの表示時間（秒）のリストを計算して返す。

    Parameters
    ----------
    visual_items : List[str]
        ビジュアルアイテムのファイルパスリスト（順番通り）
    total_duration : float
        音声の総再生時間（秒）
    timing_path : Optional[str]
        タイミングJSONファイルのパス。None の場合は均等分割。

    Returns
    -------
    List[float]
        各アイテムの表示時間（秒）のリスト。合計は total_duration に等しい。
    """
    n = len(visual_items)
    if n == 0:
        return []

    # タイミングJSONがない場合は均等分割
    if timing_path is None:
        equal = total_duration / n
        return [equal] * n

    # タイミングJSONを読み込む
    try:
        timing_map = load_timing_file(timing_path)
    except ValueError as e:
        logger.warning(f"タイミングJSONの読み込みに失敗しました（均等分割にフォールバック）: {e}")
        equal = total_duration / n
        return [equal] * n

    # 各アイテムに秒数を割り当て
    durations: List[Optional[float]] = []
    specified_total = 0.0
    unspecified_indices: List[int] = []

    for i, item_path in enumerate(visual_items):
        filename = os.path.basename(item_path)
        if filename in timing_map:
            dur = timing_map[filename]
            durations.append(dur)
            specified_total += dur
        else:
            durations.append(None)
            unspecified_indices.append(i)

    # 指定されていないアイテムに残り時間を均等分割
    if unspecified_indices:
        remaining = max(0.0, total_duration - specified_total)
        equal_remaining = remaining / len(unspecified_indices) if unspecified_indices else 0.0
        for i in unspecified_indices:
            durations[i] = max(0.1, equal_remaining)  # 最低0.1秒

    # 合計が0以下の場合は均等分割にフォールバック
    total_specified = sum(d for d in durations if d is not None)
    if total_specified <= 0:
        logger.warning("タイミングJSONの合計が0以下です。均等分割にフォールバックします。")
        equal = total_duration / n
        return [equal] * n

    # 合計を total_duration に正規化（比率を保持）
    scale = total_duration / total_specified
    normalized = [d * scale for d in durations]  # type: ignore

    # 浮動小数点誤差を最後のアイテムで吸収
    diff = total_duration - sum(normalized[:-1])
    normalized[-1] = max(0.1, diff)

    logger.debug(f"Clip durations: {[f'{d:.2f}s' for d in normalized]} (total={sum(normalized):.2f}s)")
    return normalized


def get_timing_summary(
    visual_items: List[str],
    total_duration: float,
    timing_path: Optional[str],
) -> str:
    """
    タイミング情報のサマリー文字列を返す（UI表示用）。

    Returns
    -------
    str
        例: "均等 (各10.0s)" または "JSON指定 (10s/15s/5s)"
    """
    n = len(visual_items)
    if n == 0:
        return ""

    if timing_path is None:
        equal = total_duration / n
        return f"均等 (各{equal:.1f}s)"

    try:
        durations = calculate_clip_durations(visual_items, total_duration, timing_path)
        parts = "/".join(f"{d:.1f}s" for d in durations)
        return f"JSON指定 ({parts})"
    except Exception:
        equal = total_duration / n
        return f"均等 (各{equal:.1f}s)"
