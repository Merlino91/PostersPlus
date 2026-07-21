with open("main.py", "r") as f:
    text = f.read()

import re

# Fetch logo is called here:
# logo, rating_result, trending_rank = await asyncio.gather(
#            fetch_logo(client, logos, rcfg.logo_language) if (is_textless and not is_no_poster) else _resolved(None),

replacement = '''
        logo, rating_result, trending_rank = await asyncio.gather(
            fetch_logo(client, logos, rcfg.logo_language) if (is_textless and not is_no_poster) else _resolved(None),
            rating_coro,
            fetch_trending_rank(client, tmdb_id, effective_tmdb_key, type),
        )

        if logo and not rcfg.logo_original_colors:
            from tmdb import ensure_light_logo
            logo = ensure_light_logo(logo)
'''

text = re.sub(
r'''        logo, rating_result, trending_rank = await asyncio.gather\(
            fetch_logo\(client, logos, rcfg\.logo_language\) if \(is_textless and not is_no_poster\) else _resolved\(None\),
            rating_coro,
            fetch_trending_rank\(client, tmdb_id, effective_tmdb_key, type\),
        \)''',
replacement, text)

with open("main.py", "w") as f:
    f.write(text)
