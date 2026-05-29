with open("configurator.html", "r") as f:
    text = f.read()
import re
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
