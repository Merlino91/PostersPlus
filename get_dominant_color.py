with open("main.py", "r") as f:
    text = f.read()

import re
add_dom = """def _get_dominant_color(image: Image.Image) -> tuple[int, int, int]:
    resized = image.resize((1, 1), resample=Image.Resampling.LANCZOS)
    return resized.getpixel((0, 0))

def _get_text_color(bg_color: tuple[int, int, int]) -> tuple[int, int, int]:
    # Calculate luminance to decide whether text should be black or white
    r, g, b = bg_color
    luminance = (0.299 * r + 0.587 * g + 0.114 * b)
    if luminance > 128:
        return (0, 0, 0)
    else:
        return (255, 255, 255)

def add_overlays("""

text = text.replace("def add_overlays(", add_dom)

with open("main.py", "w") as f:
    f.write(text)
