# -*- coding: utf-8 -*-
"""Patch video_generator.py to add video input support"""

with open('video_generator.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find start line (is_gif = ...)
start = None
for i, line in enumerate(lines):
    if "is_gif = pair.image_path.lower().endswith('.gif')" in line:
        start = i
        break

# Find end line (after the RuntimeError block)
end = None
for i in range(start, len(lines)):
    if "FFmpegエラー:\\n{result.stderr[-2000:]}" in lines[i] or "FFmpegエラー:\n{result.stderr[-2000:]}" in lines[i]:
        # Find the closing paren
        for j in range(i, min(i+5, len(lines))):
            if lines[j].strip() == ')':
                end = j + 1
                break
        if end:
            break

print(f"Replacing lines {start+1} to {end}")

new_block = '''\
    from file_scanner import VIDEO_PRIORITY
    is_gif = pair.image_path.lower().endswith('.gif')
    is_video = pair.image_ext in VIDEO_PRIORITY

    # ---- フィルタグラフ構築 ----
    if config.ken_burns and not is_gif and not is_video:
        # ケン・バーンズ効果あり（静止画のみ）
        kb_filter = _build_ken_burns_filter(w, h, fps, duration,
                                            config.ken_burns_zoom, chapter_index)
        scale_filter = (
            f"[0:v]scale={int(w * config.ken_burns_zoom * 1.1)}:{int(h * config.ken_burns_zoom * 1.1)}"
            f":force_original_aspect_ratio=increase,"
            f"crop={int(w * config.ken_burns_zoom * 1.1)}:{int(h * config.ken_burns_zoom * 1.1)},"
            f"{kb_filter},"
            f"setsar=1"
        )
    else:
        # 通常スケール（GIF / 動画 / 静止画）
        scale_filter = (
            f"[0:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,"
            f"setsar=1,fps={fps}"
        )

    # タイトルオーバーレイ
    title_filter = (
        f"drawbox=x=0:y=ih-120:w=iw:h=120:color=black@0.6:t=fill:"
        f"enable=\'between(t,0,{title_dur})\','
        f"drawtext=text=\'{escaped_title}\':"
        f"fontsize={TITLE_FONT_SIZE}:"
        f"fontcolor=white:"
        f"x=(w-text_w)/2:"
        f"y=h-80:"
        f"enable=\'between(t,0,{title_dur})\'"
    )

    # フェード
    fade_out_start = max(0, duration - fade)
    fade_filter = f"fade=t=out:st={fade_out_start:.3f}:d={fade:.3f}"
    fade_in_filter = f"fade=t=in:st=0:d={fade:.3f}"
    vf = f"{scale_filter},{title_filter},{fade_in_filter},{fade_filter}"

    # ---- FFmpeg 引数 ----
    if is_video:
        # 入力動画ファイル:
        #   - 動画の音声トラックは完全に無効化 (-map 0:v:0 のみ使用)
        #   - 音声ファイルの音声のみを使用 (-map 1:a:0)
        #   - 動画が音声より短い場合はループ再生 (-stream_loop -1)
        #   - 音声の長さで切り取る (-t duration)
        args = [
            \'-y\',
            \'-stream_loop\', \'-1\',        # 動画を無限ループ（音声長さで切り取る）
            \'-i\', pair.image_path,         # 入力動画（映像トラックのみ使用）
            \'-i\', pair.audio_path,         # 入力音声（100%使用）
            \'-map\', \'0:v:0\',             # 動画の映像ストリームのみ
            \'-map\', \'1:a:0\',             # 音声ファイルの音声ストリームのみ
            \'-vf\', vf,
            \'-c:v\', \'libx264\', \'-preset\', \'fast\', \'-crf\', \'23\',
            \'-c:a\', \'aac\', \'-b:a\', \'192k\',
            \'-t\', str(duration),           # 音声の長さで切り取る
            \'-pix_fmt\', \'yuv420p\',
            \'-movflags\', \'+faststart\',
            output_path
        ]
    elif is_gif:
        args = [
            \'-y\',
            \'-stream_loop\', \'-1\',
            \'-i\', pair.image_path,
            \'-i\', pair.audio_path,
            \'-vf\', vf,
            \'-c:v\', \'libx264\', \'-preset\', \'fast\', \'-crf\', \'23\',
            \'-c:a\', \'aac\', \'-b:a\', \'192k\',
            \'-t\', str(duration),
            \'-pix_fmt\', \'yuv420p\',
            \'-movflags\', \'+faststart\',
            output_path
        ]
    else:
        # 静止画 (jpg/png/bmp/webp/tiff/avif)
        args = [
            \'-y\',
            \'-loop\', \'1\',
            \'-i\', pair.image_path,
            \'-i\', pair.audio_path,
            \'-vf\', vf,
            \'-c:v\', \'libx264\', \'-preset\', \'fast\', \'-crf\', \'23\',
            \'-c:a\', \'aac\', \'-b:a\', \'192k\',
            \'-t\', str(duration),
            \'-pix_fmt\', \'yuv420p\',
            \'-movflags\', \'+faststart\',
            output_path
        ]
    result = run_ffmpeg(ffmpeg_path, args)
    if result.returncode != 0:
        raise RuntimeError(
            f"チャプター \'{pair.base_name}\' の動画生成に失敗しました。\\n"
            f"FFmpegエラー:\\n{result.stderr[-2000:]}"
        )
'''

new_lines = lines[:start] + [new_block] + lines[end:]

with open('video_generator.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Patch applied successfully")
