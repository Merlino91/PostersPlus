with open("main.py", "r") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "font = ImageFont.truetype(os.path.join(_fonts_dir, font_file), font_size)" in line and "except IOError" in lines[i+1]:
        lines[i] = "            font = ImageFont.truetype(os.path.join(_fonts_dir, font_file), font_size)\n"

with open("main.py", "w") as f:
    f.writelines(lines)
