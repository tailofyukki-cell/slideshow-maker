# -*- coding: utf-8 -*-
"""Patch main_window.py to support multi-image display in pairs table"""

with open('main_window.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find start: "# Row background colors"
start = None
for i, line in enumerate(lines):
    if '# Row background colors' in line:
        start = i
        break

# Find end: after "item.setBackground(bg_color)"
end = None
for i in range(start, len(lines)):
    if 'item.setBackground(bg_color)' in lines[i]:
        end = i + 1
        break

print(f"Replacing lines {start+1} to {end}")

new_block = '''\
        # Row background colors
        COLOR_COMPLETE      = QColor(220, 255, 220)   # complete pair: light green
        COLOR_ANIMATED_GIF  = QColor(210, 235, 255)   # animated GIF: light blue
        COLOR_VIDEO         = QColor(255, 235, 210)   # video input: light orange
        COLOR_MULTI         = QColor(240, 220, 255)   # multi-image: light purple
        COLOR_INCOMPLETE    = QColor(255, 245, 200)   # incomplete: light yellow

        for row, pair in enumerate(all_pairs):
            # base name
            item_name = QTableWidgetItem(pair.base_name)
            item_name.setFont(QFont("", 11, QFont.Bold))
            self.pairs_table.setItem(row, 0, item_name)

            # audio file
            audio_text = os.path.basename(pair.audio_path) if pair.audio_path else "（なし）"
            item_audio = QTableWidgetItem(audio_text)
            if not pair.audio_path:
                item_audio.setForeground(QColor("#c50f1f"))
            self.pairs_table.setItem(row, 1, item_audio)

            # visual file(s) - with badge display
            if not pair.single_mode:
                # multi-image mode
                names = [os.path.basename(v.path) for v in pair.visual_items]
                if len(names) <= 3:
                    image_text = "  /  ".join(names) + f"  [{len(names)}枚]"
                else:
                    image_text = (
                        "  /  ".join(names[:2])
                        + f"  ...他{len(names)-2}枚  [{len(names)}枚合計]"
                    )
                item_image = QTableWidgetItem(image_text)
                item_image.setForeground(QColor("#5a0080"))  # purple for multi-image
            elif pair.image_path:
                img_basename = os.path.basename(pair.image_path)
                if pair.is_animated_gif:
                    image_text = f"{img_basename}  [アニメGIF]"
                elif pair.image_ext == '.gif':
                    image_text = f"{img_basename}  [静止GIF]"
                elif pair.is_video_input:
                    image_text = f"{img_basename}  [動画入力]"
                else:
                    image_text = img_basename
                item_image = QTableWidgetItem(image_text)
                if pair.is_animated_gif:
                    item_image.setForeground(QColor("#0050a0"))  # blue for animated GIF
                elif pair.is_video_input:
                    item_image.setForeground(QColor("#7a3800"))  # brown for video input
            else:
                item_image = QTableWidgetItem("（なし）")
                item_image.setForeground(QColor("#c50f1f"))
            self.pairs_table.setItem(row, 2, item_image)

            # status
            item_status = QTableWidgetItem(pair.status_text)
            self.pairs_table.setItem(row, 3, item_status)

            # row background color
            if pair.is_complete and not pair.single_mode:
                bg_color = COLOR_MULTI
            elif pair.is_complete and pair.single_mode and pair.is_animated_gif:
                bg_color = COLOR_ANIMATED_GIF
            elif pair.is_complete and pair.single_mode and pair.is_video_input:
                bg_color = COLOR_VIDEO
            elif pair.is_complete:
                bg_color = COLOR_COMPLETE
            else:
                bg_color = COLOR_INCOMPLETE
            for col in range(4):
                item = self.pairs_table.item(row, col)
                if item:
                    item.setBackground(bg_color)
'''

new_lines = lines[:start] + [new_block] + lines[end:]

with open('main_window.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Patch applied successfully")
