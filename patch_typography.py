import re

with open('main.py', 'r') as f:
    content = f.read()

# Replace Fonts
content = re.sub(r'ImageFont.truetype\(os.path.join\(_FONTS_DIR, "(Inter|Ubuntu)-Bold.ttf"\)',
                 r'ImageFont.truetype(os.path.join(_FONTS_DIR, f"{getattr(cfg, \'text_font_family\', \'Inter\')}-Bold.ttf")',
                 content)

# Add text shadow to rating label (riga 758 / 783)
content = content.replace(
"""            draw.text(
                (tx, ty - int(font_size * 0.10)),
                label,
                font=font_meta,
                fill=(200, 200, 200, 255),
            )""",
"""            if getattr(cfg, 'text_drop_shadow', False):
                draw.text(
                    (tx + 2, ty - int(font_size * 0.10) + 2),
                    label,
                    font=font_meta,
                    fill=(0, 0, 0, 150),
                )
            draw.text(
                (tx, ty - int(font_size * 0.10)),
                label,
                font=font_meta,
                fill=(200, 200, 200, 255),
            )"""
)

# Add text shadow to genre label (riga 821)
content = content.replace(
"""            draw.text((genre_x, y), genre_text, font=font_meta, fill=(235, 235, 235, 255))""",
"""            if getattr(cfg, 'text_drop_shadow', False):
                draw.text((genre_x + 2, y + 2), genre_text, font=font_meta, fill=(0, 0, 0, 150))
            draw.text((genre_x, y), genre_text, font=font_meta, fill=(235, 235, 235, 255))"""
)

# Add text shadow to year text (riga 825)
content = content.replace(
"""                draw.text((year_x, y), year_text, font=font_meta, fill=(235, 235, 235, 255))""",
"""                if getattr(cfg, 'text_drop_shadow', False):
                    draw.text((year_x + 2, y + 2), year_text, font=font_meta, fill=(0, 0, 0, 150))
                draw.text((year_x, y), year_text, font=font_meta, fill=(235, 235, 235, 255))"""
)

with open('main.py', 'w') as f:
    f.write(content)
