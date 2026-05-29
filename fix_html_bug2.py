with open("configurator.html", "r") as f:
    text = f.read()

import re

# Bug 2: `v('cfg-gradient-color')` doesn't exist, the function is `vEl('cfg-gradient-color')`
text = text.replace("v('cfg-gradient-color')", "vEl('cfg-gradient-color')")
text = text.replace("v('cfg-top-gradient-intensity')", "vEl('cfg-top-gradient-intensity')")
text = text.replace("v('cfg-bottom-gradient-intensity')", "vEl('cfg-bottom-gradient-intensity')")
text = text.replace("v('cfg-frosted-glass-intensity')", "vEl('cfg-frosted-glass-intensity')")
text = text.replace("v('cfg-font-family')", "vEl('cfg-font-family')")
text = text.replace("v('cfg-sash-style')", "vEl('cfg-sash-style')")

with open("configurator.html", "w") as f:
    f.write(text)
