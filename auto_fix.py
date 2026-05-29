with open("main.py", "r") as f:
    text = f.read()

import re

# We messed up the try/except blocks in build_poster by using global regex.
# Let's write a simple script that matches `try: ... font_file = ... \n [indent]font_meta = ...` and aligns them
lines = text.split('\n')
for i in range(len(lines)):
    line = lines[i]
    if "font = ImageFont.truetype(" in line or "font_meta = ImageFont.truetype" in line or "wm_font = ImageFont.truetype" in line or "font_tag = ImageFont.truetype" in line:
        if i+1 < len(lines) and "except IOError:" in lines[i+1]:
            # Align with except IOError
            except_indent = len(lines[i+1]) - len(lines[i+1].lstrip())
            lines[i] = " " * (except_indent + 4) + line.lstrip()

with open("main.py", "w") as f:
    f.write("\n".join(lines))
