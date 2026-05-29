with open("main.py", "r") as f:
    text = f.read()

import re

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

                x_ratio = cfg.sash_badge_x
                y_ratio = cfg.sash_badge_y
                max_w_ratio = 1.0 - ((tag_w + padding_x * 2) / width)

                rect_x1 = int(width * x_ratio)
                rect_y1 = int(height * y_ratio)
                rect_x1 = min(rect_x1, int(width * max_w_ratio))

                rect_x2 = rect_x1 + tag_w + (padding_x * 2)
                rect_y2 = rect_y1 + tag_h + (padding_y * 2)

                dom_color = _get_dominant_color(image)
                pill_bg = dom_color if cfg.sash_pill_dominant_color else (212, 175, 55)

                r, g, b = pill_bg
                luminance = (0.299 * r + 0.587 * g + 0.114 * b)
                pill_text = (0, 0, 0) if luminance > 128 else (255, 255, 255)

                if not cfg.sash_pill_dominant_color:
                    pill_text = (0, 0, 0)

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
    r'            if cfg\.rating_display_mode == 4:\s+dom_color = _get_dominant_color\(image\).*?image = draw_award_sash\(image, label, sash_type=sash_type, muted=cfg\.muted\)',
    pill_sash_replacement, text, flags=re.DOTALL
)

with open("main.py", "w") as f:
    f.write(text)
