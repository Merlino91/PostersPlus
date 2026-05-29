with open("main.py", "r") as f:
    text = f.read()

import re

# We need to add all the new config parameters into `build_request_config`
# so the backend actually assigns them from params[]
# Things to add:
# cfg.sash_style = params.get("sash_style", cfg.sash_style)
# cfg.sash_pill_scale = _f("sash_pill_scale", cfg.sash_pill_scale, 0.1, 5.0)
# cfg.sash_pill_dominant_color = _b("sash_pill_dominant_color", cfg.sash_pill_dominant_color)
# cfg.sash_shadow = _b("sash_shadow", cfg.sash_shadow)
# cfg.gradient_color_mode = params.get("gradient_color_mode", cfg.gradient_color_mode)
# cfg.top_gradient_enabled = _b("top_gradient_enabled", cfg.top_gradient_enabled)
# cfg.top_gradient_intensity = _i("top_gradient_intensity", cfg.top_gradient_intensity, 0, 255)
# cfg.bottom_gradient_enabled = _b("bottom_gradient_enabled", cfg.bottom_gradient_enabled)
# cfg.bottom_gradient_intensity = _i("bottom_gradient_intensity", cfg.bottom_gradient_intensity, 0, 255)
# cfg.bottom_frosted_glass_intensity = _i("bottom_frosted_glass_intensity", cfg.bottom_frosted_glass_intensity, 0, 100)
# cfg.font_family = params.get("font_family", cfg.font_family)
# cfg.text_drop_shadow = _b("text_drop_shadow", cfg.text_drop_shadow)
# cfg.logo_original_colors = _b("logo_original_colors", cfg.logo_original_colors)

new_params = '''    cfg.sash_style = params.get("sash_style", cfg.sash_style)
    cfg.sash_pill_scale = _f("sash_pill_scale", cfg.sash_pill_scale, 0.1, 5.0)
    cfg.sash_pill_dominant_color = _b("sash_pill_dominant_color", cfg.sash_pill_dominant_color)
    cfg.sash_shadow = _b("sash_shadow", cfg.sash_shadow)
    cfg.gradient_color_mode = params.get("gradient_color_mode", cfg.gradient_color_mode)
    cfg.top_gradient_enabled = _b("top_gradient_enabled", cfg.top_gradient_enabled)
    cfg.top_gradient_intensity = _i("top_gradient_intensity", cfg.top_gradient_intensity, 0, 255)
    cfg.bottom_gradient_enabled = _b("bottom_gradient_enabled", cfg.bottom_gradient_enabled)
    cfg.bottom_gradient_intensity = _i("bottom_gradient_intensity", cfg.bottom_gradient_intensity, 0, 255)
    cfg.bottom_frosted_glass_intensity = _i("bottom_frosted_glass_intensity", cfg.bottom_frosted_glass_intensity, 0, 100)
    cfg.font_family = params.get("font_family", cfg.font_family)
    cfg.text_drop_shadow = _b("text_drop_shadow", cfg.text_drop_shadow)
    cfg.logo_original_colors = _b("logo_original_colors", cfg.logo_original_colors)'''

text = re.sub(
    r'    cfg\.sash_priority = _parse_sash_priority\(params\.get\("sash_priority"\)\)',
    f'    cfg.sash_priority = _parse_sash_priority(params.get("sash_priority"))\n{new_params}',
    text
)

with open("main.py", "w") as f:
    f.write(text)
