import re

with open('configurator.html', 'r') as f:
    content = f.read()

# Add new HTML UI controls to configurator
new_html = """
          <!-- NEW V2 FEATURES -->
          <div class="panel">
            <h2>Posters+ V2 Overlays & Typography</h2>
            <div class="field">
              <label class="field-label">Gradient Top</label>
              <label class="toggle-row">
                <input type="checkbox" id="tog-grad-top" onchange="build(); queuePreviewReload()" checked>
                <div class="toggle-switch"></div>
                <div class="toggle-label">Enable Top Gradient</div>
              </label>
            </div>
            <div class="field">
              <label class="field-label">Gradient Bottom</label>
              <label class="toggle-row">
                <input type="checkbox" id="tog-grad-bot" onchange="build(); queuePreviewReload()" checked>
                <div class="toggle-switch"></div>
                <div class="toggle-label">Enable Bottom Gradient</div>
              </label>
            </div>
            <div class="field">
              <label class="field-label">Frosted Glass Intensity</label>
              <div class="range-row">
                <input type="range" id="cfg-glass-int" min="0" max="50" step="1" value="12" oninput="updateRange(this,'rng-glass'); build(); queuePreviewReload()">
                <span class="range-val" id="rng-glass">12</span>
              </div>
            </div>
            <div class="field">
              <label class="field-label">Dominant Color Logic</label>
              <label class="toggle-row">
                <input type="checkbox" id="tog-dom-color" onchange="build(); queuePreviewReload()">
                <div class="toggle-switch"></div>
                <div class="toggle-label">Use Dominant Color instead of Black</div>
              </label>
            </div>
            <div class="field">
              <label class="field-label">Original Logo Color</label>
              <label class="toggle-row">
                <input type="checkbox" id="tog-logo-color" onchange="build(); queuePreviewReload()">
                <div class="toggle-switch"></div>
                <div class="toggle-label">Keep Original Logo Colors</div>
              </label>
            </div>
            <div class="field">
              <label class="field-label">Text Font Family</label>
              <select id="cfg-font-family" onchange="build(); queuePreviewReload()">
                <option value="Inter">Inter</option>
                <option value="Ubuntu">Ubuntu</option>
              </select>
            </div>
            <div class="field">
              <label class="field-label">Text Drop Shadow</label>
              <label class="toggle-row">
                <input type="checkbox" id="tog-text-shadow" onchange="build(); queuePreviewReload()">
                <div class="toggle-switch"></div>
                <div class="toggle-label">Enable Text Shadow</div>
              </label>
            </div>
          </div>
"""

content = content.replace('<div class="panel" id="panel-discovery">', new_html + '\n<div class="panel" id="panel-discovery">')

# Modify the Sash style selection
sash_html = """
            <div class="field" id="wrap-sash-style">
              <label class="field-label">Sash Style</label>
              <select id="cfg-sash-style" onchange="updateSashStyleFields(); build(); queuePreviewReload()">
                <option value="ribbon">Ribbon</option>
                <option value="corner_badge">Corner Badge</option>
                <option value="minimal_pill">Minimal Pill ITA</option>
              </select>
            </div>
            <div id="wrap-pill-scale" style="display:none;" class="field">
              <label class="field-label">Pill Scale</label>
              <div class="range-row">
                <input type="range" id="cfg-pill-scale" min="0.5" max="2.0" step="0.1" value="1.0" oninput="updateRange(this,'rng-pill-scale'); build(); queuePreviewReload()">
                <span class="range-val" id="rng-pill-scale">1.0</span>
              </div>
            </div>
"""

content = content.replace('<div class="field" id="wrap-sash-badge">', sash_html + '\n<div class="field" id="wrap-sash-badge" style="display:none;">') # Hide the old toggle

# Add updateSashStyleFields JS
js_update_sash = """
function updateSashStyleFields() {
  const style = document.getElementById('cfg-sash-style').value;
  const showBadgePos = (style === 'corner_badge' || style === 'minimal_pill');
  const posFields = document.getElementById('wrap-sash-badge-fields');
  if(posFields) posFields.style.display = showBadgePos ? 'block' : 'none';

  const showScale = (style === 'minimal_pill');
  const scaleField = document.getElementById('wrap-pill-scale');
  if(scaleField) scaleField.style.display = showScale ? 'block' : 'none';
}
"""

content = content.replace('function updateSashBadgeFields() {', js_update_sash + '\nfunction updateSashBadgeFields() {')
content = content.replace('const isBadge = c(\'tog-sash-badge\');', 'const isBadge = (document.getElementById(\'cfg-sash-style\').value !== \'ribbon\');')

# JS params.set modifications
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

content = content.replace("params.set('rating_display_mode', v('cfg-rating-display-mode'));", "params.set('rating_display_mode', v('cfg-rating-display-mode'));\n" + js_params_add)

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
