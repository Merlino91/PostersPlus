with open("configurator.html", "r") as f:
    text = f.read()

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
        </div>
"""
text = text.replace('        <!-- 3. LOGO -->', typography + '\n        <!-- 3. LOGO -->')

with open("configurator.html", "w") as f:
    f.write(text)
