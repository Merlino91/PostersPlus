import re

with open("configurator.html", "r") as f:
    html = f.read()

# Replace toggle switch with dropdown for Sash Style
sash_dropdown = """<div class="field" style="margin-bottom:14px;">
              <label class="field-label">Sash Style</label>
              <select id="cfg-sash-style" onchange="updateSashBadgeFields(); build(); queuePreviewReload()">
                <option value="ribbon">Ribbon (Diagonal)</option>
                <option value="badge">Corner Badge</option>
                <option value="pill">Minimal Pill ITA</option>
              </select>
            </div>"""

html = re.sub(r'<div class="toggle-row" style="margin-bottom:14px;">\s*<div>\s*<div class="toggle-label">Badge Style</div>\s*<div class="field-hint">Render as a badge instead of a diagonal sash\.</div>\s*</div>\s*<label class="toggle-switch">\s*<input type="checkbox" id="tog-sash-badge" onchange="updateSashBadgeFields\(\); build\(\); queuePreviewReload\(\)">\s*<div class="toggle-track"><div class="toggle-thumb"></div></div>\s*</label>\s*</div>', sash_dropdown, html)


# update UI logic in configurator.html
js_logic1 = """function updateSashBadgeFields() {
  const sashStyle = document.getElementById('cfg-sash-style').value;
  const isBadgeOrPill = (sashStyle === 'badge' || sashStyle === 'pill');
  document.getElementById('sash-muted-row').style.display     = isBadgeOrPill ? 'none' : '';
  document.getElementById('sash-badge-offsets').style.display = isBadgeOrPill ? '' : 'none';
  document.getElementById('sash-pill-fields').style.display   = (sashStyle === 'pill') ? '' : 'none';
  if (isBadgeOrPill) initCustomMobileSliders();
}"""

html = re.sub(r'function updateSashBadgeFields\(\) \{\s*const isBadge = c\(\'tog-sash-badge\'\);\s*document\.getElementById\(\'sash-muted-row\'\)\.style\.display\s*=\s*isBadge \? \'none\' : \'\';\s*document\.getElementById\(\'sash-badge-offsets\'\)\.style\.display = isBadge \? \'\' : \'none\';\s*if \(isBadge\) initCustomMobileSliders\(\);\s*\}', js_logic1, html)

with open("configurator.html", "w") as f:
    f.write(html)
