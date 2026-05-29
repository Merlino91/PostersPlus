with open("main.py", "r") as f:
    text = f.read()

import re

# We need to add the missing _get_text_color function
missing_func = '''def _get_dominant_color(image: Image.Image) -> tuple[int, int, int]:
    small_img = image.copy()
    small_img.thumbnail((50, 50))
    small_img = small_img.convert("RGB")
    colors = small_img.getcolors(2500)
    if not colors:
        return (100, 100, 100)

    colors.sort(key=lambda t: t[0], reverse=True)
    for count, color in colors:
        luminanza = 0.299 * color[0] + 0.587 * color[1] + 0.114 * color[2]
        if 40 < luminanza < 215:
            return color

    return colors[0][1]

def _get_text_color(bg_color: tuple[int, int, int]) -> tuple[int, int, int]:
    r, g, b = bg_color
    luminance = (0.299 * r + 0.587 * g + 0.114 * b)
    if luminance > 128:
        return (0, 0, 0)
    else:
        return (255, 255, 255)
'''

text = re.sub(r'def _get_dominant_color.*?return colors\[0\]\[1\]\n', missing_func, text, flags=re.DOTALL)

with open("main.py", "w") as f:
    f.write(text)
