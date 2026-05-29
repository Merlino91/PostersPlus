import re

with open('configurator.html', 'r') as f:
    content = f.read()

js_params_load = """
  if (p.has('gradient_top_enable')) _setEl('tog-grad-top', p.get('gradient_top_enable'));
  if (p.has('gradient_bottom_enable')) _setEl('tog-grad-bot', p.get('gradient_bottom_enable'));
  if (p.has('dominant_color_logic')) _setEl('tog-dom-color', p.get('dominant_color_logic'));
  if (p.has('use_original_logo_color')) _setEl('tog-logo-color', p.get('use_original_logo_color'));
  if (p.has('text_drop_shadow')) _setEl('tog-text-shadow', p.get('text_drop_shadow'));
  if (p.has('frosted_glass_intensity')) _setEl('cfg-glass-int', p.get('frosted_glass_intensity'));
  if (p.has('text_font_family')) _setEl('cfg-font-family', p.get('text_font_family'));
  if (p.has('sash_style')) _setEl('cfg-sash-style', p.get('sash_style'));
  if (p.has('minimal_pill_scale')) _setEl('cfg-pill-scale', p.get('minimal_pill_scale'));
  updateSashStyleFields();
"""

content = content.replace("if (p.has('rating_display_mode'))            _setEl('cfg-rating-mode',  p.get('rating_display_mode'));", "if (p.has('rating_display_mode'))            _setEl('cfg-rating-mode',  p.get('rating_display_mode'));\n" + js_params_load)

with open('configurator.html', 'w') as f:
    f.write(content)
