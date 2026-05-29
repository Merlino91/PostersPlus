with open('tmdb.py', 'r') as f:
    content = f.read()

# fetch_logo definition
content = content.replace(
"""async def fetch_logo(
    client: httpx.AsyncClient,
    logos: list[dict],
    logo_language: str = "en",
) -> Image.Image | None:""",
"""async def fetch_logo(
    client: httpx.AsyncClient,
    logos: list[dict],
    logo_language: str = "en",
    use_original_colors: bool = False,
) -> Image.Image | None:"""
)

# fetch_logo ensure_light_logo logic
content = content.replace(
"""    logo = ensure_light_logo(logo)""",
"""    if not use_original_colors:
        logo = ensure_light_logo(logo)"""
)

# composite_logo logic
old_composite = """
def composite_logo(
    image: Image.Image,
    logo: Image.Image,
    *,
    max_w_ratio: float = LOGO_MAX_W_RATIO,
    max_h_ratio: float = LOGO_MAX_H_RATIO,
    bottom_ratio: float = LOGO_BOTTOM_RATIO,
) -> None:
    width, height = image.size

    max_w = int(width  * max_w_ratio)
    max_h = int(height * max_h_ratio)

    logo.thumbnail((max_w, max_h), Image.LANCZOS)

    alpha_bbox = logo.getchannel("A").getbbox()
    if alpha_bbox:
        logo = logo.crop(alpha_bbox)

    logo_x = round((width - logo.width) / 2)
    logo_y = height - int(height * bottom_ratio) - logo.height

    image.paste(logo, (logo_x, logo_y), mask=logo)
"""

new_composite = """
def composite_logo(
    image: Image.Image,
    logo: Image.Image,
    *,
    max_w_ratio: float = LOGO_MAX_W_RATIO,
    max_h_ratio: float = LOGO_MAX_H_RATIO,
    bottom_ratio: float = LOGO_BOTTOM_RATIO,
) -> None:
    width, height = image.size

    target_area = width * height * 0.05
    logo_area = logo.width * logo.height

    if logo_area > 0:
        scale = (target_area / logo_area) ** 0.5
        new_w = int(logo.width * scale)
        new_h = int(logo.height * scale)
        logo = logo.resize((new_w, new_h), Image.LANCZOS)

    alpha_bbox = logo.getchannel("A").getbbox()
    if alpha_bbox:
        logo = logo.crop(alpha_bbox)

    logo_x = round((width - logo.width) / 2)
    logo_y = int(height * 0.83) - logo.height

    image.paste(logo, (logo_x, logo_y), mask=logo)
"""
content = content.replace(old_composite.strip(), new_composite.strip())

with open('tmdb.py', 'w') as f:
    f.write(content)

with open('main.py', 'r') as f:
    main_content = f.read()

main_content = main_content.replace(
"""            fetch_logo(client, logos, rcfg.logo_language) if (is_textless and not is_no_poster) else _resolved(None),""",
"""            fetch_logo(client, logos, rcfg.logo_language, getattr(rcfg, 'use_original_logo_color', False)) if (is_textless and not is_no_poster) else _resolved(None),"""
)

with open('main.py', 'w') as f:
    f.write(main_content)
