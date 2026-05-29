import re

with open('configurator.html', 'r') as f:
    content = f.read()

# Add display toggle based on sash style
content = content.replace("function updateSashBadgeFields() {", """
function updateSashBadgeFields() {
  const isBadge = (document.getElementById('cfg-sash-style').value !== 'ribbon');
  _setEl('wrap-sash-badge-fields', isBadge ? 'block' : 'none', 'display');
""")
with open('configurator.html', 'w') as f:
    f.write(content)
