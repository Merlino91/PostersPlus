with open("config.py", "r") as f:
    text = f.read()

import re
text = re.sub(r'SCORE_GLOW_ALPHA\s*=\s*40\s*# alpha of the glow applied',
              r'SCORE_GLOW_ALPHA     = 40   # alpha of the glow applied\n\n'
              r'# Minimal ITA Styling Defaults\n'
              r'BOTTOM_FROSTED_GLASS_INTENSITY = 12\n'
              r'TOP_GRADIENT_ENABLED = True\n'
              r'BOTTOM_GRADIENT_ENABLED = True\n'
              r'GRADIENT_COLOR_MODE = "black"  # "black" or "dominant"\n'
              r'TOP_GRADIENT_INTENSITY = 220\n'
              r'BOTTOM_GRADIENT_INTENSITY = 255\n'
              r'SASH_PILL_SCALE = 1.0\n'
              r'SASH_PILL_DOMINANT_COLOR = True\n'
              r'SASH_SHADOW = False\n'
              r'TEXT_DROP_SHADOW = False\n'
              r'FONT_FAMILY = "Ubuntu"\n'
              r'LOGO_ORIGINAL_COLORS = False\n',
              text)

with open("config.py", "w") as f:
    f.write(text)
