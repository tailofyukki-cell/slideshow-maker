# -*- coding: utf-8 -*-
"""Patch main_window.py to add telop column and telop detection in scan results"""

with open('main_window.py', 'r', encoding='utf-8') as f:
    src = f.read()

# 1. Add telop_parser import
old_import = "from video_generator import generate_video, GenerationConfig, OUTPUT_FILENAME, RESOLUTION_PRESETS, DEFAULT_PRESET"
new_import = (
    "from telop_parser import find_telop_file, load_telop_file\n"
    "from video_generator import generate_video, GenerationConfig, OUTPUT_FILENAME, RESOLUTION_PRESETS, DEFAULT_PRESET"
)
assert old_import in src, "import anchor not found"
src = src.replace(old_import, new_import, 1)

# 2. Change column count from 4 to 5
old_col = '        self.pairs_table.setColumnCount(4)\n        self.pairs_table.setHorizontalHeaderLabels(["ベース名", "音声ファイル", "画像ファイル", "状態"])'
new_col = '        self.pairs_table.setColumnCount(5)\n        self.pairs_table.setHorizontalHeaderLabels(["ベース名", "音声ファイル", "画像ファイル", "テロップ", "状態"])'
assert old_col in src, "column count anchor not found"
src = src.replace(old_col, new_col, 1)

# 3. Update column resize modes (add col 3 for telop, shift status to col 4)
old_resize = (
    '        self.pairs_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)\n'
    '        self.pairs_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)\n'
    '        self.pairs_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)\n'
    '        self.pairs_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)'
)
new_resize = (
    '        self.pairs_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)\n'
    '        self.pairs_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)\n'
    '        self.pairs_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)\n'
    '        self.pairs_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)\n'
    '        self.pairs_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)'
)
assert old_resize in src, "resize anchor not found"
src = src.replace(old_resize, new_resize, 1)

# 4. In _update_pairs_table: add telop column and shift status to col 4
old_status = (
    '            # status\n'
    '            item_status = QTableWidgetItem(pair.status_text)\n'
    '            self.pairs_table.setItem(row, 3, item_status)\n'
    '\n'
    '            # row background color'
)
new_status = (
    '            # telop column\n'
    '            telop_json = find_telop_file(pair.audio_path) if pair.audio_path else None\n'
    '            if telop_json:\n'
    '                try:\n'
    '                    entries = load_telop_file(telop_json)\n'
    '                    telop_text = f"{len(entries)}件"\n'
    '                    item_telop = QTableWidgetItem(telop_text)\n'
    '                    item_telop.setForeground(QColor("#7b00d4"))\n'
    '                except Exception as e:\n'
    '                    item_telop = QTableWidgetItem(f"エラー")\n'
    '                    item_telop.setForeground(QColor("#c50f1f"))\n'
    '            else:\n'
    '                item_telop = QTableWidgetItem("—")\n'
    '                item_telop.setForeground(QColor("#888888"))\n'
    '            self.pairs_table.setItem(row, 3, item_telop)\n'
    '\n'
    '            # status\n'
    '            item_status = QTableWidgetItem(pair.status_text)\n'
    '            self.pairs_table.setItem(row, 4, item_status)\n'
    '            # row background color'
)
assert old_status in src, "status anchor not found"
src = src.replace(old_status, new_status, 1)

# 5. Update background color loop from range(4) to range(5)
old_range = '            for col in range(4):\n                item = self.pairs_table.item(row, col)\n                if item:\n                    item.setBackground(bg_color)'
new_range = '            for col in range(5):\n                item = self.pairs_table.item(row, col)\n                if item:\n                    item.setBackground(bg_color)'
assert old_range in src, "range anchor not found"
src = src.replace(old_range, new_range, 1)

# 6. Add telop count to scan log
old_scan_log = (
    '            self._log(f"スキャン完了: {self.scan_result.summary}")\n'
    '            if self.scan_result.audio_format_stats:\n'
    '                self._log(f"音声形式: {self.scan_result.audio_format_stats}")\n'
    '            if self.scan_result.image_format_stats:\n'
    '                self._log(f"画像形式: {self.scan_result.image_format_stats}")'
)
new_scan_log = (
    '            self._log(f"スキャン完了: {self.scan_result.summary}")\n'
    '            if self.scan_result.audio_format_stats:\n'
    '                self._log(f"音声形式: {self.scan_result.audio_format_stats}")\n'
    '            if self.scan_result.image_format_stats:\n'
    '                self._log(f"画像形式: {self.scan_result.image_format_stats}")\n'
    '            # count telop files\n'
    '            _telop_count = sum(\n'
    '                1 for p in self.scan_result.complete_pairs\n'
    '                if p.audio_path and find_telop_file(p.audio_path)\n'
    '            )\n'
    '            if _telop_count > 0:\n'
    '                self._log(f"テロップファイル: {_telop_count}件 (.json) を検出しました")'
)
assert old_scan_log in src, "scan log anchor not found"
src = src.replace(old_scan_log, new_scan_log, 1)

with open('main_window.py', 'w', encoding='utf-8') as f:
    f.write(src)

print("Patch applied successfully")
