with open("main.py", "r") as f:
    text = f.read()

text = text.replace("_fonts_dir", "_FONTS_DIR")

with open("main.py", "w") as f:
    f.write(text)
