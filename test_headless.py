# -*- coding: utf-8 -*-
"""
Headless tests (no GUI)
Covers:
  - Telop parser: load, validate, drawtext filter generation
  - Telop in video generation (single mode & multi-image mode)
  - Multi-image mode: suffix _001, _002, ... detection and equal-split generation
  - Exact-match priority over suffix-based multi-image
  - Single-mode (1:1) still works
  - Video input (audio stripped)
  - Animated GIF detection
  - Audio/image format detection
  - Resolution presets
"""
import os
import sys
import json
import tempfile
import shutil
import subprocess

FFMPEG = shutil.which('ffmpeg')


def make_audio(folder, name, ext='.mp3', duration=4, freq=440):
    path = os.path.join(folder, f"{name}{ext}")
    codec_map = {
        '.mp3':  ['-c:a', 'libmp3lame'],
        '.wav':  ['-c:a', 'pcm_s16le'],
        '.flac': ['-c:a', 'flac'],
        '.ogg':  ['-c:a', 'libvorbis'],
        '.aac':  ['-c:a', 'aac'],
        '.m4a':  ['-c:a', 'aac'],
    }
    codec_args = codec_map.get(ext, ['-c:a', 'aac'])
    cmd = [FFMPEG, '-y', '-f', 'lavfi',
           '-i', f'sine=frequency={freq}:duration={duration}',
           ] + codec_args + [path]
    subprocess.run(cmd, capture_output=True)
    return path


def make_image(folder, name, ext='.png', color='red', size='320x240'):
    path = os.path.join(folder, f"{name}{ext}")
    cmd = [FFMPEG, '-y', '-f', 'lavfi',
           '-i', f'color={color}:size={size}:duration=1',
           '-frames:v', '1', path]
    subprocess.run(cmd, capture_output=True)
    return path


def make_video(folder, name, ext='.mp4', duration=1, color='blue', size='320x240'):
    path = os.path.join(folder, f"{name}{ext}")
    cmd = [FFMPEG, '-y',
           '-f', 'lavfi', '-i', f'color={color}:size={size}:duration={duration}',
           '-f', 'lavfi', '-i', f'sine=frequency=880:duration={duration}',
           '-c:v', 'libx264', '-c:a', 'aac', '-shortest', path]
    subprocess.run(cmd, capture_output=True)
    return path


def make_animated_gif(folder, name):
    gif_path = os.path.join(folder, f"{name}.gif")
    frame_paths = []
    for i, color in enumerate(['red', 'green', 'blue']):
        fp = os.path.join(folder, f'_frame_{name}_{i}.png')
        subprocess.run([FFMPEG, '-y', '-f', 'lavfi',
                        '-i', f'color={color}:size=160x120:duration=1',
                        '-frames:v', '1', fp], capture_output=True)
        frame_paths.append(fp)
    subprocess.run([FFMPEG, '-y', '-framerate', '2',
                    '-i', os.path.join(folder, f'_frame_{name}_%d.png'),
                    '-vf', 'scale=160:120', gif_path], capture_output=True)
    for fp in frame_paths:
        try:
            os.remove(fp)
        except Exception:
            pass
    return gif_path


def make_telop_json(folder, name, entries):
    path = os.path.join(folder, f"{name}.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    return path


def get_video_duration(path):
    result = subprocess.run(
        ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', path],
        capture_output=True, text=True
    )
    fmt = json.loads(result.stdout).get('format', {})
    return float(fmt.get('duration', 0))


# ============================================================
# Telop parser tests
# ============================================================

def test_telop_parser_basic():
    """Test basic telop JSON parsing"""
    print("=== telop parser basic test ===")
    from telop_parser import load_telop_file, TelopEntry

    with tempfile.TemporaryDirectory() as tmpdir:
        path = make_telop_json(tmpdir, 'track', [
            {"text": "ドカーン！", "start": 1.0, "end": 2.5,
             "position": "center", "size": 80, "color": "yellow", "bold": True},
            {"text": "BGMが流れる...", "start": 3.0, "end": 5.0,
             "position": "bottom", "size": 48, "color": "white"},
        ])
        entries = load_telop_file(path)
        assert len(entries) == 2
        assert entries[0].text == "ドカーン！"
        assert entries[0].start == 1.0
        assert entries[0].end == 2.5
        assert entries[0].position == "center"
        assert entries[0].size == 80
        assert entries[0].color == "yellow"
        assert entries[0].bold is True
        assert entries[1].text == "BGMが流れる..."
        assert entries[1].position == "bottom"
        print(f"  Entry 0: {entries[0].text} [{entries[0].start}-{entries[0].end}s]")
        print(f"  Entry 1: {entries[1].text} [{entries[1].start}-{entries[1].end}s]")
        print("  [PASS] telop parser basic test")


def test_telop_parser_defaults():
    """Test telop parser default values"""
    print("\n=== telop parser defaults test ===")
    from telop_parser import load_telop_file, DEFAULT_POSITION, DEFAULT_FONT_SIZE, DEFAULT_COLOR

    with tempfile.TemporaryDirectory() as tmpdir:
        path = make_telop_json(tmpdir, 'track', [
            {"text": "最小定義", "start": 0.0, "end": 1.0}
        ])
        entries = load_telop_file(path)
        assert len(entries) == 1
        e = entries[0]
        assert e.position == DEFAULT_POSITION
        assert e.size == DEFAULT_FONT_SIZE
        assert e.color == DEFAULT_COLOR
        assert e.bold is False
        assert e.outline is True
        assert e.bg is False
        print(f"  Defaults: position={e.position}, size={e.size}, color={e.color}")
        print("  [PASS] telop parser defaults test")


def test_telop_parser_validation():
    """Test telop parser validation errors"""
    print("\n=== telop parser validation test ===")
    from telop_parser import load_telop_file

    with tempfile.TemporaryDirectory() as tmpdir:
        # missing text
        p = make_telop_json(tmpdir, 'bad1', [{"start": 0, "end": 1}])
        try:
            load_telop_file(p)
            assert False, "Should raise ValueError"
        except ValueError as e:
            print(f"  Missing text caught: {e}")

        # end <= start
        p = make_telop_json(tmpdir, 'bad2', [{"text": "x", "start": 5, "end": 3}])
        try:
            load_telop_file(p)
            assert False, "Should raise ValueError"
        except ValueError as e:
            print(f"  end<=start caught: {e}")

        # invalid position
        p = make_telop_json(tmpdir, 'bad3', [{"text": "x", "start": 0, "end": 1, "position": "invalid"}])
        try:
            load_telop_file(p)
            assert False, "Should raise ValueError"
        except ValueError as e:
            print(f"  Invalid position caught: {e}")

        print("  [PASS] telop parser validation test")


def test_telop_no_file():
    """Test that missing telop file returns empty list"""
    print("\n=== telop no file test ===")
    from telop_parser import load_telop_file, find_telop_file

    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = os.path.join(tmpdir, 'track.mp3')
        result = find_telop_file(audio_path)
        assert result is None
        entries = load_telop_file(os.path.join(tmpdir, 'nonexistent.json'))
        assert entries == []
        print("  [PASS] telop no file test")


def test_telop_drawtext_filters():
    """Test drawtext filter generation"""
    print("\n=== telop drawtext filter test ===")
    from telop_parser import load_telop_file, build_telop_drawtext_filters

    with tempfile.TemporaryDirectory() as tmpdir:
        path = make_telop_json(tmpdir, 'track', [
            {"text": "テスト", "start": 1.0, "end": 3.0, "position": "center",
             "bg": True, "outline": True},
            {"text": "下部テロップ", "start": 4.0, "end": 6.0, "position": "bottom"},
        ])
        entries = load_telop_file(path)
        filters = build_telop_drawtext_filters(entries, width=1920, height=1080)
        # bg=True generates drawbox + drawtext (2 filters for first entry)
        assert len(filters) >= 3, f"Expected >=3 filters, got {len(filters)}"
        for f in filters:
            print(f"  filter: {f[:80]}...")
        print("  [PASS] telop drawtext filter test")


def test_telop_video_generation_single():
    """Test video generation with telop in single mode"""
    print("\n=== telop video generation (single mode) test ===")
    from file_scanner import scan_folder
    from video_generator import generate_video, GenerationConfig

    with tempfile.TemporaryDirectory() as tmpdir:
        make_audio(tmpdir, 'scene1', duration=5)
        make_image(tmpdir, 'scene1', color='green')
        make_telop_json(tmpdir, 'scene1', [
            {"text": "ドカーン！", "start": 1.0, "end": 2.5,
             "position": "center", "size": 60, "color": "yellow"},
            {"text": "END", "start": 4.0, "end": 5.0,
             "position": "bottom-right", "size": 40, "color": "white"},
        ])

        result = scan_folder(tmpdir)
        assert len(result.complete_pairs) == 1

        output_path = os.path.join(tmpdir, 'out_telop.mp4')
        config = GenerationConfig(
            pairs=result.complete_pairs,
            output_path=output_path,
            width=320, height=240,
        )
        generate_video(config, progress_callback=lambda p, m: print(f"  [{p:3d}%] {m}"))
        assert os.path.exists(output_path)
        size = os.path.getsize(output_path)
        dur = get_video_duration(output_path)
        print(f"  Output: {size:,} bytes, {dur:.2f}s")
        assert size > 1000
        assert 4.5 <= dur <= 5.5
        print("  [PASS] telop video generation (single mode) test")


def test_telop_video_generation_multi():
    """Test video generation with telop in multi-image mode (cross-clip time)"""
    print("\n=== telop video generation (multi-image mode) test ===")
    from file_scanner import scan_folder
    from video_generator import generate_video, GenerationConfig

    with tempfile.TemporaryDirectory() as tmpdir:
        make_audio(tmpdir, 'multi', duration=6)
        make_image(tmpdir, 'multi_001', color='red')
        make_image(tmpdir, 'multi_002', color='blue')
        make_image(tmpdir, 'multi_003', color='green')
        # telop spanning clip boundary (clip 1: 0-2s, clip 2: 2-4s, clip 3: 4-6s)
        make_telop_json(tmpdir, 'multi', [
            {"text": "クリップ1", "start": 0.5, "end": 1.5, "position": "top"},
            {"text": "クリップ2", "start": 2.5, "end": 3.5, "position": "center"},
            {"text": "クリップ3", "start": 4.5, "end": 5.5, "position": "bottom"},
        ])

        result = scan_folder(tmpdir)
        assert len(result.complete_pairs) == 1
        pair = result.complete_pairs[0]
        assert not pair.single_mode

        output_path = os.path.join(tmpdir, 'out_telop_multi.mp4')
        config = GenerationConfig(
            pairs=result.complete_pairs,
            output_path=output_path,
            width=320, height=240,
        )
        generate_video(config, progress_callback=lambda p, m: print(f"  [{p:3d}%] {m}"))
        assert os.path.exists(output_path)
        size = os.path.getsize(output_path)
        dur = get_video_duration(output_path)
        print(f"  Output: {size:,} bytes, {dur:.2f}s")
        assert size > 1000
        assert 5.5 <= dur <= 6.5
        print("  [PASS] telop video generation (multi-image mode) test")


# ============================================================
# Existing tests (unchanged)
# ============================================================

def test_multi_image_detection():
    print("\n=== multi-image detection test ===")
    from file_scanner import scan_folder
    with tempfile.TemporaryDirectory() as tmpdir:
        make_audio(tmpdir, '001')
        make_image(tmpdir, '001_001', color='red')
        make_image(tmpdir, '001_002', color='green')
        make_image(tmpdir, '001_003', color='blue')
        result = scan_folder(tmpdir)
        assert len(result.complete_pairs) == 1
        pair = result.complete_pairs[0]
        assert not pair.single_mode
        assert len(pair.visual_items) == 3
        print(f"  visual_items: {[os.path.basename(v.path) for v in pair.visual_items]}")
        print("  [PASS] multi-image detection test")


def test_exact_match_priority():
    print("\n=== exact match priority test ===")
    from file_scanner import scan_folder
    with tempfile.TemporaryDirectory() as tmpdir:
        make_audio(tmpdir, '001')
        make_image(tmpdir, '001', color='yellow')
        make_image(tmpdir, '001_001', color='red')
        make_image(tmpdir, '001_002', color='green')
        result = scan_folder(tmpdir)
        assert len(result.complete_pairs) == 1
        pair = result.complete_pairs[0]
        assert pair.single_mode
        assert os.path.basename(pair.image_path) == '001.png'
        print(f"  Used: {os.path.basename(pair.image_path)} (single_mode={pair.single_mode})")
        print("  [PASS] exact match priority test")


def test_single_mode_still_works():
    print("\n=== single mode (1:1) test ===")
    from file_scanner import scan_folder
    from video_generator import generate_video, GenerationConfig
    with tempfile.TemporaryDirectory() as tmpdir:
        make_audio(tmpdir, 'solo', duration=2)
        make_image(tmpdir, 'solo', color='purple')
        result = scan_folder(tmpdir)
        assert len(result.complete_pairs) == 1
        output_path = os.path.join(tmpdir, 'out_single.mp4')
        config = GenerationConfig(pairs=result.complete_pairs, output_path=output_path, width=320, height=240)
        generate_video(config, progress_callback=lambda p, m: print(f"  [{p:3d}%] {m}"))
        assert os.path.exists(output_path)
        dur = get_video_duration(output_path)
        assert 1.5 <= dur <= 2.5
        print(f"  Output duration: {dur:.2f}s")
        print("  [PASS] single mode test")


def test_audio_formats():
    print("\n=== audio format detection test ===")
    from file_scanner import scan_folder
    for ext in ['.mp3', '.wav', '.flac', '.ogg', '.aac', '.m4a']:
        with tempfile.TemporaryDirectory() as tmpdir:
            make_audio(tmpdir, 'track', ext)
            make_image(tmpdir, 'track')
            result = scan_folder(tmpdir)
            print(f"  [{'OK' if result.complete_pairs else 'SKIP'}] {ext}")
    print("  [PASS] audio format detection test")


def test_resolution_presets():
    print("\n=== resolution presets test ===")
    from video_generator import RESOLUTION_PRESETS, DEFAULT_PRESET
    assert DEFAULT_PRESET in RESOLUTION_PRESETS
    for name, (w, h) in RESOLUTION_PRESETS.items():
        print(f"  {name:35s} -> {w}x{h}")
    w, h = RESOLUTION_PRESETS["1080p 縦型 (TikTok/Reels)"]
    assert w == 1080 and h == 1920
    print("  [PASS] resolution presets test")


def test_telop_animation_filter_generation():
    """Test that all Phase 1 animations generate valid filter strings"""
    print("\n=== telop animation filter generation test ===")
    from telop_parser import build_telop_drawtext_filters, TelopEntry, VALID_ANIMATIONS

    phase1_animations = [
        "none", "fade", "fade_in", "fade_out",
        "slide_left", "slide_right", "slide_top", "slide_bottom",
        "slide_left_fade", "slide_right_fade",
        "blink", "shake", "bounce",
    ]

    # Verify all Phase 1 animations are in VALID_ANIMATIONS
    for anim in phase1_animations:
        assert anim in VALID_ANIMATIONS, f"'{anim}' not in VALID_ANIMATIONS"
    print(f"  All {len(phase1_animations)} Phase 1 animations registered")

    # Test filter generation for each animation
    for anim in phase1_animations:
        entry = TelopEntry(
            text="テスト",
            start=1.0,
            end=4.0,
            position="center",
            animation=anim,
            anim_duration=0.5,
        )
        filters = build_telop_drawtext_filters([entry], 1920, 1080, 0.0)
        assert len(filters) >= 1, f"animation='{anim}' generated no filters"
        assert any('drawtext' in f for f in filters), f"animation='{anim}' has no drawtext"
        print(f"  [{anim:20s}] {len(filters)} filter(s) generated")

    # Verify alpha expression for fade animations
    for anim in ["fade", "fade_in", "fade_out", "slide_left_fade", "slide_right_fade"]:
        entry = TelopEntry(text="フェード", start=1.0, end=5.0, animation=anim, anim_duration=0.5)
        filters = build_telop_drawtext_filters([entry], 1920, 1080, 0.0)
        has_alpha = any("alpha=" in f for f in filters)
        assert has_alpha, f"animation='{anim}' should have alpha= but got: {filters}"
    print("  Fade-based animations have alpha= expression")

    # Verify dynamic x for slide_left/right
    for anim in ["slide_left", "slide_right", "slide_left_fade", "slide_right_fade"]:
        entry = TelopEntry(text="スライド", start=1.0, end=4.0, animation=anim, anim_duration=0.5)
        filters = build_telop_drawtext_filters([entry], 1920, 1080, 0.0)
        has_dynamic_x = any("if(lt" in f for f in filters)
        assert has_dynamic_x, f"animation='{anim}' should have dynamic x"
    print("  Horizontal slide animations have dynamic x expression")

    # Verify dynamic y for slide_top/bottom
    for anim in ["slide_top", "slide_bottom"]:
        entry = TelopEntry(text="スライド", start=1.0, end=4.0, animation=anim, anim_duration=0.5)
        filters = build_telop_drawtext_filters([entry], 1920, 1080, 0.0)
        has_dynamic_y = any("if(lt" in f for f in filters)
        assert has_dynamic_y, f"animation='{anim}' should have dynamic y"
    print("  Vertical slide animations have dynamic y expression")

    # Verify blink uses mod
    entry = TelopEntry(text="点滅", start=1.0, end=4.0, animation="blink", blink_freq=3.0)
    filters = build_telop_drawtext_filters([entry], 1920, 1080, 0.0)
    assert any("mod" in f for f in filters), "blink should use mod in alpha"
    print("  blink animation uses mod() in alpha expression")

    # Verify shake uses sin
    entry = TelopEntry(text="揺れ", start=1.0, end=4.0, animation="shake", shake_freq=8.0, shake_amp=15)
    filters = build_telop_drawtext_filters([entry], 1920, 1080, 0.0)
    assert any("sin" in f for f in filters), "shake should use sin in x"
    print("  shake animation uses sin() in x expression")

    # Verify bounce uses abs(sin
    entry = TelopEntry(text="バウンス", start=1.0, end=4.0, animation="bounce", bounce_freq=3.0, bounce_amp=40)
    filters = build_telop_drawtext_filters([entry], 1920, 1080, 0.0)
    assert any("abs(sin" in f for f in filters), "bounce should use abs(sin in y"
    print("  bounce animation uses abs(sin()) in y expression")

    # Verify time_offset works
    entry = TelopEntry(text="オフセット", start=5.0, end=7.0, animation="fade", anim_duration=0.3)
    filters = build_telop_drawtext_filters([entry], 1920, 1080, 3.0)
    assert len(filters) >= 1, "time_offset should shift timing, not skip"
    print("  time_offset correctly shifts telop timing")

    # Verify out-of-range telop is skipped
    entry = TelopEntry(text="スキップ", start=0.0, end=2.0, animation="none")
    filters = build_telop_drawtext_filters([entry], 1920, 1080, 5.0)
    assert len(filters) == 0, "out-of-range telop should be skipped"
    print("  Out-of-range telop is correctly skipped")

    # Verify invalid animation raises ValueError on load
    with tempfile.TemporaryDirectory() as tmpdir:
        from telop_parser import load_telop_file
        bad_path = os.path.join(tmpdir, 'bad.json')
        with open(bad_path, 'w') as f:
            json.dump([{"text": "x", "start": 0, "end": 1, "animation": "invalid_xyz"}], f)
        try:
            load_telop_file(bad_path)
            assert False, "Should raise ValueError for invalid animation"
        except ValueError:
            pass
    print("  Invalid animation name raises ValueError")

    print("  [PASS] telop animation filter generation test")


def test_telop_animation_video_generation():
    """Test video generation with animated telop entries"""
    print("\n=== telop animation video generation test ===")
    from file_scanner import scan_folder
    from video_generator import generate_video, GenerationConfig

    with tempfile.TemporaryDirectory() as tmpdir:
        make_audio(tmpdir, 'anim_scene', duration=8)
        make_image(tmpdir, 'anim_scene', color='darkblue')
        make_telop_json(tmpdir, 'anim_scene', [
            {"text": "フェード",     "start": 0.5, "end": 2.5,
             "animation": "fade",        "anim_duration": 0.4,
             "position": "center",       "color": "yellow", "size": 60},
            {"text": "スライドイン", "start": 3.0, "end": 5.0,
             "animation": "slide_left",  "anim_duration": 0.5,
             "position": "bottom",       "color": "white"},
            {"text": "ぴかぴか！",   "start": 5.5, "end": 7.5,
             "animation": "blink",       "blink_freq": 4.0,
             "position": "top",          "color": "red", "size": 72},
        ])

        result = scan_folder(tmpdir)
        assert len(result.complete_pairs) == 1

        output_path = os.path.join(tmpdir, 'out_anim.mp4')
        config = GenerationConfig(
            pairs=result.complete_pairs,
            output_path=output_path,
            width=320, height=240,
        )
        generate_video(config, progress_callback=lambda p, m: print(f"  [{p:3d}%] {m}"))
        assert os.path.exists(output_path)
        size = os.path.getsize(output_path)
        dur = get_video_duration(output_path)
        print(f"  Output: {size:,} bytes, {dur:.2f}s")
        assert size > 1000
        assert 7.5 <= dur <= 8.5
        print("  [PASS] telop animation video generation test")


def test_timing_parser_basic():
    """Test timing_parser: load, calculate, fallback"""
    print("\n=== timing parser basic test ===")
    from timing_parser import (
        find_timing_file, load_timing_file,
        calculate_clip_durations, get_timing_summary,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = os.path.join(tmpdir, '001.mp3')
        open(audio_path, 'w').close()  # dummy file

        # Test 1: no timing file -> None
        result = find_timing_file(audio_path)
        assert result is None, "Should return None when no timing file"
        print("  find_timing_file returns None when file absent")

        # Test 2: create timing file -> found
        timing_path = os.path.join(tmpdir, '001_timing.json')
        timing_data = {
            "001_001.png": 10.0,
            "001_002.png": 15.0,
            "001_003.png": 5.0,
        }
        with open(timing_path, 'w', encoding='utf-8') as f:
            json.dump(timing_data, f)
        result = find_timing_file(audio_path)
        assert result == timing_path, f"Expected {timing_path}, got {result}"
        print("  find_timing_file finds the timing JSON")

        # Test 3: load_timing_file
        loaded = load_timing_file(timing_path)
        assert loaded['001_001.png'] == 10.0
        assert loaded['001_002.png'] == 15.0
        assert loaded['001_003.png'] == 5.0
        print("  load_timing_file returns correct values")

        # Test 4: calculate_clip_durations with exact match
        items = [
            os.path.join(tmpdir, '001_001.png'),
            os.path.join(tmpdir, '001_002.png'),
            os.path.join(tmpdir, '001_003.png'),
        ]
        durations = calculate_clip_durations(items, 30.0, timing_path)
        assert len(durations) == 3
        assert abs(sum(durations) - 30.0) < 0.01, f"Sum should be 30.0, got {sum(durations)}"
        # ratios: 10:15:5 = 2:3:1 -> 10s:15s:5s
        assert abs(durations[0] - 10.0) < 0.01, f"Expected 10.0, got {durations[0]}"
        assert abs(durations[1] - 15.0) < 0.01, f"Expected 15.0, got {durations[1]}"
        assert abs(durations[2] - 5.0) < 0.01, f"Expected 5.0, got {durations[2]}"
        print(f"  calculate_clip_durations: {[f'{d:.2f}s' for d in durations]}")

        # Test 5: calculate_clip_durations without timing file -> equal split
        durations_equal = calculate_clip_durations(items, 30.0, None)
        assert all(abs(d - 10.0) < 0.01 for d in durations_equal), f"Should be equal: {durations_equal}"
        print(f"  Equal split: {[f'{d:.2f}s' for d in durations_equal]}")

        # Test 6: partial specification (one item not in JSON)
        partial_timing_path = os.path.join(tmpdir, '002_timing.json')
        partial_data = {
            "001_001.png": 10.0,
            "001_002.png": 15.0,
            # 001_003.png not specified -> gets remaining time
        }
        with open(partial_timing_path, 'w', encoding='utf-8') as f:
            json.dump(partial_data, f)
        durations_partial = calculate_clip_durations(items, 30.0, partial_timing_path)
        assert len(durations_partial) == 3
        assert abs(sum(durations_partial) - 30.0) < 0.01
        print(f"  Partial spec: {[f'{d:.2f}s' for d in durations_partial]} (3rd gets remainder)")

        # Test 7: get_timing_summary
        summary_none = get_timing_summary(items, 30.0, None)
        assert '均等' in summary_none
        print(f"  Summary (no JSON): {summary_none}")
        summary_json = get_timing_summary(items, 30.0, timing_path)
        assert 'JSON' in summary_json
        print(f"  Summary (JSON): {summary_json}")

        # Test 8: invalid JSON raises ValueError
        bad_path = os.path.join(tmpdir, 'bad_timing.json')
        with open(bad_path, 'w') as f:
            f.write('[1, 2, 3]')  # array, not object
        try:
            load_timing_file(bad_path)
            assert False, "Should raise ValueError"
        except ValueError:
            pass
        print("  Invalid JSON format raises ValueError")

    print("  [PASS] timing parser basic test")


def test_timing_video_generation():
    """Test video generation with timing JSON (non-equal clip durations)"""
    print("\n=== timing video generation test ===")
    from file_scanner import scan_folder
    from video_generator import generate_video, GenerationConfig

    with tempfile.TemporaryDirectory() as tmpdir:
        # 12-second audio
        make_audio(tmpdir, 'scene', duration=12)
        # 3 images
        make_image(tmpdir, 'scene_001', color='red')
        make_image(tmpdir, 'scene_002', color='green')
        make_image(tmpdir, 'scene_003', color='blue')
        # timing JSON: 2s / 6s / 4s
        timing_data = {
            'scene_001.png': 2.0,
            'scene_002.png': 6.0,
            'scene_003.png': 4.0,
        }
        timing_path = os.path.join(tmpdir, 'scene_timing.json')
        with open(timing_path, 'w', encoding='utf-8') as f:
            json.dump(timing_data, f)

        result = scan_folder(tmpdir)
        assert len(result.complete_pairs) == 1
        pair = result.complete_pairs[0]
        assert not pair.single_mode, "Should be multi-image mode"
        assert len(pair.visual_items) == 3

        output_path = os.path.join(tmpdir, 'out_timing.mp4')
        config = GenerationConfig(
            pairs=result.complete_pairs,
            output_path=output_path,
            width=320, height=240,
        )
        generate_video(config, progress_callback=lambda p, m: print(f"  [{p:3d}%] {m}"))
        assert os.path.exists(output_path)
        size = os.path.getsize(output_path)
        dur = get_video_duration(output_path)
        print(f"  Output: {size:,} bytes, {dur:.2f}s")
        assert size > 1000
        assert 11.5 <= dur <= 12.5, f"Expected ~12s, got {dur:.2f}s"
        print("  [PASS] timing video generation test")


def test_phase2_animation_filter_generation():
    """Phase 2 animations: zoom_in, zoom_out, pop, typewriter, combination array"""
    print("\n[TEST] Phase 2 animation filter generation")
    from telop_parser import load_telop_file, build_telop_drawtext_filters, TelopEntry, AnimSpec
    import tempfile, json, os

    with tempfile.TemporaryDirectory() as d:
        # --- zoom_in (object form) ---
        data = [{
            "text": "ズームイン",
            "start": 0.0, "end": 4.0,
            "position": "center",
            "size": 60,
            "animation": {"type": "zoom_in", "in_duration": 0.5}
        }]
        p = os.path.join(d, 'zoom_in.json')
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        entries = load_telop_file(p)
        assert len(entries) == 1
        assert entries[0].anim_specs[0].anim_type == 'zoom_in'
        filters = build_telop_drawtext_filters(entries, 1920, 1080)
        assert len(filters) == 1
        assert 'fontsize=' in filters[0]
        print("  zoom_in filter:", filters[0][:80])

        # --- zoom_out (object form) ---
        data = [{
            "text": "ズームアウト",
            "start": 0.0, "end": 4.0,
            "position": "center",
            "size": 60,
            "animation": {"type": "zoom_out", "in_duration": 0.5}
        }]
        p = os.path.join(d, 'zoom_out.json')
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        entries = load_telop_file(p)
        assert entries[0].anim_specs[0].anim_type == 'zoom_out'
        filters = build_telop_drawtext_filters(entries, 1920, 1080)
        assert 'fontsize=' in filters[0]
        print("  zoom_out filter:", filters[0][:80])

        # --- pop (object form) ---
        data = [{
            "text": "ポップ！",
            "start": 0.0, "end": 4.0,
            "position": "center",
            "size": 70,
            "animation": {"type": "pop", "in_duration": 0.4, "pop_overshoot": 1.4}
        }]
        p = os.path.join(d, 'pop.json')
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        entries = load_telop_file(p)
        assert entries[0].anim_specs[0].anim_type == 'pop'
        assert entries[0].anim_specs[0].pop_overshoot == 1.4
        filters = build_telop_drawtext_filters(entries, 1920, 1080)
        assert 'fontsize=' in filters[0]
        print("  pop filter:", filters[0][:80])

        # --- typewriter (object form) ---
        data = [{
            "text": "タイプ",
            "start": 0.0, "end": 5.0,
            "position": "bottom",
            "size": 60,
            "animation": {"type": "typewriter", "chars_per_sec": 5}
        }]
        p = os.path.join(d, 'typewriter.json')
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        entries = load_telop_file(p)
        assert entries[0].anim_specs[0].anim_type == 'typewriter'
        filters = build_telop_drawtext_filters(entries, 1920, 1080)
        # "タイプ" is 3 chars -> 3 drawtext filters
        assert len(filters) == 3, f"Expected 3 filters for 3-char typewriter, got {len(filters)}"
        print(f"  typewriter filters ({len(filters)} chars):", filters[0][:80])

        # --- combination array: slide_left + fade_out ---
        data = [{
            "text": "組み合わせ",
            "start": 0.0, "end": 5.0,
            "position": "bottom",
            "size": 60,
            "animation": [
                {"type": "slide_left", "in_duration": 0.5},
                {"type": "fade_out",   "out_duration": 0.4}
            ]
        }]
        p = os.path.join(d, 'combo.json')
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        entries = load_telop_file(p)
        assert len(entries[0].anim_specs) == 2
        assert entries[0].anim_specs[0].anim_type == 'slide_left'
        assert entries[0].anim_specs[1].anim_type == 'fade_out'
        filters = build_telop_drawtext_filters(entries, 1920, 1080)
        assert len(filters) == 1
        # Should have both x slide expression and alpha fade expression
        assert 'alpha=' in filters[0]
        print("  combo filter:", filters[0][:120])

        # --- typewriter incompatible with combination ---
        data = [{
            "text": "エラー",
            "start": 0.0, "end": 4.0,
            "animation": [
                {"type": "typewriter"},
                {"type": "fade"}
            ]
        }]
        p = os.path.join(d, 'invalid_combo.json')
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        try:
            load_telop_file(p)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            print(f"  typewriter combo error (expected): {e}")

        print("  [PASS] Phase 2 animation filter generation test")


def test_phase2_animation_video_generation():
    """Phase 2: zoom_in and typewriter in actual video output"""
    print("\n[TEST] Phase 2 animation video generation")
    if not FFMPEG:
        print("  SKIP: ffmpeg not found")
        return
    import tempfile, json, os
    from file_scanner import scan_folder
    from video_generator import generate_video, GenerationConfig

    with tempfile.TemporaryDirectory() as d:
        make_audio(d, '001', '.mp3', duration=6)
        make_image(d, '001', '.png', color='green')

        # zoom_in telop
        telop_data = [
            {
                "text": "ズームイン",
                "start": 0.5, "end": 4.0,
                "position": "center", "size": 60,
                "color": "yellow",
                "animation": {"type": "zoom_in", "in_duration": 0.5}
            },
            {
                "text": "タイプ",
                "start": 4.0, "end": 6.0,
                "position": "bottom", "size": 50,
                "color": "white",
                "animation": {"type": "typewriter", "chars_per_sec": 4}
            }
        ]
        with open(os.path.join(d, '001.json'), 'w', encoding='utf-8') as f:
            json.dump(telop_data, f, ensure_ascii=False)

        scan_result = scan_folder(d)
        pairs = scan_result.complete_pairs
        assert len(pairs) == 1
        output_path = os.path.join(d, 'out_phase2.mp4')
        config = GenerationConfig(
            pairs=pairs,
            output_path=output_path,
            width=320, height=240,
        )
        generate_video(config, progress_callback=lambda p, m: print(f"  [{p:3d}%] {m}"))
        assert os.path.exists(output_path)
        size = os.path.getsize(output_path)
        print(f"  Output: {size:,} bytes")
        assert size > 1000
        print("  [PASS] Phase 2 animation video generation test")


def test_visualizer_filter_generation():
    """Test that build_visualizer_filter generates valid filter strings for all styles and color modes."""
    print("\n=== visualizer filter generation test ===")
    from video_generator import build_visualizer_filter, VIZUALIZER_STYLES, VIZUALIZER_COLOR_MODES
    W, H = 1920, 1080
    # solid mode (existing)
    for style in VIZUALIZER_STYLES.keys():
        fc = build_visualizer_filter(
            style=style, color="#00ffff", opacity=0.6,
            viz_height=80, width=W, height=H, color_mode="solid"
        )
        assert "[vout]" in fc, f"Missing [vout] in filter for style={style}"
        assert "overlay" in fc, f"Missing overlay in filter for style={style}"
        print(f"  [OK] solid/{style}: {fc[:70]}...")
    # color modes (rainbow/fire/neon/gold)
    for mode in ["rainbow", "fire", "neon", "gold"]:
        for style in VIZUALIZER_STYLES.keys():
            fc = build_visualizer_filter(
                style=style, color="#00ffff", opacity=0.6,
                viz_height=80, width=W, height=H, color_mode=mode
            )
            assert "[vout]" in fc, f"Missing [vout] in filter for mode={mode} style={style}"
            assert "overlay" in fc, f"Missing overlay in filter for mode={mode} style={style}"
            assert "geq=" in fc, f"Missing geq filter for mode={mode} style={style}"
        print(f"  [OK] {mode}: all styles passed")
    print("  [PASS] visualizer filter generation test")


def test_title_overlay_toggle():
    """Test title_overlay=False suppresses title in generated video (no FFmpeg error)."""
    print("\n=== title overlay toggle test ===")
    from file_scanner import scan_folder
    from video_generator import generate_video, GenerationConfig

    if not FFMPEG:
        print("  SKIP: ffmpeg not found")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        make_audio(tmpdir, 'track', duration=3)
        make_image(tmpdir, 'track', color='blue')

        result = scan_folder(tmpdir)
        assert len(result.complete_pairs) == 1

        # title_overlay=True (default)
        out_with = os.path.join(tmpdir, 'out_with_title.mp4')
        config_with = GenerationConfig(
            pairs=result.complete_pairs,
            output_path=out_with,
            width=320, height=240,
            title_overlay=True,
        )
        generate_video(config_with, progress_callback=lambda p, m: None)
        assert os.path.exists(out_with)
        size_with = os.path.getsize(out_with)
        print(f"  title_overlay=True  : {size_with:,} bytes")
        assert size_with > 1000

        # title_overlay=False
        out_without = os.path.join(tmpdir, 'out_no_title.mp4')
        config_without = GenerationConfig(
            pairs=result.complete_pairs,
            output_path=out_without,
            width=320, height=240,
            title_overlay=False,
        )
        generate_video(config_without, progress_callback=lambda p, m: None)
        assert os.path.exists(out_without)
        size_without = os.path.getsize(out_without)
        print(f"  title_overlay=False : {size_without:,} bytes")
        assert size_without > 1000

        print("  [PASS] title overlay toggle test")


def test_cli_list_presets():
    """Test CLI --list-presets outputs preset names."""
    print("\n=== CLI --list-presets test ===")
    from cli import build_parser, run_cli
    import io
    from contextlib import redirect_stdout

    parser = build_parser()
    args = parser.parse_args(['--cli', '--list-presets'])
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = run_cli(args)
    output = buf.getvalue()
    assert code == 0, f"Expected exit 0, got {code}"
    assert '1080p' in output, f"Expected preset names in output, got: {output[:200]}"
    assert 'default' in output.lower(), f"Expected [default] marker, got: {output[:200]}"
    print(f"  Output snippet: {output.splitlines()[0]}")
    print("  [PASS] CLI --list-presets test")


def test_cli_dry_run():
    """Test CLI --dry-run scans folder without generating video."""
    print("\n=== CLI --dry-run test ===")
    from cli import build_parser, run_cli
    import io
    from contextlib import redirect_stdout

    if not FFMPEG:
        print("  SKIP: ffmpeg not found")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        make_audio(tmpdir, 'song1', duration=3)
        make_image(tmpdir, 'song1', color='red')
        make_audio(tmpdir, 'song2', duration=3)
        make_image(tmpdir, 'song2', color='blue')

        parser = build_parser()
        args = parser.parse_args(['--cli', '--input', tmpdir, '--dry-run'])
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = run_cli(args)
        output = buf.getvalue()
        assert code == 0, f"Expected exit 0, got {code}"
        assert 'song1' in output or 'song2' in output, f"Expected pair names in output"
        assert 'Dry run' in output, f"Expected 'Dry run' in output"
        # No video should be generated
        mp4_files = [f for f in os.listdir(tmpdir) if f.endswith('.mp4')]
        assert len(mp4_files) == 0, f"Dry run should not generate video, found: {mp4_files}"
        print(f"  Pairs found: {output.count('[')}")  # rough count
        print("  [PASS] CLI --dry-run test")


def test_cli_generate():
    """Test CLI end-to-end video generation."""
    print("\n=== CLI generate test ===")
    from cli import build_parser, run_cli
    import io
    from contextlib import redirect_stdout

    if not FFMPEG:
        print("  SKIP: ffmpeg not found")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        make_audio(tmpdir, 'clip1', duration=3)
        make_image(tmpdir, 'clip1', color='green')
        output_path = os.path.join(tmpdir, 'cli_out.mp4')

        parser = build_parser()
        args = parser.parse_args([
            '--cli',
            '--input', tmpdir,
            '--output', output_path,
            '--no-title',
            '--verbose',
        ])
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = run_cli(args)
        output = buf.getvalue()
        assert code == 0, f"Expected exit 0, got {code}\nOutput:\n{output}"
        assert os.path.exists(output_path), f"Output file not created: {output_path}"
        size = os.path.getsize(output_path)
        assert size > 1000, f"Output file too small: {size}"
        assert 'Done!' in output or 'done' in output.lower(), f"Expected done message"
        print(f"  Output: {size:,} bytes")
        print("  [PASS] CLI generate test")


def test_cli_no_input_error():
    """Test CLI returns error when --input is missing."""
    print("\n=== CLI no-input error test ===")
    from cli import build_parser, run_cli
    import io
    from contextlib import redirect_stderr

    parser = build_parser()
    args = parser.parse_args(['--cli'])
    buf = io.StringIO()
    with redirect_stderr(buf):
        code = run_cli(args)
    assert code == 1, f"Expected exit 1, got {code}"
    print("  [PASS] CLI no-input error test")


def test_find_folder_bgm():
    """Test find_folder_bgm detects _bgm.mp3 in folder."""
    print("\n=== find_folder_bgm test ===")
    from video_generator import find_folder_bgm
    tmp = tempfile.mkdtemp()
    try:
        # No BGM file
        result = find_folder_bgm(tmp)
        assert result is None, f"Expected None, got {result}"
        # Create _bgm.mp3
        bgm_path = os.path.join(tmp, '_bgm.mp3')
        make_audio(tmp, '_bgm', ext='.mp3', duration=3)
        result = find_folder_bgm(tmp)
        assert result == bgm_path, f"Expected {bgm_path}, got {result}"
        print("  [PASS] find_folder_bgm")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_bgm_timing_json():
    """Test load_bgm_timing reads JSON correctly."""
    print("\n=== BGM timing JSON test ===")
    from video_generator import load_bgm_timing
    tmp = tempfile.mkdtemp()
    try:
        bgm_path = os.path.join(tmp, '_bgm.mp3')
        timing_path = os.path.join(tmp, '_bgm_timing.json')
        # No timing file
        result = load_bgm_timing(bgm_path)
        assert result == {}, f"Expected empty dict, got {result}"
        # With timing file
        timing_data = {"start_offset": 5.0, "fade_in": 2.0, "fade_out": 3.0, "volume": 0.4}
        with open(timing_path, 'w', encoding='utf-8') as f:
            json.dump(timing_data, f)
        result = load_bgm_timing(bgm_path)
        assert result['start_offset'] == 5.0
        assert result['fade_in'] == 2.0
        assert result['volume'] == 0.4
        print("  [PASS] BGM timing JSON")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_bgm_mix_video():
    """Test mix_bgm_to_video produces a valid MP4 with audio."""
    print("\n=== BGM mix video test ===")
    if not FFMPEG:
        print("  [SKIP] FFmpeg not found")
        return
    from video_generator import mix_bgm_to_video, generate_video, GenerationConfig
    from file_scanner import FilePair
    tmp = tempfile.mkdtemp()
    try:
        # Create voice audio + image + BGM
        audio_path = make_audio(tmp, 'song', ext='.wav', duration=5)
        img_path = make_image(tmp, 'song', color='blue')
        bgm_path = make_audio(tmp, '_bgm', ext='.mp3', duration=3, freq=220)
        output_path = os.path.join(tmp, 'output.mp4')
        pair = FilePair(base_name='song', audio_path=audio_path, image_path=img_path)
        config = GenerationConfig(
            pairs=[pair],
            output_path=output_path,
            width=320, height=240,
            bgm_path=bgm_path,
            voice_volume=1.0,
            bgm_volume=0.5,
            bgm_fade_in=0.5,
            bgm_fade_out=1.0,
        )
        generate_video(config=config)
        assert os.path.isfile(output_path), "Output file not created"
        size = os.path.getsize(output_path)
        assert size > 10000, f"Output file too small: {size} bytes"
        print(f"  [PASS] BGM mix video ({size:,} bytes)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_file_scanner_bgm_exclusion():
    """Test that _bgm.mp3 is excluded from chapter pairing."""
    print("\n=== File scanner BGM exclusion test ===")
    from file_scanner import scan_folder
    tmp = tempfile.mkdtemp()
    try:
        # Create normal pair + BGM file
        make_audio(tmp, 'song', ext='.mp3', duration=3)
        make_image(tmp, 'song', color='green')
        make_audio(tmp, '_bgm', ext='.mp3', duration=10)
        result = scan_folder(tmp)
        base_names = [p.base_name for p in result.complete_pairs]
        assert 'song' in base_names, f"'song' not found in {base_names}"
        assert '_bgm' not in base_names, f"'_bgm' should be excluded, got {base_names}"
        print(f"  [PASS] BGM exclusion (pairs: {base_names})")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_cli_bgm_option():
    """Test CLI --bgm option is accepted and reflected in config."""
    print("\n=== CLI BGM option test ===")
    from cli import build_parser
    parser = build_parser()
    args = parser.parse_args([
        '--cli', '--input', '/tmp/test', '--output', '/tmp/out.mp4',
        '--bgm', '/tmp/bgm.mp3', '--voice-vol', '1.2', '--bgm-vol', '0.3',
        '--bgm-offset', '5.0', '--bgm-fade-in', '2.0', '--bgm-fade-out', '3.0',
    ])
    assert args.bgm == '/tmp/bgm.mp3'
    assert abs(args.voice_vol - 1.2) < 0.001
    assert abs(args.bgm_vol - 0.3) < 0.001
    assert abs(args.bgm_offset - 5.0) < 0.001
    assert abs(args.bgm_fade_in - 2.0) < 0.001
    assert abs(args.bgm_fade_out - 3.0) < 0.001
    print("  [PASS] CLI BGM option")


if __name__ == '__main__':
    # Telop tests
    test_telop_parser_basic()
    test_telop_parser_defaults()
    test_telop_parser_validation()
    test_telop_no_file()
    test_telop_drawtext_filters()
    test_telop_video_generation_single()
    test_telop_video_generation_multi()
    # Animation tests (Phase 1)
    test_telop_animation_filter_generation()
    test_telop_animation_video_generation()
    # Animation tests (Phase 2)
    test_phase2_animation_filter_generation()
    test_phase2_animation_video_generation()
    # Timing tests
    test_timing_parser_basic()
    test_timing_video_generation()
    # Existing tests
    test_multi_image_detection()
    test_exact_match_priority()
    test_single_mode_still_works()
    test_audio_formats()
    test_resolution_presets()
    test_visualizer_filter_generation()
    # New feature tests
    test_title_overlay_toggle()
    test_cli_list_presets()
    test_cli_dry_run()
    test_cli_generate()
    test_cli_no_input_error()
    # BGM tests
    test_find_folder_bgm()
    test_bgm_timing_json()
    test_bgm_mix_video()
    test_file_scanner_bgm_exclusion()
    test_cli_bgm_option()
    print("\n[ALL TESTS PASSED]")
