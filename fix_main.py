with open("main.py", "r") as f:
    text = f.read()

import re

# Need to fix up ensure_light_logo logic
text = re.sub(
    r'            logo = get_cached_tmdb_logo_from_path\(logo_path\)',
    r'''            logo = get_cached_tmdb_logo_from_path(logo_path)
            if logo and not cfg.logo_original_colors:
                logo = ensure_light_logo(logo)''',
    text
)

text = re.sub(
    r'                logo = Image.open\(io.BytesIO\(cached_bytes\)\)\.convert\("RGBA"\)',
    r'''                logo = Image.open(io.BytesIO(cached_bytes)).convert("RGBA")
                if logo and not cfg.logo_original_colors:
                    logo = ensure_light_logo(logo)''',
    text
)

text = re.sub(
    r'            logo = await fetch_logo\(client, logos, rcfg\.logo_language\)',
    r'''            logo = await fetch_logo(client, logos, rcfg.logo_language)
            if logo and not rcfg.logo_original_colors:
                from tmdb import ensure_light_logo
                logo = ensure_light_logo(logo)''',
    text
)


with open("main.py", "w") as f:
    f.write(text)

with open("tmdb.py", "r") as f:
    tmdb_text = f.read()

tmdb_text = re.sub(r'    logo = ensure_light_logo\(logo\)\n\n    buf = io\.BytesIO\(\)', '    buf = io.BytesIO()', tmdb_text)

with open("tmdb.py", "w") as f:
    f.write(tmdb_text)
