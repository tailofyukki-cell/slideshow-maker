# SlideshowMaker

音声ファイル（MP3/WAV/FLAC等）と画像ファイル（JPG/PNG/GIF等）または動画ファイルを組み合わせて、自動で1本のMP4動画を作成するWindows向けデスクトップアプリケーションです。

## 特徴

- 指定フォルダ内の音声と画像をファイル名で自動ペアリング
- 音声の長さに合わせて画像を表示
- チャプター（ファイル）間にフェード効果を挿入
- 各チャプター開始時にファイル名（タイトル）を表示（ON/OFF切替可能）
- FFmpegによる高品質な動画エンコード
- インターネット接続不要で完全ローカル動作
- **GUIモード**と**CLIモード（コマンドライン）**の両方に対応

## 動作環境

- Windows 10 / 11 (64bit)
- `ffmpeg.exe` と `ffprobe.exe` を `SlideshowMaker.exe` と同じフォルダに配置

---

## GUIモードの使い方

### 1. 準備

1つのフォルダに、使用したい音声ファイルと画像ファイルを入れます。  
対応させたい音声と画像は、**拡張子を除いたファイル名を同じ**にしてください。

**ファイル構成例:**
```
my_folder/
├── 001.mp3
├── 001.jpg
├── chapter02.mp3
├── chapter02.png
└── title_bgm.mp3  ※画像がない場合は無視されます
```

### 2. アプリの起動と操作

1. `SlideshowMaker.exe` をダブルクリックして起動します。
2. 「**① 入力フォルダ選択**」で、ファイルを入れたフォルダを指定します。
3. 自動的にスキャンが行われ、「**② ファイルペア一覧**」に結果が表示されます。
   - 緑色の行が「完全ペア（音声＋画像）」として動画生成の対象になります。
4. 「**③ 出力設定**」で各種オプションを設定します。

| 設定項目 | 説明 |
|---|---|
| 解像度 | 6種類のプリセットから選択（YouTube横型/TikTok縦型/Instagram正方形 等） |
| ケン・バーンズ効果 | 静止画にズーム/パン動作を追加 |
| オーディオビジュアライザー | 音声波形を透かしとして動画に重ねる（4スタイル） |
| **ファイル名タイトルを動画に表示する** | **各チャプター先頭にファイル名を表示するかどうか（ON/OFF）** |
| 出力先 | 出力MP4ファイルのパス（デフォルト: 入力フォルダ内の `output.mp4`） |

5. 「**④ 動画生成**」の「▶ 動画を生成する」ボタンをクリックします。
6. 進捗バーが100%になり「完了」と表示されれば成功です。

---

## CLIモードの使い方

`--cli` フラグを付けることでコマンドラインから使用できます。バッチ処理や自動化に便利です。

### 基本的な使い方

```cmd
REM ヘルプを表示
SlideshowMaker.exe --cli --help

REM 利用可能な解像度プリセットを一覧表示
SlideshowMaker.exe --cli --list-presets

REM 基本的な動画生成
SlideshowMaker.exe --cli --input C:\Music\MyAlbum --output C:\out\album.mp4

REM ドライラン（スキャンのみ、動画は生成しない）
SlideshowMaker.exe --cli --input C:\Music\MyAlbum --dry-run
```

### オプション一覧

| オプション | 短縮形 | 説明 | デフォルト |
|---|---|---|---|
| `--input FOLDER` | `-i` | 入力フォルダのパス | （必須） |
| `--output FILE` | `-o` | 出力MP4ファイルのパス | `<入力フォルダ>/output.mp4` |
| `--preset NAME` | `-p` | 解像度プリセット名 | `1080p 横型 (YouTube/一般)` |
| `--width W` | | カスタム幅（px） | — |
| `--height H` | | カスタム高さ（px） | — |
| `--no-title` | | ファイル名タイトルを非表示にする | （デフォルトは表示） |
| `--ken-burns` | | ケン・バーンズ効果を有効にする | OFF |
| `--fps N` | | フレームレート | 30 |
| `--fade SEC` | | フェード時間（秒） | 0.75 |
| `--visualizer STYLE` | | ビジュアライザー（waveform/freqbar/spectrum/vectorscope） | OFF |
| `--viz-height PX` | | ビジュアライザーの高さ（px） | 80 |
| `--viz-opacity 0.0-1.0` | | ビジュアライザーの不透明度 | 0.6 |
| `--viz-color #RRGGBB` | | ビジュアライザーの色 | `#00ffff` |
| `--list-presets` | | 解像度プリセット一覧を表示して終了 | — |
| `--dry-run` | | スキャンのみ（動画生成なし） | — |
| `--verbose` | `-v` | 詳細な進捗を表示 | OFF |

### CLIモードの使用例

```cmd
REM タイトル非表示 + ケン・バーンズ効果
SlideshowMaker.exe --cli --input C:\Songs --output C:\out.mp4 --no-title --ken-burns

REM TikTok縦型 + ビジュアライザー
SlideshowMaker.exe --cli --input C:\Songs --output C:\out.mp4 --preset "1080p 縦型 (TikTok/Reels)" --visualizer waveform

REM カスタム解像度 + 詳細ログ
SlideshowMaker.exe --cli --input C:\Songs --output C:\out.mp4 --width 1280 --height 720 --verbose
```

---

## 対応ファイル形式

| 種類 | 対応形式 |
|---|---|
| 音声 | MP3, WAV, FLAC, OGG, AAC, M4A, WMA |
| 画像 | JPG, PNG, WebP, AVIF, BMP, TIFF, GIF（アニメーション対応） |
| 動画（ビジュアル素材として） | MP4, MOV, AVI, MKV, WebM, FLV, WMV |

## 高度な機能

### 複数画像モード（マルチイメージ）

1つの音声に複数の画像を対応させる場合、ファイル名に `_001`, `_002` のサフィックスを付けます。

```
my_folder/
├── 001.mp3
├── 001_001.png   ← 最初の画像
├── 001_002.png   ← 2番目の画像
└── 001_003.png   ← 3番目の画像
```

### タイミング制御（Timing JSON）

`{ベース名}_timing.json` を配置すると、各画像の表示時間を個別に指定できます。

```json
[
  {"image": "001_001.png", "duration": 10.0},
  {"image": "001_002.png", "duration": 15.0},
  {"image": "001_003.png", "duration": 5.0}
]
```

### テロップ（Telop JSON）

`{ベース名}.json` を配置すると、動画にテキストオーバーレイを追加できます。

```json
[
  {
    "text": "テロップテキスト",
    "start": 1.0,
    "end": 4.0,
    "position": "bottom",
    "size": 60,
    "color": "white",
    "animation": {"type": "fade", "in_duration": 0.5, "out_duration": 0.5}
  }
]
```

---

## エラー時の対処

| エラー | 原因と対処 |
|---|---|
| 完全ペアが0件 | 音声と画像のベース名が一致しているか確認。全角/半角の違いも別ファイルとして扱われます |
| FFmpegが見つからない | `ffmpeg.exe` を `SlideshowMaker.exe` と同じフォルダに配置してください |
| 出力先に書き込めない | 出力先フォルダのアクセス権限を確認するか、別のフォルダを指定してください |

---

## 開発者向け：ビルド手順（exe化）

### 必要な環境

- Windows 10 / 11
- Python 3.9 以上

### 手順

1. コマンドプロンプトまたはPowerShellでこのフォルダを開きます。
2. 以下のコマンドを実行してビルドスクリプトを起動します。
   ```cmd
   build_windows.bat
   ```
3. スクリプトが自動で依存パッケージ（PyQt5, mutagen, PyInstaller等）をインストールし、ビルドを行います。
4. 完了すると `dist` フォルダ内に `SlideshowMaker.exe` が生成されます。
5. [FFmpeg公式サイト](https://ffmpeg.org/download.html)からWindows版の `ffmpeg.exe` と `ffprobe.exe` をダウンロードし、`SlideshowMaker.exe` と同じフォルダに配置してください。

### 技術スタック

| 用途 | 技術 |
|---|---|
| GUI | PyQt5 |
| 音声解析 | mutagen |
| 動画生成 | FFmpeg (subprocess経由) |
| パッケージング | PyInstaller |
