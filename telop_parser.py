# -*- coding: utf-8 -*-
"""
telop_parser.py - Telop (caption/onomatopoeia) definition file loader

File format: JSON array placed alongside the audio file.
  audio file : 001.mp3
  telop file : 001.json

Example 001.json:
[
  {
    "text": "ドカーン！",
    "start": 1.0,
    "end": 2.5,
    "position": "center",
    "size": 80,
    "color": "yellow",
    "bold": true,
    "animation": "fade"
  },
  {
    "text": "BGMが流れる...",
    "start": 3.0,
    "end": 5.0,
    "position": "bottom",
    "size": 48,
    "color": "white",
    "bg": true,
    "animation": "slide_left",
    "anim_duration": 0.4
  },
  {
    "text": "タイプライター",
    "start": 6.0,
    "end": 10.0,
    "position": "top",
    "size": 60,
    "color": "cyan",
    "animation": {
      "type": "typewriter",
      "chars_per_sec": 6
    }
  },
  {
    "text": "ズームイン！",
    "start": 11.0,
    "end": 14.0,
    "position": "center",
    "size": 70,
    "color": "white",
    "animation": {
      "type": "zoom_in",
      "in_duration": 0.4
    }
  },
  {
    "text": "組み合わせ",
    "start": 15.0,
    "end": 19.0,
    "position": "bottom",
    "size": 60,
    "color": "white",
    "bg": true,
    "animation": [
      {"type": "slide_right", "in_duration": 0.5},
      {"type": "fade_out",    "out_duration": 0.4}
    ]
  }
]

Optional global settings (add as first element with "__settings__": true):
{
  "__settings__": true,
  "fontfile": "C:/Windows/Fonts/YuGothB.ttc"
}

Supported position values:
  top, center, bottom,
  top-left, top-right, bottom-left, bottom-right

Supported animation values (Phase 1 + Phase 2):
  none              : アニメーションなし（デフォルト）
  fade              : フェードイン + フェードアウト
  fade_in           : フェードインのみ
  fade_out          : フェードアウトのみ
  slide_left        : 左からスライドイン
  slide_right       : 右からスライドイン
  slide_top         : 上からスライドイン
  slide_bottom      : 下からスライドイン
  slide_left_fade   : 左スライドイン + フェードアウト
  slide_right_fade  : 右スライドイン + フェードアウト
  blink             : 点滅
  shake             : 横揺れ
  bounce            : バウンス
  zoom_in           : 小さい文字から拡大しながら出現 (Phase 2)
  zoom_out          : 大きい文字から縮小しながら出現 (Phase 2)
  pop               : ポップアップ（オーバーシュートあり） (Phase 2)
  typewriter        : 1文字ずつ表示 (Phase 2)

Animation can also be specified as:
  - A string: "fade"
  - An object: {"type": "fade", "in_duration": 0.3, "out_duration": 0.3}
  - An array:  [{"type": "slide_left"}, {"type": "fade_out", "out_duration": 0.3}]
    (combination; typewriter cannot be combined)

Animation parameters (optional):
  anim_duration : イン/アウトのアニメーション時間（秒）。デフォルト 0.5
  blink_freq    : blink の点滅周波数（Hz）。デフォルト 3.0
  shake_freq    : shake の揺れ周波数（Hz）。デフォルト 8.0
  shake_amp     : shake の振れ幅（px）。デフォルト 15
  bounce_freq   : bounce の周波数（Hz）。デフォルト 3.0
  bounce_amp    : bounce の振れ幅（px）。デフォルト 40
  chars_per_sec : typewriter の文字表示速度（文字/秒）。デフォルト 8
  pop_overshoot : pop のオーバーシュート倍率（デフォルト 1.3）

All parameters except text/start/end are optional.
"""
import os
import json
import math
from dataclasses import dataclass, field
from typing import List, Optional, Union

# ---- デフォルト値 ----
DEFAULT_FONT_SIZE      = 60
DEFAULT_COLOR          = "white"
DEFAULT_POSITION       = "bottom"
DEFAULT_OUTLINE        = True
DEFAULT_OUTLINE_COLOR  = "black"
DEFAULT_BOLD           = False
DEFAULT_BG             = False
DEFAULT_ANIMATION      = "none"
DEFAULT_ANIM_DURATION  = 0.5
DEFAULT_BLINK_FREQ     = 3.0
DEFAULT_SHAKE_FREQ     = 8.0
DEFAULT_SHAKE_AMP      = 15
DEFAULT_BOUNCE_FREQ    = 3.0
DEFAULT_BOUNCE_AMP     = 40
DEFAULT_CHARS_PER_SEC  = 8
DEFAULT_POP_OVERSHOOT  = 1.3

VALID_POSITIONS = {
    "top", "center", "bottom",
    "top-left", "top-right",
    "bottom-left", "bottom-right",
}

# Phase 1 + Phase 2 の全アニメーション
VALID_ANIMATIONS = {
    "none",
    "fade", "fade_in", "fade_out",
    "slide_left", "slide_right", "slide_top", "slide_bottom",
    "slide_left_fade", "slide_right_fade",
    "blink", "shake", "bounce",
    # Phase 2
    "zoom_in", "zoom_out", "pop",
    "typewriter",
}

# typewriter は組み合わせ不可
COMBO_INCOMPATIBLE = {"typewriter"}

PI = math.pi

# ---- Windows 日本語フォント候補（優先順） ----
WINDOWS_JP_FONTS = [
    r"C:\Windows\Fonts\YuGothB.ttc",
    r"C:\Windows\Fonts\YuGothM.ttc",
    r"C:\Windows\Fonts\yugothb.ttc",
    r"C:\Windows\Fonts\yugothm.ttc",
    r"C:\Windows\Fonts\meiryo.ttc",
    r"C:\Windows\Fonts\meiryob.ttc",
    r"C:\Windows\Fonts\msgothic.ttc",
    r"C:\Windows\Fonts\msmincho.ttc",
    r"C:\Windows\Fonts\NotoSansCJK-Regular.ttc",
]


def find_windows_jp_font() -> Optional[str]:
    """Windows 環境で利用可能な日本語フォントを自動検索して返す。"""
    for path in WINDOWS_JP_FONTS:
        if os.path.isfile(path):
            return path
    return None


# ============================================================
# アニメーション仕様オブジェクト
# ============================================================

@dataclass
class AnimSpec:
    """1つのアニメーション仕様（type + パラメータ）"""
    anim_type: str
    in_duration: float  = DEFAULT_ANIM_DURATION
    out_duration: float = DEFAULT_ANIM_DURATION
    # typewriter
    chars_per_sec: float = DEFAULT_CHARS_PER_SEC
    # pop
    pop_overshoot: float = DEFAULT_POP_OVERSHOOT


def _parse_anim_spec(raw, entry_index: int, default_dur: float) -> List[AnimSpec]:
    """
    "animation" フィールドの値をパースして AnimSpec のリストを返す。
    - 文字列: "fade" → [AnimSpec("fade")]
    - オブジェクト: {"type": "fade", ...} → [AnimSpec("fade", ...)]
    - 配列: [{"type": "slide_left"}, {"type": "fade_out"}] → [AnimSpec(...), AnimSpec(...)]
    """
    if raw is None or raw == "none":
        return [AnimSpec("none")]

    if isinstance(raw, str):
        anim_type = raw.lower()
        if anim_type not in VALID_ANIMATIONS:
            raise ValueError(
                f"テロップ定義 #{entry_index}: 'animation' の値 '{anim_type}' は無効です。"
                f"有効な値: {sorted(VALID_ANIMATIONS)}"
            )
        return [AnimSpec(anim_type, in_duration=default_dur, out_duration=default_dur)]

    if isinstance(raw, dict):
        return [_parse_single_anim_obj(raw, entry_index, default_dur)]

    if isinstance(raw, list):
        if len(raw) == 0:
            return [AnimSpec("none")]
        specs = []
        for item in raw:
            if not isinstance(item, dict):
                raise ValueError(
                    f"テロップ定義 #{entry_index}: 'animation' 配列の要素はオブジェクトである必要があります"
                )
            specs.append(_parse_single_anim_obj(item, entry_index, default_dur))
        # typewriter は組み合わせ不可
        for sp in specs:
            if sp.anim_type in COMBO_INCOMPATIBLE:
                raise ValueError(
                    f"テロップ定義 #{entry_index}: '{sp.anim_type}' は他のアニメーションと組み合わせできません"
                )
        return specs

    raise ValueError(
        f"テロップ定義 #{entry_index}: 'animation' の形式が不正です（文字列・オブジェクト・配列のいずれかで指定してください）"
    )


def _parse_single_anim_obj(obj: dict, entry_index: int, default_dur: float) -> AnimSpec:
    """アニメーションオブジェクト1つをパースして AnimSpec を返す"""
    if 'type' not in obj:
        raise ValueError(f"テロップ定義 #{entry_index}: animation オブジェクトに 'type' が必要です")
    anim_type = str(obj['type']).lower()
    if anim_type not in VALID_ANIMATIONS:
        raise ValueError(
            f"テロップ定義 #{entry_index}: animation type '{anim_type}' は無効です。"
            f"有効な値: {sorted(VALID_ANIMATIONS)}"
        )
    try:
        in_dur = float(obj.get('in_duration', default_dur))
    except (TypeError, ValueError):
        in_dur = default_dur
    try:
        out_dur = float(obj.get('out_duration', default_dur))
    except (TypeError, ValueError):
        out_dur = default_dur
    try:
        cps = float(obj.get('chars_per_sec', DEFAULT_CHARS_PER_SEC))
    except (TypeError, ValueError):
        cps = DEFAULT_CHARS_PER_SEC
    try:
        overshoot = float(obj.get('pop_overshoot', DEFAULT_POP_OVERSHOOT))
    except (TypeError, ValueError):
        overshoot = DEFAULT_POP_OVERSHOOT

    return AnimSpec(
        anim_type=anim_type,
        in_duration=max(0.05, min(in_dur, 3.0)),
        out_duration=max(0.05, min(out_dur, 3.0)),
        chars_per_sec=max(0.5, cps),
        pop_overshoot=max(1.0, overshoot),
    )


# ============================================================
# TelopEntry
# ============================================================

@dataclass
class TelopEntry:
    """1つのテロップエントリ"""
    text: str
    start: float
    end: float
    position: str            = DEFAULT_POSITION
    size: int                = DEFAULT_FONT_SIZE
    color: str               = DEFAULT_COLOR
    bold: bool               = DEFAULT_BOLD
    outline: bool            = DEFAULT_OUTLINE
    outline_color: str       = DEFAULT_OUTLINE_COLOR
    bg: bool                 = DEFAULT_BG
    fontfile: Optional[str]  = None
    # Phase 1 互換パラメータ（AnimSpec に移行済みだが後方互換のために保持）
    animation: str           = DEFAULT_ANIMATION
    anim_duration: float     = DEFAULT_ANIM_DURATION
    blink_freq: float        = DEFAULT_BLINK_FREQ
    shake_freq: float        = DEFAULT_SHAKE_FREQ
    shake_amp: int           = DEFAULT_SHAKE_AMP
    bounce_freq: float       = DEFAULT_BOUNCE_FREQ
    bounce_amp: int          = DEFAULT_BOUNCE_AMP
    # Phase 2
    anim_specs: List[AnimSpec] = field(default_factory=lambda: [AnimSpec("none")])

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


def load_telop_file(json_path: str) -> List[TelopEntry]:
    """
    テロップ定義JSONファイルを読み込んでTelopEntryのリストを返す。
    ファイルが存在しない場合は空リストを返す。
    """
    if not os.path.isfile(json_path):
        return []

    with open(json_path, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"テロップファイルのJSON解析に失敗しました: {json_path}\n{e}")

    if not isinstance(data, list):
        raise ValueError(
            f"テロップファイルはJSON配列形式である必要があります: {json_path}"
        )

    # グローバル設定の抽出
    global_fontfile: Optional[str] = None
    items = list(data)
    if items and isinstance(items[0], dict) and items[0].get('__settings__'):
        settings = items.pop(0)
        global_fontfile = settings.get('fontfile', None)

    entries = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"テロップ定義 #{i+1} がオブジェクトではありません")

        # 必須フィールド
        if 'text' not in item:
            raise ValueError(f"テロップ定義 #{i+1}: 'text' が必須です")
        if 'start' not in item:
            raise ValueError(f"テロップ定義 #{i+1}: 'start' が必須です")
        if 'end' not in item:
            raise ValueError(f"テロップ定義 #{i+1}: 'end' が必須です")

        text = str(item['text'])
        if not text.strip():
            raise ValueError(f"テロップ定義 #{i+1}: 'text' が空です")

        try:
            start = float(item['start'])
            end   = float(item['end'])
        except (TypeError, ValueError):
            raise ValueError(f"テロップ定義 #{i+1}: 'start'/'end' は数値で指定してください")

        if start < 0:
            raise ValueError(f"テロップ定義 #{i+1}: 'start' は 0 以上にしてください")
        if end <= start:
            raise ValueError(
                f"テロップ定義 #{i+1}: 'end' ({end}) は 'start' ({start}) より大きくしてください"
            )

        position = str(item.get('position', DEFAULT_POSITION)).lower()
        if position not in VALID_POSITIONS:
            raise ValueError(
                f"テロップ定義 #{i+1}: 'position' の値 '{position}' は無効です。"
                f"有効な値: {sorted(VALID_POSITIONS)}"
            )

        try:
            size = int(item.get('size', DEFAULT_FONT_SIZE))
        except (TypeError, ValueError):
            raise ValueError(f"テロップ定義 #{i+1}: 'size' は整数で指定してください")
        if size < 8 or size > 500:
            raise ValueError(f"テロップ定義 #{i+1}: 'size' は 8〜500 の範囲で指定してください")

        # animation フィールドのパース（Phase 2: 文字列/オブジェクト/配列に対応）
        raw_anim = item.get('animation', DEFAULT_ANIMATION)
        try:
            anim_duration = float(item.get('anim_duration', DEFAULT_ANIM_DURATION))
        except (TypeError, ValueError):
            anim_duration = DEFAULT_ANIM_DURATION
        anim_duration = max(0.05, min(anim_duration, 3.0))

        anim_specs = _parse_anim_spec(raw_anim, i + 1, anim_duration)

        # Phase 1 互換: animation 文字列（先頭 spec の type）
        animation_compat = anim_specs[0].anim_type if anim_specs else "none"

        color         = str(item.get('color', DEFAULT_COLOR))
        bold          = bool(item.get('bold', DEFAULT_BOLD))
        outline       = bool(item.get('outline', DEFAULT_OUTLINE))
        outline_color = str(item.get('outline_color', DEFAULT_OUTLINE_COLOR))
        bg            = bool(item.get('bg', DEFAULT_BG))
        entry_fontfile = item.get('fontfile', global_fontfile)

        # アニメーション固有パラメータ（Phase 1 互換）
        try:
            blink_freq = float(item.get('blink_freq', DEFAULT_BLINK_FREQ))
        except (TypeError, ValueError):
            blink_freq = DEFAULT_BLINK_FREQ

        try:
            shake_freq = float(item.get('shake_freq', DEFAULT_SHAKE_FREQ))
        except (TypeError, ValueError):
            shake_freq = DEFAULT_SHAKE_FREQ

        try:
            shake_amp = int(item.get('shake_amp', DEFAULT_SHAKE_AMP))
        except (TypeError, ValueError):
            shake_amp = DEFAULT_SHAKE_AMP

        try:
            bounce_freq = float(item.get('bounce_freq', DEFAULT_BOUNCE_FREQ))
        except (TypeError, ValueError):
            bounce_freq = DEFAULT_BOUNCE_FREQ

        try:
            bounce_amp = int(item.get('bounce_amp', DEFAULT_BOUNCE_AMP))
        except (TypeError, ValueError):
            bounce_amp = DEFAULT_BOUNCE_AMP

        entries.append(TelopEntry(
            text=text,
            start=start,
            end=end,
            position=position,
            size=size,
            color=color,
            bold=bold,
            outline=outline,
            outline_color=outline_color,
            bg=bg,
            fontfile=entry_fontfile,
            animation=animation_compat,
            anim_duration=anim_duration,
            blink_freq=blink_freq,
            shake_freq=shake_freq,
            shake_amp=shake_amp,
            bounce_freq=bounce_freq,
            bounce_amp=bounce_amp,
            anim_specs=anim_specs,
        ))

    return entries


def find_telop_file(audio_path: str) -> Optional[str]:
    """音声ファイルと同名の .json テロップファイルのパスを返す。"""
    base = os.path.splitext(audio_path)[0]
    candidate = base + '.json'
    return candidate if os.path.isfile(candidate) else None


# ============================================================
# アニメーション式生成ヘルパー
# ============================================================

def _esc_comma(expr: str) -> str:
    """FFmpeg フィルタ式内のカンマを \\, でエスケープする"""
    return expr.replace(',', r'\,')


def _build_alpha_expr(anim_type: str, t0: float, t1: float,
                      in_dur: float, out_dur: float) -> Optional[str]:
    """
    alpha 式を生成する。None を返した場合は alpha パラメータを付与しない。
    """
    in_end  = t0 + in_dur
    out_beg = t1 - out_dur

    if anim_type == "fade":
        if out_beg <= in_end:
            mid = (t0 + t1) / 2
            return (
                f"if(lt(t,{t0:.3f}),0,"
                f"if(lt(t,{mid:.3f}),(t-{t0:.3f})/{in_dur:.3f},"
                f"if(lt(t,{t1:.3f}),({t1:.3f}-t)/{out_dur:.3f},0)))"
            )
        return (
            f"if(lt(t,{t0:.3f}),0,"
            f"if(lt(t,{in_end:.3f}),(t-{t0:.3f})/{in_dur:.3f},"
            f"if(gt(t,{out_beg:.3f}),({t1:.3f}-t)/{out_dur:.3f},1)))"
        )
    elif anim_type == "fade_in":
        return (
            f"if(lt(t,{t0:.3f}),0,"
            f"if(lt(t,{in_end:.3f}),(t-{t0:.3f})/{in_dur:.3f},1))"
        )
    elif anim_type == "fade_out":
        return (
            f"if(gt(t,{out_beg:.3f}),({t1:.3f}-t)/{out_dur:.3f},1)"
        )
    elif anim_type in ("slide_left_fade", "slide_right_fade"):
        return (
            f"if(gt(t,{out_beg:.3f}),({t1:.3f}-t)/{out_dur:.3f},1)"
        )
    elif anim_type in ("zoom_in", "zoom_out", "pop"):
        # zoom 系は fontsize で制御するが、フェードも合わせる
        return (
            f"if(lt(t,{t0:.3f}),0,"
            f"if(lt(t,{in_end:.3f}),(t-{t0:.3f})/{in_dur:.3f},1))"
        )
    elif anim_type == "blink":
        return None
    else:
        return None


def _build_x_expr(anim_type: str, base_x: str, t0: float, in_dur: float,
                  shake_freq: float, shake_amp: int) -> str:
    """x 座標式を生成する"""
    in_end = t0 + in_dur

    if anim_type == "slide_left":
        return (
            f"if(lt(t,{t0:.3f}),-400,"
            f"if(lt(t,{in_end:.3f}),-400+(({base_x})+400)*(t-{t0:.3f})/{in_dur:.3f},"
            f"{base_x}))"
        )
    elif anim_type in ("slide_left_fade",):
        return (
            f"if(lt(t,{t0:.3f}),-400,"
            f"if(lt(t,{in_end:.3f}),-400+(({base_x})+400)*(t-{t0:.3f})/{in_dur:.3f},"
            f"{base_x}))"
        )
    elif anim_type == "slide_right":
        return (
            f"if(lt(t,{t0:.3f}),w+50,"
            f"if(lt(t,{in_end:.3f}),w+50-((w+50-({base_x}))*(t-{t0:.3f})/{in_dur:.3f}),"
            f"{base_x}))"
        )
    elif anim_type in ("slide_right_fade",):
        return (
            f"if(lt(t,{t0:.3f}),w+50,"
            f"if(lt(t,{in_end:.3f}),w+50-((w+50-({base_x}))*(t-{t0:.3f})/{in_dur:.3f}),"
            f"{base_x}))"
        )
    elif anim_type == "shake":
        return (
            f"({base_x})+{shake_amp}*sin(2*{PI:.4f}*{shake_freq:.2f}*(t-{t0:.3f}))"
        )
    else:
        return base_x


def _build_y_expr(anim_type: str, base_y: str, t0: float, in_dur: float,
                  bounce_freq: float, bounce_amp: int) -> str:
    """y 座標式を生成する"""
    in_end = t0 + in_dur

    if anim_type == "slide_top":
        return (
            f"if(lt(t,{t0:.3f}),-100,"
            f"if(lt(t,{in_end:.3f}),-100+(({base_y})+100)*(t-{t0:.3f})/{in_dur:.3f},"
            f"{base_y}))"
        )
    elif anim_type == "slide_bottom":
        return (
            f"if(lt(t,{t0:.3f}),h+50,"
            f"if(lt(t,{in_end:.3f}),h+50-((h+50-({base_y}))*(t-{t0:.3f})/{in_dur:.3f}),"
            f"{base_y}))"
        )
    elif anim_type == "bounce":
        return (
            f"({base_y})-{bounce_amp}*abs(sin({PI:.4f}*{bounce_freq:.2f}*(t-{t0:.3f})))"
        )
    else:
        return base_y


def _build_blink_alpha(t0: float, t1: float, freq: float) -> str:
    """blink 用 alpha 式を生成する"""
    period = 1.0 / max(freq, 0.1)
    half   = period / 2.0
    return (
        f"if(between(t,{t0:.3f},{t1:.3f}),"
        f"if(lt(mod(t-{t0:.3f},{period:.4f}),{half:.4f}),1,0),"
        f"0)"
    )


def _build_zoom_fontsize(anim_type: str, size: int, t0: float, in_dur: float,
                         pop_overshoot: float) -> Optional[str]:
    """
    zoom_in / zoom_out / pop 用の fontsize 式を生成する。
    None を返した場合は固定 fontsize を使う。
    """
    in_end = t0 + in_dur

    if anim_type == "zoom_in":
        # 0 → size にリニア拡大
        return (
            f"if(lt(t,{t0:.3f}),1,"
            f"if(lt(t,{in_end:.3f}),{size}*(t-{t0:.3f})/{in_dur:.3f},"
            f"{size}))"
        )
    elif anim_type == "zoom_out":
        # size*2 → size に縮小
        start_size = size * 2
        return (
            f"if(lt(t,{t0:.3f}),{start_size},"
            f"if(lt(t,{in_end:.3f}),{start_size}-({start_size}-{size})*(t-{t0:.3f})/{in_dur:.3f},"
            f"{size}))"
        )
    elif anim_type == "pop":
        # 0 → size*overshoot → size（sin波でバウンス）
        peak_size = int(size * pop_overshoot)
        # 前半: 0→peak, 後半: peak→size
        half_dur = in_dur / 2.0
        mid = t0 + half_dur
        in_end2 = t0 + in_dur
        return (
            f"if(lt(t,{t0:.3f}),1,"
            f"if(lt(t,{mid:.3f}),{peak_size}*(t-{t0:.3f})/{half_dur:.3f},"
            f"if(lt(t,{in_end2:.3f}),{peak_size}-({peak_size}-{size})*(t-{mid:.3f})/{half_dur:.3f},"
            f"{size})))"
        )
    return None


# ============================================================
# typewriter フィルタ生成
# ============================================================

def _build_typewriter_filters(
    entry: TelopEntry,
    t0: float,
    t1: float,
    base_x: str,
    base_y: str,
    fontfile_param: str,
    border_params: str,
) -> List[str]:
    """
    typewriter アニメーション用に1文字ずつ drawtext フィルタを生成する。
    各文字は前の文字の右隣に配置し、指定速度で順次表示する。
    """
    spec = next(
        (s for s in entry.anim_specs if s.anim_type == "typewriter"),
        AnimSpec("typewriter")
    )
    chars = list(entry.text)
    if not chars:
        return []

    cps = spec.chars_per_sec
    char_interval = 1.0 / cps

    filters = []
    # 各文字を個別の drawtext で出力
    # x 位置: 文字インデックス * 推定文字幅（フォントサイズの0.6倍）
    # 日本語は等幅なのでフォントサイズ ≈ 文字幅
    char_width_est = entry.size

    for idx, ch in enumerate(chars):
        char_start = t0 + idx * char_interval
        if char_start >= t1:
            break  # 表示時間内に収まらない文字はスキップ

        escaped_ch = _escape_drawtext(ch)
        # x: base_x から idx * char_width 分右にずらす
        # base_x が "(w-text_w)/2" のような式の場合、全体の中央を基準に
        # 先頭文字の x = center_x - total_width/2 + idx * char_width
        total_width = len(chars) * char_width_est
        char_x = f"(w-{total_width})/2+{idx * char_width_est}"
        char_x_esc = _esc_comma(char_x)

        dt_parts = [
            f"drawtext=text='{escaped_ch}'",
            f"fontsize={entry.size}",
            f"fontcolor={entry.color}@1.0",
            f"x='{char_x_esc}'",
            f"y='{_esc_comma(base_y)}'",
        ]
        if fontfile_param:
            dt_parts.append(fontfile_param)
        if entry.outline:
            dt_parts.append("borderw=3")
            dt_parts.append(f"bordercolor={entry.outline_color}@1.0")
        dt_parts.append(f"enable='between(t\\,{char_start:.3f}\\,{t1:.3f})'")

        filters.append(":".join(dt_parts))

    return filters


# ============================================================
# 組み合わせアニメーション式の合成
# ============================================================

def _merge_alpha_exprs(exprs: List[Optional[str]]) -> Optional[str]:
    """
    複数の alpha 式を乗算で合成する。
    None（アニメーションなし）は 1 として扱う。
    """
    valid = [e for e in exprs if e is not None]
    if not valid:
        return None
    if len(valid) == 1:
        return valid[0]
    # 2つの式を乗算: alpha = expr1 * expr2
    # FFmpeg では alpha 式に乗算は直接書けないため、if 式で近似
    # 実用上は2つまでの組み合わせを想定
    return f"({valid[0]})*({valid[1]})"


# ============================================================
# メイン: フィルタ文字列生成
# ============================================================

def build_telop_drawtext_filters(
    entries: List[TelopEntry],
    width: int,
    height: int,
    time_offset: float = 0.0,
) -> List[str]:
    """
    TelopEntry のリストから FFmpeg drawtext フィルタ文字列のリストを生成する。

    Args:
        entries     : テロップエントリのリスト
        width       : 動画の幅
        height      : 動画の高さ
        time_offset : チャプター内でのクリップ開始オフセット（複数画像モード用）
    Returns:
        List[str]: drawtext / drawbox フィルタ文字列のリスト
    """
    auto_font = find_windows_jp_font()

    filters = []
    for entry in entries:
        # クリップ内の相対時刻に変換
        clip_start = max(0.0, entry.start - time_offset)
        clip_end   = entry.end - time_offset
        if clip_end <= clip_start:
            continue

        t0 = clip_start
        t1 = clip_end

        # 後方互換: anim_specs が [none] のままで animation フィールドが設定されている場合
        # animation 文字列から AnimSpec を生成してセットする
        specs = entry.anim_specs
        if (len(specs) == 1 and specs[0].anim_type == 'none'
                and entry.animation and entry.animation != 'none'):
            specs = _parse_anim_spec(entry.animation, 0, entry.anim_duration)

        # ベース x/y 式（アニメーションなし時の位置）
        base_x, base_y = _position_to_xy(entry.position, width, height, entry.size)

        # フォントファイルの決定
        resolved_font = entry.fontfile or auto_font
        if resolved_font and os.path.isfile(resolved_font):
            fp = resolved_font.replace('\\', '/').replace(':', '\\:')
            fontfile_param = f"fontfile='{fp}'"
        else:
            fontfile_param = ""

        border_params = ""
        if entry.outline:
            border_params = f"borderw=3:bordercolor={entry.outline_color}@1.0"

        # ---- typewriter は特別処理 ----
        is_typewriter = any(s.anim_type == "typewriter" for s in specs)
        if is_typewriter:
            # 背景帯
            if entry.bg:
                bg_height = entry.size + 20
                bg_y = _bg_y_expr(entry.position, height, bg_height)
                filters.append(
                    f"drawbox=x=0:y={bg_y}:w=iw:h={bg_height}"
                    f":color=black@0.6:t=fill"
                    f":enable='between(t\\,{t0:.3f}\\,{t1:.3f})'"
                )
            tw_filters = _build_typewriter_filters(
                entry, t0, t1, base_x, base_y, fontfile_param, border_params
            )
            filters.extend(tw_filters)
            continue

        # ---- 組み合わせアニメーション処理 ----
        # x/y 式: 最初のスライド系 spec を使用
        x_expr = base_x
        y_expr = base_y
        zoom_fontsize_expr = None

        for sp in specs:
            at = sp.anim_type
            # x
            new_x = _build_x_expr(at, base_x, t0, sp.in_duration,
                                   entry.shake_freq, entry.shake_amp)
            if new_x != base_x:
                x_expr = new_x
            # y
            new_y = _build_y_expr(at, base_y, t0, sp.in_duration,
                                   entry.bounce_freq, entry.bounce_amp)
            if new_y != base_y:
                y_expr = new_y
            # zoom fontsize
            if at in ("zoom_in", "zoom_out", "pop"):
                zoom_fontsize_expr = _build_zoom_fontsize(
                    at, entry.size, t0, sp.in_duration, sp.pop_overshoot
                )

        # alpha 式: 各 spec の alpha を合成
        alpha_exprs = []
        for sp in specs:
            at = sp.anim_type
            if at == "blink":
                alpha_exprs.append(_build_blink_alpha(t0, t1, entry.blink_freq))
            else:
                ae = _build_alpha_expr(at, t0, t1, sp.in_duration, sp.out_duration)
                if ae is not None:
                    alpha_exprs.append(ae)

        alpha_expr = _merge_alpha_exprs(alpha_exprs)

        # カンマエスケープ
        x_esc = _esc_comma(x_expr)
        y_esc = _esc_comma(y_expr)

        escaped = _escape_drawtext(entry.text)

        # 背景帯
        if entry.bg:
            bg_height = entry.size + 20
            bg_y = _bg_y_expr(entry.position, height, bg_height)
            filters.append(
                f"drawbox=x=0:y={bg_y}:w=iw:h={bg_height}"
                f":color=black@0.6:t=fill"
                f":enable='between(t\\,{t0:.3f}\\,{t1:.3f})'"
            )

        # drawtext 組み立て
        dt_parts = [
            f"drawtext=text='{escaped}'",
        ]
        # fontsize: zoom 系は動的式、それ以外は固定
        if zoom_fontsize_expr:
            dt_parts.append(f"fontsize='{_esc_comma(zoom_fontsize_expr)}'")
        else:
            dt_parts.append(f"fontsize={entry.size}")

        dt_parts += [
            f"fontcolor={entry.color}@1.0",
            f"x='{x_esc}'",
            f"y='{y_esc}'",
        ]
        if fontfile_param:
            dt_parts.append(fontfile_param)
        if entry.outline:
            dt_parts.append("borderw=3")
            dt_parts.append(f"bordercolor={entry.outline_color}@1.0")
        if alpha_expr:
            alpha_esc = _esc_comma(alpha_expr)
            dt_parts.append(f"alpha='{alpha_esc}'")

        # enable（表示時間範囲）
        dt_parts.append(f"enable='between(t\\,{t0:.3f}\\,{t1:.3f})'")

        drawtext_str = ":".join(dt_parts)
        filters.append(drawtext_str)

    return filters


def _escape_drawtext(text: str) -> str:
    """FFmpeg drawtext 用テキストエスケープ"""
    text = text.replace('\\', '\\\\')
    text = text.replace(':', '\\:')
    text = text.replace("'", "\\'")
    text = text.replace('%', '\\%')
    return text


def _position_to_xy(position: str, width: int, height: int, size: int):
    """position 文字列から FFmpeg drawtext の x/y 式を返す。"""
    margin = 20
    pos = position.lower()

    if pos == "top":
        x = "(w-text_w)/2"
        y = str(margin)
    elif pos == "center":
        x = "(w-text_w)/2"
        y = "(h-text_h)/2"
    elif pos == "bottom":
        x = "(w-text_w)/2"
        y = f"h-text_h-{margin}"
    elif pos == "top-left":
        x = str(margin)
        y = str(margin)
    elif pos == "top-right":
        x = f"w-text_w-{margin}"
        y = str(margin)
    elif pos == "bottom-left":
        x = str(margin)
        y = f"h-text_h-{margin}"
    elif pos == "bottom-right":
        x = f"w-text_w-{margin}"
        y = f"h-text_h-{margin}"
    else:
        x = "(w-text_w)/2"
        y = f"h-text_h-{margin}"

    return x, y


def _bg_y_expr(position: str, height: int, bg_height: int) -> str:
    """背景帯の y 座標式を返す"""
    pos = position.lower()
    if 'top' in pos:
        return str(0)
    elif pos == 'center':
        return f"(ih-{bg_height})/2"
    else:
        return f"ih-{bg_height}"
