with open('main.py', 'r') as f:
    content = f.read()

content = content.replace("getattr(cfg, \\'text_font_family\\', \\'Inter\\')", "getattr(cfg, 'text_font_family', 'Inter')")

with open('main.py', 'w') as f:
    f.write(content)
