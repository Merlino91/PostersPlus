with open("configurator.html", "r") as f:
    text = f.read()

import re
# Append to params logic
js_add = """
  // Overlays
  params.set('gradient_color_mode', v('cfg-gradient-color'));
  params.set('top_gradient_enabled', c('tog-top-gradient') ? 'true' : 'false');
  params.set('top_gradient_intensity', v('cfg-top-gradient-intensity'));
  params.set('bottom_gradient_enabled', c('tog-bottom-gradient') ? 'true' : 'false');
  params.set('bottom_gradient_intensity', v('cfg-bottom-gradient-intensity'));
  params.set('bottom_frosted_glass_intensity', v('cfg-frosted-glass-intensity'));

  // Typography
  params.set('font_family', v('cfg-font-family'));
  params.set('text_drop_shadow', c('tog-text-shadow') ? 'true' : 'false');

  // Logo
  params.set('logo_original_colors', c('tog-logo-colors') ? 'true' : 'false');
"""

text = text.replace("  // ── Info Sash ──────────────────────────────────────────────────────────────", js_add + "\n  // ── Info Sash ──────────────────────────────────────────────────────────────")

sash_add = """
    const sashStyle = v('cfg-sash-style');
    params.set('sash_style', sashStyle);
    if (sashStyle === 'badge' || sashStyle === 'pill') {
      params.set('sash_badge_x', n('cfg-sash-badge-x').toFixed(2));
      params.set('sash_badge_y', n('cfg-sash-badge-y').toFixed(2));
    }
    if (sashStyle === 'pill') {
      params.set('sash_pill_scale', n('cfg-sash-pill-scale').toFixed(2));
      params.set('sash_pill_dominant_color', c('tog-sash-pill-color') ? 'true' : 'false');
      params.set('sash_shadow', c('tog-sash-shadow') ? 'true' : 'false');
    }
"""

text = re.sub(
    r'    if \(isBadge\) \{\s*// Muted is not compatible with badge style — omit it from URL\s*params\.set\(\'sash_badge_x\', n\(\'cfg-sash-badge-x\'\)\.toFixed\(2\)\);\s*params\.set\(\'sash_badge_y\', n\(\'cfg-sash-badge-y\'\)\.toFixed\(2\)\);\s*\} else \{\s*params\.set\(\'muted\', c\(\'tog-muted\'\) \? \'true\' : \'false\'\);\s*\}',
    sash_add,
    text
)


# Load URL params into UI
load_add = """
  if (p.has('gradient_color_mode'))            _setEl('cfg-gradient-color', p.get('gradient_color_mode'));
  if (p.has('top_gradient_enabled'))           _setEl('tog-top-gradient', p.get('top_gradient_enabled'));
  if (p.has('top_gradient_intensity'))         _setEl('cfg-top-gradient-intensity', p.get('top_gradient_intensity'));
  if (p.has('bottom_gradient_enabled'))        _setEl('tog-bottom-gradient', p.get('bottom_gradient_enabled'));
  if (p.has('bottom_gradient_intensity'))      _setEl('cfg-bottom-gradient-intensity', p.get('bottom_gradient_intensity'));
  if (p.has('bottom_frosted_glass_intensity')) _setEl('cfg-frosted-glass-intensity', p.get('bottom_frosted_glass_intensity'));

  if (p.has('font_family'))                    _setEl('cfg-font-family', p.get('font_family'));
  if (p.has('text_drop_shadow'))               _setEl('tog-text-shadow', p.get('text_drop_shadow'));

  if (p.has('logo_original_colors'))           _setEl('tog-logo-colors', p.get('logo_original_colors'));
"""

text = text.replace("  // ── Sash ────────────────────────────────────────────────────────────────", load_add + "\n  // ── Sash ────────────────────────────────────────────────────────────────")

sash_load = """
  if (p.has('sash_style'))                _setEl('cfg-sash-style',  p.get('sash_style'));
  if (p.has('sash_pill_scale'))           _setEl('cfg-sash-pill-scale',  p.get('sash_pill_scale'));
  if (p.has('sash_pill_dominant_color'))  _setEl('tog-sash-pill-color',  p.get('sash_pill_dominant_color'));
  if (p.has('sash_shadow'))               _setEl('tog-sash-shadow',  p.get('sash_shadow'));
"""

text = text.replace("  if (p.has('sash_badge'))      _setEl('tog-sash-badge',    p.get('sash_badge'));", sash_load)

with open("configurator.html", "w") as f:
    f.write(text)
