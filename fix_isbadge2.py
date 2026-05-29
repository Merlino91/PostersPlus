with open('configurator.html', 'r') as f:
    content = f.read()

bad_func = """
function updateSashBadgeFields() {
  const isBadge = (document.getElementById('cfg-sash-style').value !== 'ribbon');
  _setEl('wrap-sash-badge-fields', isBadge ? 'block' : 'none', 'display');

  const isBadge = (document.getElementById('cfg-sash-style').value !== 'ribbon');
  document.getElementById('sash-muted-row').style.display     = isBadge ? 'none' : '';
  document.getElementById('sash-badge-offsets').style.display = isBadge ? '' : 'none';
  if (isBadge) initCustomMobileSliders();
}
"""

good_func = """
function updateSashBadgeFields() {
  const isBadge = (document.getElementById('cfg-sash-style').value !== 'ribbon');
  _setEl('wrap-sash-badge-fields', isBadge ? 'block' : 'none', 'display');

  const mutedRow = document.getElementById('sash-muted-row');
  if (mutedRow) mutedRow.style.display = isBadge ? 'none' : '';

  const badgeOffsets = document.getElementById('sash-badge-offsets');
  if (badgeOffsets) badgeOffsets.style.display = isBadge ? '' : 'none';
  if (isBadge) initCustomMobileSliders();
}
"""

content = content.replace(bad_func.strip(), good_func.strip())

with open('configurator.html', 'w') as f:
    f.write(content)
