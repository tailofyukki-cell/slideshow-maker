# -*- coding: utf-8 -*-
"""
SlideshowMaker CLI mode
Usage:
    python main.py --cli --input <folder> --output <file.mp4> [options]
    SlideshowMaker.exe --cli --input <folder> --output <file.mp4> [options]
"""
import os
import sys
import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="SlideshowMaker",
        description=(
            "SlideshowMaker CLI - Audio+Image/Video pairs to MP4 converter\n"
            "Scans input folder for paired audio and image/video files, "
            "then generates an MP4 slideshow."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  SlideshowMaker.exe --cli --input C:\\Music\\MyAlbum --output C:\\out\\album.mp4

  # With resolution preset
  SlideshowMaker.exe --cli --input ./songs --output ./out.mp4 --preset "1080p縦型"

  # No title overlay, with Ken Burns effect
  SlideshowMaker.exe --cli --input ./songs --output ./out.mp4 --no-title --ken-burns

  # With audio visualizer
  SlideshowMaker.exe --cli --input ./songs --output ./out.mp4 --visualizer waveform

  # List available presets
  SlideshowMaker.exe --cli --list-presets

  # Dry run (scan only, no video generation)
  SlideshowMaker.exe --cli --input ./songs --dry-run
""",
    )

    parser.add_argument(
        "--cli",
        action="store_true",
        help="Run in CLI mode (required to activate CLI mode)",
    )

    # Input / Output
    io_group = parser.add_argument_group("Input / Output")
    io_group.add_argument(
        "--input", "-i",
        metavar="FOLDER",
        help="Input folder containing audio and image/video files",
    )
    io_group.add_argument(
        "--output", "-o",
        metavar="FILE",
        help="Output MP4 file path (default: <input_folder>/output.mp4)",
    )

    # Resolution
    res_group = parser.add_argument_group("Resolution")
    res_group.add_argument(
        "--preset", "-p",
        metavar="PRESET_NAME",
        default=None,
        help=(
            "Resolution preset name. Use --list-presets to see available options. "
            "Default: '1080p 横型 (YouTube/一般)'"
        ),
    )
    res_group.add_argument(
        "--width",
        type=int,
        default=None,
        help="Custom output width in pixels (overrides --preset)",
    )
    res_group.add_argument(
        "--height",
        type=int,
        default=None,
        help="Custom output height in pixels (overrides --preset)",
    )

    # Video options
    vid_group = parser.add_argument_group("Video Options")
    vid_group.add_argument(
        "--no-title",
        action="store_true",
        help="Disable filename title overlay on generated video",
    )
    vid_group.add_argument(
        "--ken-burns",
        action="store_true",
        help="Enable Ken Burns effect (zoom/pan animation) on still images",
    )
    vid_group.add_argument(
        "--fps",
        type=int,
        default=30,
        help="Output video frame rate (default: 30)",
    )
    vid_group.add_argument(
        "--fade",
        type=float,
        default=0.75,
        metavar="SECONDS",
        help="Fade in/out duration in seconds (default: 0.75)",
    )

    # Visualizer
    viz_group = parser.add_argument_group("Audio Visualizer")
    viz_group.add_argument(
        "--visualizer",
        metavar="STYLE",
        default=None,
        choices=["waveform", "freqbar", "spectrum", "vectorscope"],
        help=(
            "Enable audio visualizer watermark. "
            "Choices: waveform, freqbar, spectrum, vectorscope"
        ),
    )
    viz_group.add_argument(
        "--viz-height",
        type=int,
        default=80,
        metavar="PX",
        help="Visualizer bar height in pixels (default: 80)",
    )
    viz_group.add_argument(
        "--viz-opacity",
        type=float,
        default=0.6,
        metavar="0.0-1.0",
        help="Visualizer opacity 0.0-1.0 (default: 0.6)",
    )
    viz_group.add_argument(
        "--viz-color",
        default="#00ffff",
        metavar="COLOR",
        help="Visualizer color in hex format (default: #00ffff)",
    )

    # BGM Mix
    bgm_group = parser.add_argument_group("BGM Mix")
    bgm_group.add_argument(
        "--bgm",
        metavar="FILE",
        default=None,
        help=(
            "BGM audio file to mix with voice. "
            "If not specified, auto-detects _bgm.mp3/wav etc. in input folder."
        ),
    )
    bgm_group.add_argument(
        "--voice-vol",
        type=float,
        default=1.0,
        metavar="0.0-2.0",
        help="Voice audio volume multiplier (default: 1.0)",
    )
    bgm_group.add_argument(
        "--bgm-vol",
        type=float,
        default=0.5,
        metavar="0.0-2.0",
        help="BGM volume multiplier (default: 0.5)",
    )
    bgm_group.add_argument(
        "--bgm-offset",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help="BGM start offset in seconds (default: 0.0)",
    )
    bgm_group.add_argument(
        "--bgm-fade-in",
        type=float,
        default=1.0,
        metavar="SECONDS",
        help="BGM fade-in duration in seconds (default: 1.0)",
    )
    bgm_group.add_argument(
        "--bgm-fade-out",
        type=float,
        default=2.0,
        metavar="SECONDS",
        help="BGM fade-out duration in seconds (default: 2.0)",
    )

    # Utility
    util_group = parser.add_argument_group("Utility")
    util_group.add_argument(
        "--list-presets",
        action="store_true",
        help="List available resolution presets and exit",
    )
    util_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan input folder and show pairs without generating video",
    )
    util_group.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed progress output",
    )

    return parser


def run_cli(args: argparse.Namespace) -> int:
    """
    CLIモードのメイン処理。
    Returns: exit code (0=success, 1=error)
    """
    from video_generator import (
        generate_video, GenerationConfig,
        RESOLUTION_PRESETS, DEFAULT_PRESET, OUTPUT_FILENAME,
        find_folder_bgm,
    )
    from file_scanner import scan_folder

    # --list-presets
    if args.list_presets:
        print("Available resolution presets:")
        for name, (w, h) in RESOLUTION_PRESETS.items():
            marker = " [default]" if name == DEFAULT_PRESET else ""
            print(f"  {name!r:45s} {w} x {h}{marker}")
        return 0

    # --input required for non-utility commands
    if not args.input:
        print("ERROR: --input <folder> is required.", file=sys.stderr)
        print("Use --help for usage information.", file=sys.stderr)
        return 1

    input_folder = os.path.abspath(args.input)
    if not os.path.isdir(input_folder):
        print(f"ERROR: Input folder not found: {input_folder}", file=sys.stderr)
        return 1

    # Scan folder
    print(f"Scanning: {input_folder}")
    scan_result = scan_folder(input_folder)

    if not scan_result.has_complete_pairs:
        print("ERROR: No complete audio+image/video pairs found in the input folder.",
              file=sys.stderr)
        print("  Audio files found:", len(scan_result.audio_only))
        print("  Image/video files found:", len(scan_result.image_only))
        return 1

    # Print scan summary
    pairs = scan_result.complete_pairs
    print(f"Found {len(pairs)} complete pair(s):")
    for i, pair in enumerate(pairs):
        mode = "single" if pair.single_mode else f"multi({len(pair.visual_items)} images)"
        print(f"  [{i+1:3d}] {pair.base_name}  [{mode}]")

    if scan_result.audio_only:
        print(f"  (audio-only, skipped: {len(scan_result.audio_only)})")
    if scan_result.image_only:
        print(f"  (image-only, skipped: {len(scan_result.image_only)})")

    # --dry-run: stop here
    if args.dry_run:
        print("\nDry run complete. No video generated.")
        return 0

    # Resolve output path
    if args.output:
        output_path = os.path.abspath(args.output)
        if not output_path.lower().endswith('.mp4'):
            output_path += '.mp4'
    else:
        output_path = os.path.join(input_folder, OUTPUT_FILENAME)

    # Resolve resolution
    if args.width and args.height:
        w, h = args.width, args.height
        preset_label = f"custom ({w}x{h})"
    elif args.preset:
        # Partial match support (e.g. "1080p縦型" matches "1080p 縦型 (TikTok/Reels)")
        matched = None
        for name in RESOLUTION_PRESETS:
            if args.preset in name or name.startswith(args.preset):
                matched = name
                break
        if matched is None:
            # Exact match fallback
            matched = args.preset if args.preset in RESOLUTION_PRESETS else None
        if matched is None:
            print(f"ERROR: Unknown preset: {args.preset!r}", file=sys.stderr)
            print("Use --list-presets to see available options.", file=sys.stderr)
            return 1
        w, h = RESOLUTION_PRESETS[matched]
        preset_label = matched
    else:
        w, h = RESOLUTION_PRESETS[DEFAULT_PRESET]
        preset_label = DEFAULT_PRESET

    # BGM自動検出
    bgm_path = args.bgm
    if bgm_path:
        bgm_path = os.path.abspath(bgm_path)
        if not os.path.isfile(bgm_path):
            print(f"ERROR: BGM file not found: {bgm_path}", file=sys.stderr)
            return 1
    else:
        # 入力フォルダ内のBGMファイルを自動検出
        bgm_path = find_folder_bgm(input_folder)
        if bgm_path:
            print(f"Auto-detected BGM: {os.path.basename(bgm_path)}")

    # Build config
    config = GenerationConfig(
        pairs=pairs,
        output_path=output_path,
        width=w,
        height=h,
        fps=args.fps,
        fade_duration=args.fade,
        title_overlay=not args.no_title,
        ken_burns=args.ken_burns,
        visualizer_enabled=(args.visualizer is not None),
        visualizer_style=args.visualizer or "waveform",
        visualizer_height=args.viz_height,
        visualizer_opacity=max(0.0, min(1.0, args.viz_opacity)),
        visualizer_color=args.viz_color,
        bgm_path=bgm_path,
        voice_volume=max(0.0, min(2.0, args.voice_vol)),
        bgm_volume=max(0.0, min(2.0, args.bgm_vol)),
        bgm_start_offset=max(0.0, args.bgm_offset),
        bgm_fade_in=max(0.0, args.bgm_fade_in),
        bgm_fade_out=max(0.0, args.bgm_fade_out),
    )

    # Print config summary
    print(f"\nConfiguration:")
    print(f"  Output       : {output_path}")
    print(f"  Resolution   : {preset_label} ({w}x{h})")
    print(f"  FPS          : {args.fps}")
    print(f"  Fade         : {args.fade}s")
    print(f"  Title overlay: {'ON' if config.title_overlay else 'OFF'}")
    print(f"  Ken Burns    : {'ON' if config.ken_burns else 'OFF'}")
    if config.visualizer_enabled:
        print(f"  Visualizer   : {config.visualizer_style} "
              f"(height={config.visualizer_height}px, opacity={config.visualizer_opacity:.0%})")
    if config.bgm_path:
        print(f"  BGM          : {os.path.basename(config.bgm_path)} "
              f"(voice={config.voice_volume:.1f}x, bgm={config.bgm_volume:.1f}x, "
              f"offset={config.bgm_start_offset:.1f}s, "
              f"fade-in={config.bgm_fade_in:.1f}s, fade-out={config.bgm_fade_out:.1f}s)")
    print()

    # Check output path
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        print(f"ERROR: Output directory not found: {output_dir}", file=sys.stderr)
        return 1

    if os.path.exists(output_path):
        print(f"WARNING: Output file already exists and will be overwritten: {output_path}")

    # Progress callback
    def on_progress(percent: int, message: str):
        if args.verbose or percent in (0, 25, 50, 75, 85, 92, 100):
            print(f"  [{percent:3d}%] {message}")
        else:
            # Simple progress bar on same line
            bar_len = 40
            filled = int(bar_len * percent / 100)
            bar = "#" * filled + "-" * (bar_len - filled)
            print(f"\r  [{bar}] {percent:3d}%  {message[:40]:<40}", end="", flush=True)

    # Generate
    print("Generating video...")
    try:
        result_path = generate_video(
            config=config,
            progress_callback=on_progress,
        )
        print()  # newline after progress bar
        size = os.path.getsize(result_path)
        print(f"\nDone! Output: {result_path}")
        print(f"File size: {size:,} bytes ({size / 1024 / 1024:.1f} MB)")
        return 0
    except FileNotFoundError as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        return 1
    except RuntimeError as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\nUnexpected error: {e}", file=sys.stderr)
        return 1
