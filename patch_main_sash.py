import re

with open('main.py', 'r') as f:
    content = f.read()

sash_logic = """
            if cfg.sash_style == "minimal_pill":
                dom_color = _get_dominant_color(image) if cfg.dominant_color_logic else None
                from awards import draw_minimal_pill
                image = draw_minimal_pill(image, label, sash_type=sash_type,
                                         x_ratio=cfg.sash_badge_x, y_ratio=cfg.sash_badge_y,
                                         scale=cfg.minimal_pill_scale, bg_color=dom_color)
            elif cfg.sash_style == "corner_badge" or cfg.sash_badge:
                image = draw_award_badge(image, label, sash_type=sash_type,
                                         x_ratio=cfg.sash_badge_x, y_ratio=cfg.sash_badge_y)
            else:
                image = draw_award_sash(image, label, sash_type=sash_type, muted=cfg.muted)
"""

old_logic = """
            if cfg.rating_display_mode == 4:
                dom_color = _get_dominant_color(image)
                luminanza = 0.299 * dom_color[0] + 0.587 * dom_color[1] + 0.114 * dom_color[2]
                text_color = (0, 0, 0, 255) if luminanza > 128 else (255, 255, 255, 255)

                tag_font_size = int(width * 0.05)
                try:
                    font_tag = ImageFont.truetype(os.path.join(_FONTS_DIR, "Inter-Bold.ttf"), tag_font_size)
                except IOError:
                    font_tag = ImageFont.load_default()

                tag_bbox = draw.textbbox((0, 0), label, font=font_tag)
                tag_w = tag_bbox[2] - tag_bbox[0]
                tag_h = tag_bbox[3] - tag_bbox[1]

                padding_x = int(width * 0.035)
                padding_y = int(height * 0.012)

                rect_x1 = (width - tag_w) // 2 - padding_x
                rect_y1 = int(height * 0.02)
                rect_x2 = rect_x1 + tag_w + (padding_x * 2)
                rect_y2 = rect_y1 + tag_h + (padding_y * 2)

                draw.rounded_rectangle([rect_x1, rect_y1, rect_x2, rect_y2], radius=15, fill=dom_color)
                tx, ty = _text_center(draw, label, font_tag, width / 2, rect_y1 + (rect_y2 - rect_y1) / 2)
                draw.text((tx, ty), label, font=font_tag, fill=text_color)
            elif cfg.sash_badge:
                image = draw_award_badge(image, label, sash_type=sash_type,
                                         x_ratio=cfg.sash_badge_x, y_ratio=cfg.sash_badge_y)
            else:
                image = draw_award_sash(image, label, sash_type=sash_type, muted=cfg.muted)
"""

content = content.replace(old_logic.strip(), sash_logic.strip())

with open('main.py', 'w') as f:
    f.write(content)
