with open("main.py", "r") as f:
    text = f.read()

import re

# We need to replace the bottom/top gradient code in `build_poster`
# Let's find `def build_poster(` and inspect it.
# Actually we can do it with regex on `build_poster`
# Let's just dump build_poster to a file and edit it.
with open("build_poster_orig.txt", "w") as fout:
    fout.write(text[text.find("def build_poster("):text.find("async def _cache_prune_loop")])
