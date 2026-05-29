with open("tmdb.py", "r") as f:
    text = f.read()

import re
replacement_logo = """    max_w = int(width  * max_w_ratio)
    max_h = int(height * max_h_ratio)

    # Visual weight scaling instead of strict width/height limits
    # Target area is max_w * max_h
    target_area = max_w * max_h
    logo_area = logo.width * logo.height
    scale_factor = (target_area / logo_area) ** 0.5

    new_w = int(logo.width * scale_factor)
    new_h = int(logo.height * scale_factor)

    # Cap dimensions just in case they get absurdly large
    new_w = min(new_w, int(width * 0.9))
    new_h = min(new_h, int(height * 0.3))

    logo.thumbnail((new_w, new_h), Image.LANCZOS)

    alpha_bbox = logo.getchannel("A").getbbox()
    if alpha_bbox:
        logo = logo.crop(alpha_bbox)

    logo_x = round((width - logo.width) / 2)
    # Fixed central horizontal line
    logo_y = int(height * 0.83) - logo.height // 2"""

text = re.sub(r'    max_w = int\(width  \* max_w_ratio\).*?logo_y = height - int\(height \* bottom_ratio\) - logo\.height',
              replacement_logo, text, flags=re.DOTALL)

with open("tmdb.py", "w") as f:
    f.write(text)
