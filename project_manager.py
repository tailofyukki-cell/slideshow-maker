# -*- coding: utf-8 -*-
"""SlideshowMakerのプロジェクト保存・読込を扱うJSON管理モジュール。"""
import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, Optional


PROJECT_FILE_EXTENSION = ".slideshow.json"
PROJECT_FORMAT = "SlideshowMaker Project"
PROJECT_VERSION = 1

DEFAULT_PROJECT_SETTINGS: Dict[str, Any] = {
    "input_folder": "",
    "output_path": "",
    "preset_name": "",
    "ken_burns": False,
    "title_overlay": True,
    "visualizer_enabled": False,
    "visualizer_style": "waveform",
    "visualizer_height": 80,
    "visualizer_opacity_percent": 60,
    "visualizer_color_mode": "solid",
    "visualizer_color": "#00ffff",
    "bgm_enabled": False,
    "bgm_path": "",
    "voice_volume": 1.0,
    "bgm_volume": 0.5,
    "bgm_start_offset": 0.0,
    "bgm_fade_in": 1.0,
    "bgm_fade_out": 2.0,
    "loudness_normalization": False,
    "loudness_preset": "streaming",
    "loudness_target_lufs": -14.0,
    "loudness_true_peak": -1.5,
    "loudness_lra": 11.0,
}


class ProjectFileError(ValueError):
    """プロジェクトファイルの読込・検証中に発生するエラー。"""


def _is_within(path: str, parent: str) -> bool:
    """pathがparent配下にあるかを安全に判定する。"""
    try:
        absolute_path = os.path.abspath(path)
        absolute_parent = os.path.abspath(parent)
        return os.path.commonpath([absolute_path, absolute_parent]) == absolute_parent
    except ValueError:
        # Windowsで異なるドライブを比較した場合など
        return False


def _store_path(path: str, project_dir: str) -> str:
    """保存時に、プロジェクトファイル配下のパスを相対パスへ変換する。"""
    if not path:
        return ""
    absolute_path = os.path.abspath(os.path.expanduser(path))
    if _is_within(absolute_path, project_dir):
        return os.path.relpath(absolute_path, project_dir)
    return absolute_path


def _resolve_path(path: str, project_dir: str) -> str:
    """プロジェクトファイルの相対/絶対パスを現在の絶対パスに復元する。"""
    if not path:
        return ""
    expanded_path = os.path.expanduser(str(path))
    if os.path.isabs(expanded_path):
        return os.path.normpath(expanded_path)
    return os.path.normpath(os.path.abspath(os.path.join(project_dir, expanded_path)))


def _coerce_bool(value: Any, default: bool) -> bool:
    """JSON値をboolに安全に正規化する。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _coerce_number(
    value: Any, default: float, minimum: float, maximum: float, as_int: bool = False
):
    """JSONの数値を指定範囲内に正規化する。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    number = max(minimum, min(maximum, number))
    return int(round(number)) if as_int else number


def _normalise_settings(raw_settings: Any, project_dir: str) -> Dict[str, Any]:
    """プロジェクトJSONの設定値を検証・正規化して返す。"""
    if not isinstance(raw_settings, dict):
        raise ProjectFileError(
            "プロジェクトファイルの settings はJSONオブジェクトである必要があります。"
        )

    settings = deepcopy(DEFAULT_PROJECT_SETTINGS)

    for key in ("input_folder", "output_path", "bgm_path"):
        value = raw_settings.get(key, "")
        if value is not None and not isinstance(value, str):
            raise ProjectFileError(
                f"プロジェクト設定 '{key}' は文字列である必要があります。"
            )
        settings[key] = _resolve_path(value or "", project_dir)

    for key in (
        "preset_name",
        "visualizer_style",
        "visualizer_color_mode",
        "visualizer_color",
    ):
        value = raw_settings.get(key, settings[key])
        if isinstance(value, str):
            settings[key] = value

    for key in (
        "ken_burns",
        "title_overlay",
        "visualizer_enabled",
        "bgm_enabled",
        "loudness_normalization",
    ):
        settings[key] = _coerce_bool(raw_settings.get(key, settings[key]), settings[key])

    settings["visualizer_height"] = _coerce_number(
        raw_settings.get("visualizer_height", settings["visualizer_height"]),
        80,
        40,
        400,
        as_int=True,
    )
    settings["visualizer_opacity_percent"] = _coerce_number(
        raw_settings.get(
            "visualizer_opacity_percent", settings["visualizer_opacity_percent"]
        ),
        60,
        10,
        100,
        as_int=True,
    )
    settings["voice_volume"] = _coerce_number(
        raw_settings.get("voice_volume", settings["voice_volume"]), 1.0, 0.0, 2.0
    )
    settings["bgm_volume"] = _coerce_number(
        raw_settings.get("bgm_volume", settings["bgm_volume"]), 0.5, 0.0, 2.0
    )
    settings["bgm_start_offset"] = _coerce_number(
        raw_settings.get("bgm_start_offset", settings["bgm_start_offset"]),
        0.0,
        0.0,
        3600.0,
    )
    settings["bgm_fade_in"] = _coerce_number(
        raw_settings.get("bgm_fade_in", settings["bgm_fade_in"]), 1.0, 0.0, 30.0
    )
    settings["bgm_fade_out"] = _coerce_number(
        raw_settings.get("bgm_fade_out", settings["bgm_fade_out"]), 2.0, 0.0, 30.0
    )
    loudness_preset = raw_settings.get("loudness_preset", settings["loudness_preset"])
    if isinstance(loudness_preset, str):
        settings["loudness_preset"] = loudness_preset
    settings["loudness_target_lufs"] = _coerce_number(
        raw_settings.get("loudness_target_lufs", settings["loudness_target_lufs"]),
        -14.0, -30.0, -5.0,
    )
    settings["loudness_true_peak"] = _coerce_number(
        raw_settings.get("loudness_true_peak", settings["loudness_true_peak"]),
        -1.5, -9.0, 0.0,
    )
    settings["loudness_lra"] = _coerce_number(
        raw_settings.get("loudness_lra", settings["loudness_lra"]),
        11.0, 1.0, 50.0,
    )

    return settings


def make_project_payload(settings: Dict[str, Any], project_path: str) -> Dict[str, Any]:
    """UI設定から保存用のプロジェクトJSONデータを作成する。"""
    if not isinstance(settings, dict):
        raise ProjectFileError("保存する設定が不正です。")

    project_dir = os.path.dirname(os.path.abspath(project_path))
    stored_settings = deepcopy(DEFAULT_PROJECT_SETTINGS)
    for key in DEFAULT_PROJECT_SETTINGS:
        if key in settings:
            stored_settings[key] = settings[key]

    for key in ("input_folder", "output_path", "bgm_path"):
        stored_settings[key] = _store_path(str(stored_settings.get(key, "") or ""), project_dir)

    return {
        "format": PROJECT_FORMAT,
        "version": PROJECT_VERSION,
        "saved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "settings": stored_settings,
    }


def save_project_file(project_path: str, settings: Dict[str, Any]) -> str:
    """プロジェクトJSONをUTF-8で保存し、その絶対パスを返す。"""
    if not project_path:
        raise ProjectFileError("保存先が指定されていません。")

    path = os.path.abspath(os.path.expanduser(project_path))
    if not path.lower().endswith(PROJECT_FILE_EXTENSION):
        path += PROJECT_FILE_EXTENSION

    parent_dir = os.path.dirname(path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    payload = make_project_payload(settings, path)
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")
    except OSError as error:
        raise ProjectFileError(f"プロジェクトを保存できません: {error}") from error
    return path


def load_project_file(project_path: str) -> Dict[str, Any]:
    """プロジェクトJSONを読み込み、検証済みの設定辞書を返す。"""
    if not project_path:
        raise ProjectFileError("読込元が指定されていません。")

    path = os.path.abspath(os.path.expanduser(project_path))
    if not os.path.isfile(path):
        raise ProjectFileError(f"プロジェクトファイルが見つかりません: {path}")

    try:
        with open(path, "r", encoding="utf-8") as file:
            payload = json.load(file)
    except UnicodeDecodeError as error:
        raise ProjectFileError("プロジェクトファイルはUTF-8形式で保存してください。") from error
    except json.JSONDecodeError as error:
        raise ProjectFileError(
            f"プロジェクトファイルのJSON形式が不正です: {error.msg}"
        ) from error
    except OSError as error:
        raise ProjectFileError(f"プロジェクトを読み込めません: {error}") from error

    if not isinstance(payload, dict):
        raise ProjectFileError("プロジェクトファイルの最上位はJSONオブジェクトである必要があります。")
    if payload.get("format") != PROJECT_FORMAT:
        raise ProjectFileError("SlideshowMakerのプロジェクトファイルではありません。")

    version = payload.get("version")
    if not isinstance(version, int):
        raise ProjectFileError("プロジェクトファイルのバージョンが不正です。")
    if version > PROJECT_VERSION:
        raise ProjectFileError(
            f"このプロジェクトは新しいバージョン（v{version}）で保存されています。"
        )

    return _normalise_settings(payload.get("settings"), os.path.dirname(path))


def project_default_path(input_folder: str) -> Optional[str]:
    """入力フォルダ内に置く既定のプロジェクト保存先を返す。"""
    if not input_folder:
        return None
    folder = os.path.abspath(os.path.expanduser(input_folder))
    return os.path.join(folder, "slideshow_project" + PROJECT_FILE_EXTENSION)


def get_project_file_filter() -> str:
    """Qtファイルダイアログ用のプロジェクトファイルフィルタ。"""
    return "SlideshowMaker Project (*.slideshow.json);;JSON files (*.json)"
