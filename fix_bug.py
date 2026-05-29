import re

with open('configurator.html', 'r') as f:
    content = f.read()

# I used v() instead of vEl()
content = content.replace("v('cfg-glass-int')", "vEl('cfg-glass-int')")
content = content.replace("v('cfg-font-family')", "vEl('cfg-font-family')")
content = content.replace("v('cfg-sash-style')", "vEl('cfg-sash-style')")

with open('configurator.html', 'w') as f:
    f.write(content)
