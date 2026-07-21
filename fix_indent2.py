with open("main.py", "r") as f:
    text = f.read()
import re
text = re.sub(
    r'(try:\s*\n\s*wm_font_size\s*=\s*int\(width \* \d+\.\d+\)\s*\n\s*wm_font_file\s*=\s*"[^"]+"\s*if\s*cfg\.font_family\s*==\s*"Ubuntu"\s*else\s*"[^"]+"\s*\n\s*)wm_font\s*=\s*ImageFont\.truetype',
    r'\1    wm_font = ImageFont.truetype',
    text
)

text = re.sub(
    r'(try:\s*\n\s*font_size\s*=\s*int\(width \* \d+\.\d+\)\s*\n\s*font_file\s*=\s*"[^"]+"\s*if\s*cfg\.font_family\s*==\s*"Ubuntu"\s*else\s*"[^"]+"\s*\n\s*)font_meta\s*=\s*ImageFont\.truetype',
    r'\1    font_meta = ImageFont.truetype',
    text
)

text = re.sub(
    r'(try:\s*\n\s*font_size\s*=\s*int\(width \* \d+\.\d+\)\s*\n\s*font_file\s*=\s*"[^"]+"\s*if\s*cfg\.font_family\s*==\s*"Ubuntu"\s*else\s*"[^"]+"\s*\n\s*)font_tag\s*=\s*ImageFont\.truetype',
    r'\1    font_tag = ImageFont.truetype',
    text
)

with open("main.py", "w") as f:
    f.write(text)
