import re

with open('configurator.html', 'r') as f:
    content = f.read()

js_params_add = """
  params.set('gradient_top_enable', c('tog-grad-top') ? 'true' : 'false');
  params.set('gradient_bottom_enable', c('tog-grad-bot') ? 'true' : 'false');
  params.set('dominant_color_logic', c('tog-dom-color') ? 'true' : 'false');
  params.set('use_original_logo_color', c('tog-logo-color') ? 'true' : 'false');
  params.set('text_drop_shadow', c('tog-text-shadow') ? 'true' : 'false');
  params.set('frosted_glass_intensity', v('cfg-glass-int'));
  params.set('text_font_family', v('cfg-font-family'));
  params.set('sash_style', v('cfg-sash-style'));
  params.set('minimal_pill_scale', n('cfg-pill-scale').toFixed(2));
"""

content = content.replace("params.set('rating_display_mode', ratingMode);", "params.set('rating_display_mode', ratingMode);\n" + js_params_add)

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

content = content.replace("if (p.has('rating_display_mode')) _setEl('cfg-rating-display-mode', p.get('rating_display_mode'));", "if (p.has('rating_display_mode')) _setEl('cfg-rating-display-mode', p.get('rating_display_mode'));\n" + js_params_load)

with open('configurator.html', 'w') as f:
    f.write(content)
