# -*- coding: utf-8 -*-
"""
Video generator module - Creates MP4 from audio+image pairs using FFmpeg

Multi-image mode:
    When a FilePair has visual_items (multi-image mode), the audio duration
    is split equally among the visual items. Each visual item is rendered as
    a short clip with fade-in/out, then all clips are concatenated into one
    chapter video using FFmpeg concat demuxer.
"""
import os
import sys
import json
import subprocess
import tempfile
import shutil
from typing import List, Callable, Optional
from dataclasses import dataclass, field
from file_scanner import FilePair, VisualItem
from telop_parser import (
    load_telop_file, find_telop_file,
    build_telop_drawtext_filters, TelopEntry,
)


# ========== 解像度プリセット ==========
RESOLUTION_PRESETS = {
    "1080p 横型 (YouTube/一般)":   (1920, 1080),
    "720p 横型":                    (1280, 720),
    "4K 横型 (YouTube 4K)":         (3840, 2160),
    "1080p 縦型 (TikTok/Reels)":    (1080, 1920),
    "720p 縦型":                    (720, 1280),
    "1:1 正方形 (Instagram)":       (1080, 1080),
}

DEFAULT_PRESET    = "1080p 横型 (YouTube/一般)"
VIDEO_FPS         = 30
FADE_DURATION     = 0.75
TITLE_DURATION    = 2.5
TITLE_FONT_SIZE   = 60
OUTPUT_FILENAME   = "output.mp4"
KB_ZOOM_AMOUNT    = 1.08


@dataclass
class GenerationConfig:
    """動画生成設定"""
    pairs: List[FilePair]
    output_path: str
    width: int = 1920
    height: int = 1080
    fps: int = VIDEO_FPS
    fade_duration: float = FADE_DURATION
    title_duration: float = TITLE_DURATION
    title_overlay: bool = True           # ファイル名タイトルを動画に表示するか
    ken_burns: bool = False
    ken_burns_zoom: float = KB_ZOOM_AMOUNT
    # --- Audio visualizer watermark ---
    visualizer_enabled: bool = False
    visualizer_style: str = "waveform"   # waveform / freqbar / spectrum / vectorscope
    visualizer_color: str = "#00ffff"    # hex color (used when color_mode == 'solid')
    visualizer_color_mode: str = "solid" # solid / rainbow / fire / neon / gold
    visualizer_opacity: float = 0.6      # 0.0-1.0
    visualizer_height: int = 80          # bar height in px (for waveform/freqbar/spectrum)
    # --- BGM mix ---
    bgm_path: Optional[str] = None       # BGMファイルパス（Noneなら無効）
    voice_volume: float = 1.0            # 音声ボリューム倍率 (0.0-2.0)
    bgm_volume: float = 0.5             # BGMボリューム倍率 (0.0-2.0)
    bgm_fade_in: float = 1.0            # BGMフェードイン秒数
    bgm_fade_out: float = 2.0           # BGMフェードアウト秒数
    bgm_start_offset: float = 0.0       # BGM開始オフセット秒数

    @property
    def preset_name(self) -> str:
        for name, (w, h) in RESOLUTION_PRESETS.items():
            if w == self.width and h == self.height:
                return name
        return f"カスタム ({self.width}x{self.height})"


def get_ffmpeg_path() -> str:
    """FFmpegの実行ファイルパスを返す"""
    if hasattr(sys, '_MEIPASS'):
        candidates = [
            os.path.join(sys._MEIPASS, 'ffmpeg.exe'),
            os.path.join(sys._MEIPASS, 'ffmpeg'),
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c
    ffmpeg = shutil.which('ffmpeg')
    if ffmpeg:
        return ffmpeg
    exe_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    for name in ['ffmpeg.exe', 'ffmpeg']:
        candidate = os.path.join(exe_dir, name)
        if os.path.isfile(candidate):
            return candidate
    raise FileNotFoundError(
        "FFmpegが見つかりません。\n"
        "ffmpeg.exe をアプリと同じフォルダに配置するか、\n"
        "システムのPATHにFFmpegを追加してください。"
    )


def get_audio_duration(audio_path: str, ffmpeg_path: str) -> float:
    """音声ファイルの長さを秒単位で取得する"""
    ext = os.path.splitext(audio_path)[1].lower()
    try:
        if ext == '.mp3':
            from mutagen.mp3 import MP3
            return MP3(audio_path).info.length
        elif ext == '.wav':
            from mutagen.wave import WAVE
            return WAVE(audio_path).info.length
        elif ext == '.flac':
            from mutagen.flac import FLAC
            return FLAC(audio_path).info.length
        elif ext == '.ogg':
            from mutagen.oggvorbis import OggVorbis
            return OggVorbis(audio_path).info.length
        elif ext in ('.m4a', '.aac'):
            from mutagen.mp4 import MP4
            return MP4(audio_path).info.length
        elif ext == '.wma':
            from mutagen.asf import ASF
            return ASF(audio_path).info.length
    except Exception:
        pass
    ffprobe = ffmpeg_path.replace('ffmpeg', 'ffprobe').replace('ffmpeg.exe', 'ffprobe.exe')
    if not os.path.isfile(ffprobe):
        ffprobe = shutil.which('ffprobe') or 'ffprobe'
    try:
        result = subprocess.run(
            [ffprobe, '-v', 'quiet', '-print_format', 'json', '-show_streams', audio_path],
            capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=30
        )
        data = json.loads(result.stdout)
        for stream in data.get('streams', []):
            if stream.get('codec_type') == 'audio':
                dur = stream.get('duration', 0)
                if dur:
                    return float(dur)
        fmt = data.get('format', {})
        if fmt.get('duration'):
            return float(fmt['duration'])
    except Exception:
        pass
    return 5.0


def run_ffmpeg(ffmpeg_path: str, args: List[str], timeout: int = 300) -> subprocess.CompletedProcess:
    """FFmpegコマンドを実行する"""
    cmd = [ffmpeg_path] + args
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=timeout,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
    )
    return result


# ========== BGM フォルダ自動検出 ==========
BGM_FILENAMES = ['_bgm', '_BGM', 'bgm', 'BGM']
BGM_EXTENSIONS = ['.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac', '.wma']


def find_folder_bgm(folder: str) -> Optional[str]:
    """入力フォルダ内の自動BGMファイルを検索する。
    _bgm.mp3 / _bgm.wav 等を優先順にチェックする。
    """
    for name in BGM_FILENAMES:
        for ext in BGM_EXTENSIONS:
            candidate = os.path.join(folder, name + ext)
            if os.path.isfile(candidate):
                return candidate
    return None


def load_bgm_timing(bgm_path: str) -> dict:
    """
    BGMタイミングJSONを読み込む。
    JSONファイル名: {bgm_base}_timing.json
    フォーマット: {"start_offset": 5.0, "fade_in": 1.0, "fade_out": 3.0}
    ファイルがない場合は空辞書を返す。
    """
    base = os.path.splitext(bgm_path)[0]
    timing_path = base + '_timing.json'
    if not os.path.isfile(timing_path):
        return {}
    try:
        with open(timing_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def mix_bgm_to_video(
    input_video: str,
    output_video: str,
    bgm_path: str,
    voice_volume: float,
    bgm_volume: float,
    bgm_start_offset: float,
    bgm_fade_in: float,
    bgm_fade_out: float,
    ffmpeg_path: str,
) -> None:
    """
    完成した動画にBGMをミックスする。
    - BGMは動画の長さに合わせてループ再生
    - 音声とBGMをamixでミックス
    - フェードイン/アウト対応
    """
    # BGMの長さを取得してループ回数を計算
    bgm_duration = get_audio_duration(bgm_path, ffmpeg_path)

    # ffprobeで動画の長さを取得
    ffprobe = ffmpeg_path.replace('ffmpeg', 'ffprobe').replace('ffmpeg.exe', 'ffprobe.exe')
    if not os.path.isfile(ffprobe):
        ffprobe = shutil.which('ffprobe') or 'ffprobe'
    try:
        result = subprocess.run(
            [ffprobe, '-v', 'quiet', '-print_format', 'json', '-show_format', input_video],
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30
        )
        video_duration = float(json.loads(result.stdout).get('format', {}).get('duration', 0))
    except Exception:
        video_duration = 0

    if video_duration <= 0:
        raise RuntimeError("BGMミックス: 動画の長さを取得できませんでした")

    # BGMループ回数を計算（余裕を持たせて+1）
    effective_bgm_duration = bgm_duration - bgm_start_offset
    if effective_bgm_duration <= 0:
        effective_bgm_duration = bgm_duration
        bgm_start_offset = 0.0
    loop_count = int(video_duration / effective_bgm_duration) + 2

    # フェードアウト開始時刻
    fade_out_start = max(0, video_duration - bgm_fade_out)

    # audio filter_complex:
    # [1:a] = BGM
    # atrim: BGMの開始オフセットをカット
    # aloop: ループ再生
    # atrim: 動画の長さに合わせてカット
    # afade: フェードイン/アウト
    # volume: BGM音量調整
    # [0:a] = 元音声
    # volume: 音声音量調整
    # amix: ミックス
    bgm_filter = (
        f"[1:a]atrim=start={bgm_start_offset:.3f},"
        f"aloop=loop={loop_count}:size=2147483647,"
        f"atrim=duration={video_duration:.3f},"
        f"afade=t=in:st=0:d={bgm_fade_in:.3f},"
        f"afade=t=out:st={fade_out_start:.3f}:d={bgm_fade_out:.3f},"
        f"volume={bgm_volume:.3f}[bgm_out];"
        f"[0:a]volume={voice_volume:.3f}[voice_out];"
        f"[voice_out][bgm_out]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    )

    args = [
        '-y',
        '-i', input_video,
        '-i', bgm_path,
        '-filter_complex', bgm_filter,
        '-map', '0:v',
        '-map', '[aout]',
        '-c:v', 'copy',
        '-c:a', 'aac', '-b:a', '192k',
        '-movflags', '+faststart',
        output_video,
    ]
    result = run_ffmpeg(ffmpeg_path, args, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(
            f"BGMミックスに失敗しました。\nFFmpegエラー:\n{result.stderr[-2000:]}"
        )


def _build_ken_burns_filter(w: int, h: int, fps: int, duration: float,
                             zoom: float, chapter_index: int) -> str:
    """ケン・バーンズ効果フィルタ文字列を生成する"""
    total_frames = int(duration * fps)
    patterns = ['zoom_in', 'zoom_out', 'pan_lr', 'pan_rl']
    pattern = patterns[chapter_index % len(patterns)]
    if pattern == 'zoom_in':
        zoom_expr = f"zoom+{(zoom-1.0)/total_frames:.6f}"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif pattern == 'zoom_out':
        zoom_expr = f"if(eq(on,1),{zoom:.4f},zoom-{(zoom-1.0)/total_frames:.6f})"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif pattern == 'pan_lr':
        zoom_expr = str(zoom)
        x_expr = f"(iw-iw/zoom)*on/{total_frames}"
        y_expr = "ih/2-(ih/zoom/2)"
    else:
        zoom_expr = str(zoom)
        x_expr = f"(iw-iw/zoom)*(1-on/{total_frames})"
        y_expr = "ih/2-(ih/zoom/2)"
    return (
        f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}'"
        f":d={total_frames}:s={w}x{h}:fps={fps}"
    )


def _escape_drawtext(s: str) -> str:
    """drawtext フィルタ用にテキストをエスケープする"""
    s = s.replace('\\', '\\\\')
    s = s.replace(':', '\\:')
    s = s.replace("'", "\\'")
    return s


def _build_visual_vf(
    visual_path: str,
    is_gif: bool,
    is_video: bool,
    is_animated_gif: bool,
    duration: float,
    w: int,
    h: int,
    fps: int,
    fade: float,
    title_text: Optional[str],
    title_dur: float,
    ken_burns: bool,
    ken_burns_zoom: float,
    chapter_index: int,
    telop_entries: Optional[List['TelopEntry']] = None,
    telop_time_offset: float = 0.0,
) -> str:
    """視覚素材1つ分の vf フィルタ文字列を構築する"""
    from file_scanner import VIDEO_PRIORITY

    if ken_burns and not is_gif and not is_video:
        kb_filter = _build_ken_burns_filter(w, h, fps, duration,
                                            ken_burns_zoom, chapter_index)
        scale_filter = (
            f"[0:v]scale={int(w * ken_burns_zoom * 1.1)}:{int(h * ken_burns_zoom * 1.1)}"
            f":force_original_aspect_ratio=increase,"
            f"crop={int(w * ken_burns_zoom * 1.1)}:{int(h * ken_burns_zoom * 1.1)},"
            f"{kb_filter},"
            f"setsar=1"
        )
    else:
        scale_filter = (
            f"[0:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,"
            f"setsar=1,fps={fps}"
        )

    filters = [scale_filter]

    if title_text is not None:
        from telop_parser import find_windows_jp_font
        escaped = _escape_drawtext(title_text)
        # fontfileを明示指定してFontconfig依存を回避する
        _auto_font = find_windows_jp_font()
        if _auto_font and os.path.isfile(_auto_font):
            _fp = _auto_font.replace('\\', '/').replace(':', '\\:')
            _fontfile_param = f":fontfile='{_fp}'"
        else:
            _fontfile_param = ""
        title_filter = (
            f"drawbox=x=0:y=ih-120:w=iw:h=120:color=black@0.6:t=fill:"
            f"enable='between(t,0,{title_dur})',"
            f"drawtext=text='{escaped}'"
            f"{_fontfile_param}"
            f":fontsize={TITLE_FONT_SIZE}"
            f":fontcolor=white"
            f":x=(w-text_w)/2"
            f":y=h-80"
            f":enable='between(t,0,{title_dur})'"
        )
        filters.append(title_filter)

    # telop drawtext filters
    if telop_entries:
        telop_filters = build_telop_drawtext_filters(
            entries=telop_entries,
            width=w,
            height=h,
            time_offset=telop_time_offset,
        )
        filters.extend(telop_filters)

    fade_out_start = max(0, duration - fade)
    filters.append(f"fade=t=in:st=0:d={fade:.3f}")
    filters.append(f"fade=t=out:st={fade_out_start:.3f}:d={fade:.3f}")

    return ",".join(filters)


def _generate_single_visual_clip(
    visual_path: str,
    audio_path: str,
    audio_start: float,
    clip_duration: float,
    output_path: str,
    config: GenerationConfig,
    ffmpeg_path: str,
    chapter_index: int,
    is_gif: bool = False,
    is_video: bool = False,
    is_animated_gif: bool = False,
    title_text: Optional[str] = None,
    telop_entries: Optional[List['TelopEntry']] = None,
    telop_time_offset: float = 0.0,
) -> None:
    """
    1つの視覚素材と音声の一部からクリップを生成する。
    audio_start: 音声ファイルの開始オフセット（秒）
    clip_duration: クリップの長さ（秒）
    """
    w = config.width
    h = config.height
    fps = config.fps
    fade = config.fade_duration
    title_dur = config.title_duration

    vf = _build_visual_vf(
        visual_path=visual_path,
        is_gif=is_gif,
        is_video=is_video,
        is_animated_gif=is_animated_gif,
        duration=clip_duration,
        w=w, h=h, fps=fps, fade=fade,
        title_text=title_text,
        title_dur=title_dur,
        ken_burns=config.ken_burns,
        ken_burns_zoom=config.ken_burns_zoom,
        chapter_index=chapter_index,
        telop_entries=telop_entries,
        telop_time_offset=telop_time_offset,
    )

    if is_video:
        args = [
            '-y',
            '-stream_loop', '-1',
            '-i', visual_path,
            '-ss', str(audio_start),
            '-i', audio_path,
            '-map', '0:v:0',
            '-map', '1:a:0',
            '-vf', vf,
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
            '-c:a', 'aac', '-b:a', '192k',
            '-t', str(clip_duration),
            '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart',
            output_path
        ]
    elif is_gif:
        args = [
            '-y',
            '-stream_loop', '-1',
            '-i', visual_path,
            '-ss', str(audio_start),
            '-i', audio_path,
            '-vf', vf,
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
            '-c:a', 'aac', '-b:a', '192k',
            '-t', str(clip_duration),
            '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart',
            output_path
        ]
    else:
        args = [
            '-y',
            '-loop', '1',
            '-i', visual_path,
            '-ss', str(audio_start),
            '-i', audio_path,
            '-vf', vf,
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
            '-c:a', 'aac', '-b:a', '192k',
            '-t', str(clip_duration),
            '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart',
            output_path
        ]

    result = run_ffmpeg(ffmpeg_path, args)
    if result.returncode != 0:
        raise RuntimeError(
            f"クリップ生成に失敗しました: {os.path.basename(visual_path)}\n"
            f"FFmpegエラー:\n{result.stderr[-2000:]}"
        )


def generate_chapter_video(
    pair: FilePair,
    output_path: str,
    config: GenerationConfig,
    ffmpeg_path: str,
    chapter_index: int,
    temp_dir: str,
) -> None:
    """
    1チャプター分の動画を生成する。
    single_mode: 従来の1対1処理
    multi_mode:  複数画像を均等分割して結合
    """
    from file_scanner import VIDEO_PRIORITY

    total_duration = get_audio_duration(pair.audio_path, ffmpeg_path)

    if pair.single_mode:
        # ---- 従来の1対1モード ----
        is_gif = pair.image_path.lower().endswith('.gif')
        is_video = pair.image_ext in VIDEO_PRIORITY

        # load telop for this chapter
        _telop_json = find_telop_file(pair.audio_path)
        _telop_entries = load_telop_file(_telop_json) if _telop_json else []

        vf = _build_visual_vf(
            visual_path=pair.image_path,
            is_gif=is_gif,
            is_video=is_video,
            is_animated_gif=pair.is_animated_gif,
            duration=total_duration,
            w=config.width, h=config.height, fps=config.fps,
            fade=config.fade_duration,
            title_text=pair.base_name if config.title_overlay else None,
            title_dur=config.title_duration,
            ken_burns=config.ken_burns,
            ken_burns_zoom=config.ken_burns_zoom,
            chapter_index=chapter_index,
            telop_entries=_telop_entries,
            telop_time_offset=0.0,
        )

        if is_video:
            args = [
                '-y',
                '-stream_loop', '-1',
                '-i', pair.image_path,
                '-i', pair.audio_path,
                '-map', '0:v:0',
                '-map', '1:a:0',
                '-vf', vf,
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
                '-c:a', 'aac', '-b:a', '192k',
                '-t', str(total_duration),
                '-pix_fmt', 'yuv420p',
                '-movflags', '+faststart',
                output_path
            ]
        elif is_gif:
            args = [
                '-y',
                '-stream_loop', '-1',
                '-i', pair.image_path,
                '-i', pair.audio_path,
                '-vf', vf,
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
                '-c:a', 'aac', '-b:a', '192k',
                '-t', str(total_duration),
                '-pix_fmt', 'yuv420p',
                '-movflags', '+faststart',
                output_path
            ]
        else:
            args = [
                '-y',
                '-loop', '1',
                '-i', pair.image_path,
                '-i', pair.audio_path,
                '-vf', vf,
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
                '-c:a', 'aac', '-b:a', '192k',
                '-t', str(total_duration),
                '-pix_fmt', 'yuv420p',
                '-movflags', '+faststart',
                output_path
            ]
        result = run_ffmpeg(ffmpeg_path, args)
        if result.returncode != 0:
            raise RuntimeError(
                f"チャプター '{pair.base_name}' の動画生成に失敗しました。\n"
                f"FFmpegエラー:\n{result.stderr[-2000:]}"
            )

    else:
        # ---- 複数画像モード ----
        from timing_parser import find_timing_file, calculate_clip_durations
        items = pair.visual_items
        n = len(items)
        # タイミングJSONがあれば個別指定、なければ均等分割
        timing_json = find_timing_file(pair.audio_path)
        item_paths = [item.path for item in items]
        clip_durations = calculate_clip_durations(item_paths, total_duration, timing_json)
        # load telop for this chapter (shared across all clips)
        _telop_json = find_telop_file(pair.audio_path)
        _telop_entries = load_telop_file(_telop_json) if _telop_json else []
        clip_paths = []
        audio_start = 0.0
        for item_idx, item in enumerate(items):
            clip_path = os.path.join(
                temp_dir, f'chapter_{chapter_index:04d}_clip_{item_idx:04d}.mp4'
            )
            clip_duration = clip_durations[item_idx]
            # タイトルはチャプターの先頭クリップのみ表示（title_overlayがTrueの場合）
            title = (pair.base_name if item_idx == 0 else None) if config.title_overlay else None
            # ケン・バーンズのパターンはクリップごとに進める
            kb_index = chapter_index * n + item_idx
            _generate_single_visual_clip(
                visual_path=item.path,
                audio_path=pair.audio_path,
                audio_start=audio_start,
                clip_duration=clip_duration,
                output_path=clip_path,
                config=config,
                ffmpeg_path=ffmpeg_path,
                chapter_index=kb_index,
                is_gif=item.ext == '.gif',
                is_video=item.is_video_input,
                is_animated_gif=item.is_animated_gif,
                title_text=title,
                telop_entries=_telop_entries,
                telop_time_offset=audio_start,
            )
            clip_paths.append(clip_path)
            audio_start += clip_duration

        # クリップを結合してチャプター動画を作成
        if len(clip_paths) == 1:
            shutil.copy2(clip_paths[0], output_path)
        else:
            list_file = os.path.join(
                temp_dir, f'chapter_{chapter_index:04d}_clips.txt'
            )
            with open(list_file, 'w', encoding='utf-8') as f:
                for cp in clip_paths:
                    safe = cp.replace('\\', '/')
                    f.write(f"file '{safe}'\n")
            args = [
                '-y', '-f', 'concat', '-safe', '0',
                '-i', list_file, '-c', 'copy', output_path
            ]
            result = run_ffmpeg(ffmpeg_path, args)
            if result.returncode != 0:
                raise RuntimeError(
                    f"チャプター '{pair.base_name}' のクリップ結合に失敗しました。\n"
                    f"FFmpegエラー:\n{result.stderr[-2000:]}"
                )


def concatenate_videos(
    chapter_paths: List[str],
    output_path: str,
    ffmpeg_path: str,
    temp_dir: str,
) -> None:
    """複数のチャプター動画を1本に結合する"""
    if len(chapter_paths) == 1:
        shutil.copy2(chapter_paths[0], output_path)
        return
    list_file = os.path.join(temp_dir, 'concat_list.txt')
    with open(list_file, 'w', encoding='utf-8') as f:
        for path in chapter_paths:
            safe_path = path.replace('\\', '/')
            f.write(f"file '{safe_path}'\n")
    args = [
        '-y', '-f', 'concat', '-safe', '0', '-i', list_file, '-c', 'copy', output_path
    ]
    result = run_ffmpeg(ffmpeg_path, args)
    if result.returncode != 0:
        raise RuntimeError(
            f"動画の結合に失敗しました。\n"
            f"FFmpegエラー:\n{result.stderr[-2000:]}"
        )


# ========== Visualizer ==========
VIZUALIZER_STYLES = {
    "waveform":    "波形 (Waveform)",
    "freqbar":     "周波数バー (Freq Bar)",
    "spectrum":    "スペクトログラム",
    "vectorscope": "ベクタースコープ",
}

# カラーモード定義
VIZUALIZER_COLOR_MODES = {
    "solid":   "単色",
    "rainbow": "レインボー",
    "fire":    "ファイア",
    "neon":    "ネオン",
    "gold":    "ゴールド",
}


def _hex_to_ffmpeg_color(hex_color: str) -> str:
    """#RRGGBB -> 0xRRGGBB"""
    return hex_color.replace('#', '0x')


def _build_rainbow_hue_filter(viz_label: str, opacity: float) -> str:
    """
    [viz] に対して時間で色相を回転させる hue フィルタを適用し [viz_colored] を返す。
    speed=60 で約6秒で一周（虹色サイクル）。
    """
    # hue フィルタ: h='mod(t*60, 360)' で時間とともに色相を回転
    # s=2 で彩度を高めて鮮やかに
    return (
        f"[{viz_label}]hue=h='mod(t*60,360)':s=2.5[viz_colored]"
    )


# geq式定義: p(X,Y)は現在プレーンのピクセル値(0-255)、Tは時刻(秒)
# 各式は RGBA フォーマットの画像に適用する
GEQ_COLOR_EXPRS = {
    # rainbow: 120度ごとに位相をずらしたsinでR/G/Bを着色。約6秒で一周
    "rainbow": (
        "r='p(X,Y)*max(0,sin(T*1.047+0))'"
        ":g='p(X,Y)*max(0,sin(T*1.047+2.094))'"
        ":b='p(X,Y)*max(0,sin(T*1.047+4.189))'"
        ":a='255'"
    ),
    # fire: R=全局、G=sinで赤→黄に揺れる、B=0
    "fire": (
        "r='p(X,Y)'"
        ":g='p(X,Y)*(0.3+0.3*sin(T*3))'"
        ":b='0'"
        ":a='255'"
    ),
    # neon: 高速色相回転（約3秒で一周）
    "neon": (
        "r='p(X,Y)*max(0,sin(T*2.094+0))'"
        ":g='p(X,Y)*max(0,sin(T*2.094+2.094))'"
        ":b='p(X,Y)*max(0,sin(T*2.094+4.189))'"
        ":a='255'"
    ),
    # gold: R=全局、G=黄金色範囲で微妙に揺れる、B=微小
    "gold": (
        "r='p(X,Y)'"
        ":g='p(X,Y)*(0.65+0.15*sin(T*2))'"
        ":b='p(X,Y)*0.05'"
        ":a='255'"
    ),
}


def _build_color_mode_filter(
    viz_label: str,
    color_mode: str,
    solid_color: str,
    opacity: float,
) -> tuple:
    """
    カラーモードに応じたフィルタ文字列と出力ラベルを返す。
    Returns: (extra_filters: str, final_label: str)
      extra_filters: セミコロン区切りで追加するフィルタ群（空文字の場合もある）
      final_label: 透明度適用前の最終ラベル名
    """
    if color_mode in GEQ_COLOR_EXPRS:
        geq_expr = GEQ_COLOR_EXPRS[color_mode]
        extra = f"[{viz_label}]format=rgba,geq={geq_expr}[viz_col]"
        return extra, "viz_col"
    else:  # solid
        return "", viz_label


def build_visualizer_filter(
    style: str,
    color: str,
    opacity: float,
    viz_height: int,
    width: int,
    height: int,
    color_mode: str = "solid",
) -> str:
    """
    ビジュアライザーを既存の動画に透かしとして重ねる
    filter_complex 文字列を返す。
    入力: [0:v] = 映像, [0:a] = 音声
    出力: [vout]
    """
    fc = _hex_to_ffmpeg_color(color)
    clamp_h = max(40, min(viz_height, height // 3))

    # --- ステップ1: ビジュアライザー素材を生成 ---
    if style == "waveform":
        # showwaves: 単色モードのときは色付き波形、カラーモード時は白で生成してから着色
        if color_mode == "solid":
            fc_str = f"{fc}@{opacity:.2f}"
            base_filter = (
                f"[0:a]showwaves=s={width}x{clamp_h}:mode=cline:colors={fc_str}:scale=lin[viz_raw];"
                f"[viz_raw]colorkey=0x000000:0.15:0.1[viz]"
            )
        else:
            # 白色で生成してから hue で着色
            base_filter = (
                f"[0:a]showwaves=s={width}x{clamp_h}:mode=cline:colors=0xffffff@1.0:scale=lin[viz_raw];"
                f"[viz_raw]colorkey=0x000000:0.15:0.1[viz]"
            )

    elif style == "freqbar":
        if color_mode == "solid":
            base_filter = (
                f"[0:a]showfreqs=s={width}x{clamp_h}:mode=bar:colors={fc}:fscale=log:ascale=log[viz_raw];"
                f"[viz_raw]format=rgba[viz]"
            )
        else:
            # 白色で生成してgeqで着色（format=rgbaは_build_color_mode_filter内で適用）
            base_filter = (
                f"[0:a]showfreqs=s={width}x{clamp_h}:mode=bar:colors=0xffffff:fscale=log:ascale=log[viz_raw];"
                f"[viz_raw]colorkey=0x000000:0.15:0.1[viz]"
            )

    elif style == "spectrum":
        # spectrum は color=intensity で既に多色なので、カラーモードに関わらず intensity を使う
        # rainbow/neon/fire/gold 時はさらに hue で色相シフト
        base_filter = (
            f"[0:a]showspectrum=s={width}x{clamp_h}:mode=combined:color=intensity:scale=log[viz_raw];"
            f"[viz_raw]colorkey=0x000000:0.15:0.1[viz]"
        )

    elif style == "vectorscope":
        sz = min(width, height) // 5
        sz = max(80, sz)
        if color_mode == "solid":
            base_filter = (
                f"[0:a]avectorscope=s={sz}x{sz}:zoom=1.5:rc=0:gc=200:bc=0:rf=0:gf=40:bf=0[viz_raw];"
                f"[viz_raw]colorkey=0x000000:0.15:0.1[viz]"
            )
        else:
            # 白色で生成して着色
            base_filter = (
                f"[0:a]avectorscope=s={sz}x{sz}:zoom=1.5:rc=255:gc=255:bc=255:rf=0:gf=0:bf=0[viz_raw];"
                f"[viz_raw]colorkey=0x000000:0.15:0.1[viz]"
            )
    else:
        raise ValueError(f"Unknown visualizer style: {style}")

    # --- ステップ2: カラーモードフィルタを適用 ---
    color_extra, colored_label = _build_color_mode_filter(
        viz_label="viz",
        color_mode=color_mode,
        solid_color=color,
        opacity=opacity,
    )

    # --- ステップ3: 透明度適用 → overlay ---
    if style == "vectorscope":
        sz = min(width, height) // 5
        sz = max(80, sz)
        overlay_pos = f"W-{sz+20}:H-{sz+20}"
        overlay_size = clamp_h  # 使わないが変数として保持
    else:
        overlay_pos = f"0:H-{clamp_h}"

    # 透明度適用 → overlay（geq後はすでにRGBAなのでformat変換不要）
    final_filter = (
        f"[{colored_label}]colorchannelmixer=aa={opacity:.2f}[viz_t];"
        f"[0:v][viz_t]overlay={overlay_pos}:format=auto[vout]"
    )

    # 全フィルタを結合
    parts = [base_filter]
    if color_extra:
        parts.append(color_extra)
    parts.append(final_filter)
    return ";".join(parts)


def apply_visualizer(
    input_path: str,
    output_path: str,
    config: 'GenerationConfig',
    ffmpeg_path: str,
) -> None:
    """完成した動画にビジュアライザーを後処理で適用する"""
    fc = build_visualizer_filter(
        style=config.visualizer_style,
        color=config.visualizer_color,
        opacity=config.visualizer_opacity,
        viz_height=config.visualizer_height,
        width=config.width,
        height=config.height,
        color_mode=config.visualizer_color_mode,
    )
    args = [
        '-y', '-i', input_path,
        '-filter_complex', fc,
        '-map', '[vout]', '-map', '0:a',
        '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
        '-c:a', 'copy',
        '-pix_fmt', 'yuv420p',
        '-movflags', '+faststart',
        output_path,
    ]
    result = run_ffmpeg(ffmpeg_path, args, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(
            f"ビジュアライザーの適用に失敗しました。\n"
            f"FFmpegエラー:\n{result.stderr[-2000:]}"
        )


def generate_video(
    config: GenerationConfig,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> str:
    """
    メイン動画生成関数

    Args:
        config: 生成設定
        progress_callback: 進捗コールバック (percent: int, message: str)
        cancel_check: キャンセルチェック関数（Trueを返したらキャンセル）

    Returns:
        str: 生成された動画ファイルのパス
    """
    def report(percent: int, message: str):
        if progress_callback:
            progress_callback(percent, message)

    def check_cancel():
        if cancel_check and cancel_check():
            raise InterruptedError("ユーザーによってキャンセルされました。")

    report(0, "FFmpegを確認中...")
    ffmpeg_path = get_ffmpeg_path()

    output_dir = os.path.dirname(config.output_path)
    if output_dir and not os.path.exists(output_dir):
        raise FileNotFoundError(f"出力先フォルダが見つかりません: {output_dir}")
    test_dir = output_dir if output_dir else '.'
    if not os.access(test_dir, os.W_OK):
        raise PermissionError(f"出力先フォルダに書き込みできません: {test_dir}")

    pairs = config.pairs
    if not pairs:
        raise ValueError("生成するペアがありません。")

    total_chapters = len(pairs)
    chapter_paths = []
    temp_dir = tempfile.mkdtemp(prefix='slideshow_maker_')

    try:
        for i, pair in enumerate(pairs):
            check_cancel()
            chapter_output = os.path.join(temp_dir, f'chapter_{i:04d}.mp4')
            percent = int((i / total_chapters) * 80)

            if pair.single_mode:
                is_gif = pair.image_path.lower().endswith('.gif')
                kb_note = (
                    " [Ken Burns]"
                    if config.ken_burns and not is_gif and not pair.is_video_input
                    else ""
                )
                report(percent,
                       f"チャプター {i+1}/{total_chapters} を生成中: "
                       f"{pair.base_name}{kb_note}")
            else:
                report(percent,
                       f"チャプター {i+1}/{total_chapters} を生成中: "
                       f"{pair.base_name} [{len(pair.visual_items)}枚]")

            generate_chapter_video(
                pair=pair,
                output_path=chapter_output,
                config=config,
                ffmpeg_path=ffmpeg_path,
                chapter_index=i,
                temp_dir=temp_dir,
            )
            chapter_paths.append(chapter_output)

        check_cancel()
        report(85, "チャプターを結合中...")

        # --- 後処理パイプライン: viz -> BGM の順で適用 ---
        # 後処理が必要かどうかを判定
        has_viz = config.visualizer_enabled
        has_bgm = bool(config.bgm_path) and os.path.isfile(config.bgm_path or '')

        if has_viz or has_bgm:
            # まず一時ファイルに結合
            concat_tmp = os.path.join(temp_dir, 'concat_tmp.mp4')
            concatenate_videos(
                chapter_paths=chapter_paths,
                output_path=concat_tmp,
                ffmpeg_path=ffmpeg_path,
                temp_dir=temp_dir,
            )

            current_tmp = concat_tmp

            # ビジュアライザー適用
            if has_viz:
                report(90, "ビジュアライザーを適用中...")
                viz_tmp = os.path.join(temp_dir, 'viz_tmp.mp4')
                apply_visualizer(
                    input_path=current_tmp,
                    output_path=viz_tmp,
                    config=config,
                    ffmpeg_path=ffmpeg_path,
                )
                current_tmp = viz_tmp

            # BGMミックス適用
            if has_bgm:
                report(95, "BGMをミックス中...")
                # BGMタイミングJSONを読み込んでconfigの値を上書き
                bgm_timing = load_bgm_timing(config.bgm_path)
                bgm_mix_tmp = os.path.join(temp_dir, 'bgm_tmp.mp4')
                mix_bgm_to_video(
                    input_video=current_tmp,
                    output_video=bgm_mix_tmp,
                    bgm_path=config.bgm_path,
                    voice_volume=config.voice_volume,
                    bgm_volume=bgm_timing.get('volume', config.bgm_volume),
                    bgm_start_offset=bgm_timing.get('start_offset', config.bgm_start_offset),
                    bgm_fade_in=bgm_timing.get('fade_in', config.bgm_fade_in),
                    bgm_fade_out=bgm_timing.get('fade_out', config.bgm_fade_out),
                    ffmpeg_path=ffmpeg_path,
                )
                current_tmp = bgm_mix_tmp

            # 最終出力先にコピー
            shutil.copy2(current_tmp, config.output_path)

        else:
            concatenate_videos(
                chapter_paths=chapter_paths,
                output_path=config.output_path,
                ffmpeg_path=ffmpeg_path,
                temp_dir=temp_dir,
            )

        report(100, "完了！")
        return config.output_path

    finally:
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass
