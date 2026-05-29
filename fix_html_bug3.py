with open("configurator.html", "r") as f:
    text = f.read()

import re

# Bug 1: `tog-sash-badge` does not exist anymore. We replaced it with `cfg-sash-style` dropdown.
# But `buildBaseParams` still tries to read it.
# We need to remove `const isBadge = c('tog-sash-badge');` and `params.set('sash_badge', isBadge ? 'true' : 'false');`
text = re.sub(r'\s*const isBadge = c\(\'tog-sash-badge\'\);\s*params\.set\(\'sash_badge\', isBadge \? \'true\' : \'false\'\);\s*', '\n', text)

with open("configurator.html", "w") as f:
    f.write(text)
