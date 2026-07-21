with open("build_poster_new.txt", "r") as f:
    text = f.read()

import re

# Font family and drop shadow logic in build_poster
text = re.sub(
    r'font = ImageFont\.truetype\(.*?,\s*font_size\)',
    r'''font_file = "Ubuntu-Bold.ttf" if cfg.font_family == "Ubuntu" else "Inter-Bold.ttf"
        font = ImageFont.truetype(os.path.join(_fonts_dir, font_file), font_size)''',
    text
)

text = re.sub(
    r'font_meta = ImageFont\.truetype\(.*?,\s*font_size\)',
    r'''font_file = "Ubuntu-Bold.ttf" if cfg.font_family == "Ubuntu" else "Inter-Bold.ttf"
            font_meta = ImageFont.truetype(os.path.join(_fonts_dir, font_file), font_size)''',
    text
)

text = re.sub(
    r'wm_font = ImageFont\.truetype\(.*?,\s*wm_font_size\)',
    r'''wm_font_file = "Ubuntu-Bold.ttf" if cfg.font_family == "Ubuntu" else "Inter-Bold.ttf"
            wm_font = ImageFont.truetype(os.path.join(_fonts_dir, wm_font_file), wm_font_size)''',
    text
)

text = re.sub(
    r'font_tag = ImageFont\.truetype\(.*?,\s*font_size\)',
    r'''font_file = "Ubuntu-Bold.ttf" if cfg.font_family == "Ubuntu" else "Inter-Bold.ttf"
                font_tag = ImageFont.truetype(os.path.join(_fonts_dir, font_file), font_size)''',
    text
)

text = re.sub(
    r'draw\.text\(\(tx \+ shadow_offset, ty \+ shadow_offset\), fallback_title, font=font, fill=\(0, 0, 0, 180\)\)',
    r'''if cfg.text_drop_shadow:
            draw.text((tx + shadow_offset, ty + shadow_offset), fallback_title, font=font, fill=(0, 0, 0, 180))''',
    text
)


# Re-work the pill sash logic
pill_sash_replacement = '''
            if cfg.sash_style == "pill":
                font_size = int(height * 0.02 * cfg.sash_pill_scale)
                font_file = "Ubuntu-Bold.ttf" if cfg.font_family == "Ubuntu" else "Inter-Bold.ttf"
                font_tag = ImageFont.truetype(os.path.join(_fonts_dir, font_file), font_size)

                tag_bbox = draw.textbbox((0, 0), label, font=font_tag)
                tag_w = tag_bbox[2] - tag_bbox[0]
                tag_h = tag_bbox[3] - tag_bbox[1]

                padding_x = int(width * 0.035 * cfg.sash_pill_scale)
                padding_y = int(height * 0.012 * cfg.sash_pill_scale)

                # Use standard x_ratio/y_ratio mapping like badge
                x_ratio = cfg.sash_badge_x
                y_ratio = cfg.sash_badge_y

                # x_ratio 0.0 = flush left, 0.62 = right edge
                # The slider typically goes up to 0.62. To handle dynamic sizes, let's map it:
                # If x_ratio is 0.62 (default), we want it flush right.
                max_w_ratio = 1.0 - ((tag_w + padding_x * 2) / width)

                # Normalise ratio: if 0.62 was right-most for badge, let's just use it as a percentage of available width
                # 0.62 in badge slider is actually representing standard right-aligned for standard badge width.
                # Let's map 0.0 -> 0, 1.0 -> max_w_ratio, assuming x_ratio is just a fractional offset.
                rect_x1 = int(width * x_ratio)
                rect_y1 = int(height * y_ratio)

                # To prevent it from going off screen:
                rect_x1 = min(rect_x1, int(width * max_w_ratio))

                rect_x2 = rect_x1 + tag_w + (padding_x * 2)
                rect_y2 = rect_y1 + tag_h + (padding_y * 2)

                pill_bg = dom_color if cfg.sash_pill_dominant_color else (212, 175, 55)
                pill_text = text_color if cfg.sash_pill_dominant_color else (0, 0, 0)

                if cfg.sash_shadow:
                    shadow_offset = 3
                    draw.rounded_rectangle([rect_x1 + shadow_offset, rect_y1 + shadow_offset, rect_x2 + shadow_offset, rect_y2 + shadow_offset], radius=15, fill=(0,0,0,150))

                draw.rounded_rectangle([rect_x1, rect_y1, rect_x2, rect_y2], radius=15, fill=pill_bg)
                tx, ty = _text_center(draw, label, font_tag, rect_x1 + (rect_x2 - rect_x1) / 2, rect_y1 + (rect_y2 - rect_y1) / 2)
                draw.text((tx, ty), label, font=font_tag, fill=pill_text)
            elif cfg.sash_style == "badge":
                image = draw_award_badge(image, label, sash_type=sash_type,
                                         x_ratio=cfg.sash_badge_x, y_ratio=cfg.sash_badge_y)
            else:
                image = draw_award_sash(image, label, sash_type=sash_type, muted=cfg.muted)'''

text = re.sub(
    r'            if cfg\.rating_display_mode == 4:\s+font_size = int\(height \* 0\.02\).*?image = draw_award_sash\(image, label, sash_type=sash_type, muted=cfg\.muted\)',
    pill_sash_replacement, text, flags=re.DOTALL
)

with open("build_poster_new2.txt", "w") as fout:
    fout.write(text)
