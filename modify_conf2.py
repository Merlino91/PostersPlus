with open("configurator.html", "r") as f:
    text = f.read()

import re
pill_fields = """            <div id="sash-pill-fields" style="display:none; margin-bottom:14px;">
              <div class="field">
                <label class="field-label">Pill Scale</label>
                <div class="range-row">
                  <input type="range" id="cfg-sash-pill-scale" min="0.5" max="2.0" step="0.1" value="1.0" oninput="updateRange(this,'rng-sp-scale'); build(); queuePreviewReload()">
                  <span class="range-val" id="rng-sp-scale">1.0</span>
                </div>
              </div>
              <div class="toggle-row" style="margin-top:14px;">
                <div>
                  <div class="toggle-label">Dominant Color Logic</div>
                </div>
                <label class="toggle-switch">
                  <input type="checkbox" id="tog-sash-pill-color" checked onchange="build(); queuePreviewReload()">
                  <div class="toggle-track"><div class="toggle-thumb"></div></div>
                </label>
              </div>
              <div class="toggle-row">
                <div>
                  <div class="toggle-label">Sash Drop Shadow</div>
                </div>
                <label class="toggle-switch">
                  <input type="checkbox" id="tog-sash-shadow" onchange="build(); queuePreviewReload()">
                  <div class="toggle-track"><div class="toggle-thumb"></div></div>
                </label>
              </div>
            </div>"""

text = text.replace('            <div class="field-hint" style="margin-bottom:10px;">Drag to reorder', pill_fields + '\n            <div class="field-hint" style="margin-bottom:10px;">Drag to reorder')

overlays_masks = """
        <!-- Overlays & Masks -->
        <div class="section">
          <div class="section-header" onclick="toggleSection(this)">
            <div class="section-accent"></div>
            <span class="section-tag">Overlays & Masks</span>
            <span class="section-chevron">▼</span>
          </div>
          <div class="section-body">
            <div class="field" style="margin-bottom:14px;">
              <label class="field-label">Gradient Color Mode</label>
              <select id="cfg-gradient-color" onchange="build(); queuePreviewReload()">
                <option value="black" selected>Classic Black</option>
                <option value="dominant">Dominant Color Wash</option>
              </select>
            </div>

            <div class="toggle-row">
              <div><div class="toggle-label">Top Gradient</div></div>
              <label class="toggle-switch">
                <input type="checkbox" id="tog-top-gradient" checked onchange="build(); queuePreviewReload()">
                <div class="toggle-track"><div class="toggle-thumb"></div></div>
              </label>
            </div>
            <div class="field">
              <label class="field-label">Top Gradient Intensity</label>
              <div class="range-row">
                <input type="range" id="cfg-top-gradient-intensity" min="0" max="255" step="1" value="220" oninput="updateRange(this,'rng-top-grad'); build(); queuePreviewReload()">
                <span class="range-val" id="rng-top-grad">220</span>
              </div>
            </div>

            <div class="toggle-row" style="margin-top:14px;">
              <div><div class="toggle-label">Bottom Gradient</div></div>
              <label class="toggle-switch">
                <input type="checkbox" id="tog-bottom-gradient" checked onchange="build(); queuePreviewReload()">
                <div class="toggle-track"><div class="toggle-thumb"></div></div>
              </label>
            </div>
            <div class="field">
              <label class="field-label">Bottom Gradient Intensity</label>
              <div class="range-row">
                <input type="range" id="cfg-bottom-gradient-intensity" min="0" max="255" step="1" value="255" oninput="updateRange(this,'rng-bot-grad'); build(); queuePreviewReload()">
                <span class="range-val" id="rng-bot-grad">255</span>
              </div>
            </div>

            <div class="field" style="margin-top:14px;">
              <label class="field-label">Frosted Glass Base (Minimal ITA)</label>
              <div class="range-row">
                <input type="range" id="cfg-frosted-glass-intensity" min="0" max="30" step="1" value="12" oninput="updateRange(this,'rng-frost'); build(); queuePreviewReload()">
                <span class="range-val" id="rng-frost">12</span>
              </div>
            </div>
          </div>
        </div>
"""

# Insert overlays masks before Text & Typography or similar... Let's just insert it before 5. QUALITY BADGES
text = text.replace('        <!-- 5. QUALITY BADGES -->', overlays_masks + '\n        <!-- 5. QUALITY BADGES -->')

# Add font and text shadow UI
typography = """        <!-- Typography -->
        <div class="section">
          <div class="section-header" onclick="toggleSection(this)">
            <div class="section-accent"></div>
            <span class="section-tag">Text & Typography</span>
            <span class="section-chevron">▼</span>
          </div>
          <div class="section-body">
            <div class="field" style="margin-bottom:14px;">
              <label class="field-label">Font Family</label>
              <select id="cfg-font-family" onchange="build(); queuePreviewReload()">
                <option value="Ubuntu" selected>Ubuntu</option>
                <option value="Inter">Inter</option>
              </select>
            </div>
            <div class="toggle-row">
              <div><div class="toggle-label">Text Drop Shadow</div></div>
              <label class="toggle-switch">
                <input type="checkbox" id="tog-text-shadow" onchange="build(); queuePreviewReload()">
                <div class="toggle-track"><div class="toggle-thumb"></div></div>
              </label>
            </div>
          </div>
        </div>"""

text = text.replace('        <!-- 4. LOGO & TEXTLESS -->', typography + '\n        <!-- 4. LOGO & TEXTLESS -->')

text = re.sub(
r'<div class="toggle-row" style="margin-bottom:14px;">\s*<div>\s*<div class="toggle-label">Textless Mode</div>',
r'''<div class="toggle-row">
              <div><div class="toggle-label">Original Colors</div></div>
              <label class="toggle-switch">
                <input type="checkbox" id="tog-logo-colors" onchange="build(); queuePreviewReload()">
                <div class="toggle-track"><div class="toggle-thumb"></div></div>
              </label>
            </div>
            <div class="toggle-row" style="margin-bottom:14px; margin-top:14px;">
              <div>
                <div class="toggle-label">Textless Mode</div>''',
text)

with open("configurator.html", "w") as f:
    f.write(text)
