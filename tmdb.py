#tmdb.py
import asyncio
import io
import logging
import httpx
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

from cache import (
    get_cached_trending_snapshot, set_cached_trending_snapshot,
    get_cached_tmdb_poster, set_cached_tmdb_poster,
    get_cached_tmdb_logo, set_cached_tmdb_logo,
    get_cached_tmdb_metadata, set_cached_tmdb_metadata,
)

from config import (
    POSTER_WIDTH, POSTER_HEIGHT,
    LOGO_MAX_W_RATIO, LOGO_MAX_H_RATIO, LOGO_BOTTOM_RATIO,
)

def normalise_poster(image: Image.Image) -> Image.Image:
    target_w, target_h = POSTER_WIDTH, POSTER_HEIGHT
    src_w, src_h = image.size
    scale = max(target_w / src_w, target_h / src_h)
    new_w, new_h = round(src_w * scale), round(src_h * scale)
    image = image.resize((new_w, new_h), Image.LANCZOS)
    left, top = round((new_w - target_w) / 2), round((new_h - target_h) / 2)
    return image.crop((left, top, left + target_w, top + target_h))

def ensure_light_logo(logo: Image.Image, threshold: float = 0.2) -> Image.Image:
    rgba = np.array(logo.convert("RGBA"), dtype=np.float32)
    visible_mask = rgba[:, :, 3] > 30
    if not visible_mask.any(): return logo
    r, g, b = rgba[:, :, 0][visible_mask], rgba[:, :, 1][visible_mask], rgba[:, :, 2][visible_mask]
    if (0.2126 * r + 0.7152 * g + 0.0722 * b).mean() / 255.0 > threshold: return logo
    out = rgba.copy()
    out[:, :, 0][visible_mask] = 255
    out[:, :, 1][visible_mask] = 255
    out[:, :, 2][visible_mask] = 255
    return Image.fromarray(out.astype(np.uint8), "RGBA")

async def fetch_poster_metadata(
    client: httpx.AsyncClient, tmdb_id: str, tmdb_key: str, media_type: str = "movie", logo_language: str = "en",
) -> tuple[list[int], bool, list[dict], str | None, str, str, str | None, dict]:
    endpoint = "tv" if media_type in ("tv", "series") else "movie"
    metadata_cache_key = f"{endpoint}_{tmdb_id}"

    meta = get_cached_tmdb_metadata(metadata_cache_key)
    if meta:
        return (
            meta["genre_ids"], meta["is_textless"], meta["logos"], meta["release_year"],
            meta["title"], meta["poster_path"], meta.get("backdrop_path"),
            {
                "credits": meta.get("credits", {}), "production_companies": meta.get("production_companies", []),
                "original_language": meta.get("original_language"), "runtime": meta.get("runtime"),
                "number_of_seasons": meta.get("number_of_seasons"), "number_of_episodes": meta.get("number_of_episodes"),
                "status": meta.get("status"), "next_episode_to_air": meta.get("next_episode_to_air")
            },
        )

    _img_langs = "en,null" if logo_language == "en" else f"{logo_language},en,null"
    resp = await client.get(f"https://api.themoviedb.org/3/{endpoint}/{tmdb_id}", params={"api_key": tmdb_key, "append_to_response": "images,credits", "include_image_language": _img_langs})
    resp.raise_for_status()
    data = resp.json()

    title = data.get("title") or data.get("name") or data.get("original_title") or data.get("original_name") or "Unknown Title"
    raw_date = data.get("release_date") or data.get("first_air_date") or ""
    release_year = raw_date[:4] if len(raw_date) >= 4 else None

    images = data.get("images", {}); posters = images.get("posters", []); logos = images.get("logos", []); backdrops = images.get("backdrops", [])
    textless = [p for p in posters if p.get("iso_639_1") in (None, "")]

    if textless:
        poster_path = max(textless, key=lambda x: x.get("vote_average", 0))["file_path"]
        is_textless = True
    else:
        poster_path = data.get("poster_path")
        is_textless = False

    if not poster_path: is_textless = False  

    backdrop_candidates = [b for b in backdrops if b.get("iso_639_1") in (None, "")]
    backdrop_path = max(backdrop_candidates, key=lambda x: x.get("vote_average", 0))["file_path"] if backdrop_candidates else None

    genre_ids = [g["id"] for g in data.get("genres", [])]
    credits = data.get("credits", {}); production_companies = data.get("production_companies", [])
    original_language = data.get("original_language"); runtime = data.get("runtime")
    number_of_seasons = data.get("number_of_seasons"); number_of_episodes = data.get("number_of_episodes")
    
    status = data.get("status")
    next_ep = data.get("next_episode_to_air")
    next_episode_to_air = next_ep.get("air_date") if next_ep else None

    set_cached_tmdb_metadata(
        metadata_cache_key, title, release_year, genre_ids, is_textless, poster_path, logos,
        credits=credits, production_companies=production_companies, original_language=original_language,
        runtime=runtime, number_of_seasons=number_of_seasons, number_of_episodes=number_of_episodes,
        backdrop_path=backdrop_path, status=status, next_episode_to_air=next_episode_to_air
    )

    tmdb_data = {
        "credits": credits, "production_companies": production_companies, "original_language": original_language,
        "runtime": runtime, "number_of_seasons": number_of_seasons, "number_of_episodes": number_of_episodes,
        "status": status, "next_episode_to_air": next_episode_to_air
    }

    return genre_ids, is_textless, logos, release_year, title, poster_path, backdrop_path, tmdb_data


async def fetch_poster_image(client: httpx.AsyncClient, tmdb_id: str, media_type: str, poster_path: str) -> Image.Image:
    poster_cache_key = f"{media_type}_{tmdb_id}_{poster_path.strip('/')}"
    cached_bytes = get_cached_tmdb_poster(poster_cache_key)
    if cached_bytes:
        image = Image.open(io.BytesIO(cached_bytes)).convert("RGBA")
        if image.size != (POSTER_WIDTH, POSTER_HEIGHT): image = normalise_poster(image)
        return image
    img_resp = await client.get(f"https://image.tmdb.org/t/p/w500{poster_path}")
    img_resp.raise_for_status()
    image = normalise_poster(Image.open(io.BytesIO(img_resp.content)).convert("RGBA"))
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="JPEG", quality=92)
    set_cached_tmdb_poster(poster_cache_key, buf.getvalue())
    return image

async def fetch_backdrop_image(client: httpx.AsyncClient, tmdb_id: str, backdrop_path: str) -> Image.Image:
    cache_key = f"backdrop_{tmdb_id}_{backdrop_path.strip('/')}"
    cached_bytes = get_cached_tmdb_poster(cache_key)
    if cached_bytes:
        image = Image.open(io.BytesIO(cached_bytes)).convert("RGBA")
        if image.size != (POSTER_WIDTH, POSTER_HEIGHT): image = normalise_poster(image)
        return image
    img_resp = await client.get(f"https://image.tmdb.org/t/p/w1280{backdrop_path}")
    img_resp.raise_for_status()
    image = Image.open(io.BytesIO(img_resp.content)).convert("RGBA")
    w, h = image.size
    crop_w = int(h * 2 / 3)
    if crop_w < w:
        left = (w - crop_w) // 2
        image = image.crop((left, 0, left + crop_w, h))
    image = normalise_poster(image)
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="JPEG", quality=92)
    set_cached_tmdb_poster(cache_key, buf.getvalue())
    return image

async def fetch_logo(
    client: httpx.AsyncClient, tmdb_id: str, media_type: str, tmdb_key: str, fanart_key: str,
    logos: list[dict], logo_language: str = "en", use_original_colors: bool = False,
) -> Image.Image | None:
    fanart_logo_url = None
    if fanart_key:
        query_id = tmdb_id; endpoint = "movies"
        if media_type in ("tv", "series"):
            try:
                ext_resp = await client.get(f"https://api.themoviedb.org/3/tv/{tmdb_id}/external_ids", params={"api_key": tmdb_key})
                if ext_resp.status_code == 200: query_id = ext_resp.json().get("tvdb_id")
            except Exception: pass
            endpoint = "tv"
        if query_id:
            try:
                f_resp = await client.get(f"https://webservice.fanart.tv/v3/{endpoint}/{query_id}", params={"api_key": fanart_key})
                if f_resp.status_code == 200:
                    f_data = f_resp.json()
                    f_logos = (f_data.get("hdmovielogo", []) or f_data.get("movielogo", [])) if endpoint == "movies" else (f_data.get("hdtvlogo", []) or f_data.get("clearlogo", []))
                    if f_logos:
                        candidates = [l for l in f_logos if l.get("lang") == logo_language] or [l for l in f_logos if l.get("lang") == "en"] or [l for l in f_logos if l.get("lang") == "ja"]
                        if candidates:
                            candidates.sort(key=lambda x: int(x.get("likes", 0)), reverse=True)
                            fanart_logo_url = candidates[0].get("url")
            except Exception: pass

    if fanart_logo_url:
        logo_cache_key = "fanart_" + fanart_logo_url.split("/")[-1]
        cached_bytes = get_cached_tmdb_logo(logo_cache_key)
        if cached_bytes: return Image.open(io.BytesIO(cached_bytes)).convert("RGBA")
        try:
            resp = await client.get(fanart_logo_url)
            resp.raise_for_status()
            logo = Image.open(io.BytesIO(resp.content)).convert("RGBA")
            bbox = logo.getchannel("A").getbbox()
            if bbox: logo = logo.crop(bbox)
            if not use_original_colors: logo = ensure_light_logo(logo)
            buf = io.BytesIO()
            logo.save(buf, format="PNG")
            set_cached_tmdb_logo(logo_cache_key, buf.getvalue())
            return logo
        except Exception: pass

    preferred = [lg for lg in logos if lg["file_path"].endswith(".png") and lg.get("iso_639_1") == logo_language]
    english = [lg for lg in logos if lg["file_path"].endswith(".png") and lg.get("iso_639_1") == "en"]
    neutral = [lg for lg in logos if lg["file_path"].endswith(".png") and lg.get("iso_639_1") in (None, "")]
    
    candidates = sorted(preferred or neutral or english, key=lambda x: x.get("vote_average", 0), reverse=True)
    if not candidates: return None

    logo_path = candidates[0]["file_path"]
    logo_cache_key = logo_path.strip('/').replace('/', '_')
    cached_bytes = get_cached_tmdb_logo(logo_cache_key)
    if cached_bytes: return Image.open(io.BytesIO(cached_bytes)).convert("RGBA")

    resp = await client.get(f"https://image.tmdb.org/t/p/w500{logo_path}")
    resp.raise_for_status()
    logo = Image.open(io.BytesIO(resp.content)).convert("RGBA")
    bbox = logo.getchannel("A").getbbox()
    if bbox: logo = logo.crop(bbox)
    if not use_original_colors: logo = ensure_light_logo(logo)

    buf = io.BytesIO()
    logo.save(buf, format="PNG")
    set_cached_tmdb_logo(logo_cache_key, buf.getvalue())
    return logo


async def fetch_trending_rank(client: httpx.AsyncClient, tmdb_id: str, tmdb_key: str, media_type: str = "movie") -> int | None:
    endpoint = "tv" if media_type in ("tv", "series") else "movie"
    snapshot = get_cached_trending_snapshot(endpoint)
    if snapshot is None:
        async def _fetch_page(page: int) -> list[dict]:
            resp = await client.get(f"https://api.themoviedb.org/3/trending/{endpoint}/day", params={"api_key": tmdb_key, "page": page})
            resp.raise_for_status()
            return resp.json().get("results", [])
        try: page1_results, page2_results = await asyncio.gather(_fetch_page(1), _fetch_page(2))
        except Exception: return None
        rankings: dict[str, int] = {}
        for i, item in enumerate(page1_results, start=1): rankings[str(item["id"])] = i
        for i, item in enumerate(page2_results, start=len(page1_results) + 1): rankings[str(item["id"])] = i
        set_cached_trending_snapshot(endpoint, rankings)
        snapshot = rankings
    return snapshot.get(str(tmdb_id))


def composite_logo(
    image: Image.Image, logo: Image.Image, *, max_w_ratio: float = LOGO_MAX_W_RATIO, max_h_ratio: float = LOGO_MAX_H_RATIO, bottom_ratio: float = LOGO_BOTTOM_RATIO,
) -> None:
    width, height = image.size
    max_w, max_h = int(width * max_w_ratio), int(height * max_h_ratio)
    logo.thumbnail((max_w, max_h), Image.LANCZOS)
    alpha_bbox = logo.getchannel("A").getbbox()
    if alpha_bbox: logo = logo.crop(alpha_bbox)
    logo_x = round((width - logo.width) / 2)
    logo_y = height - int(height * bottom_ratio) - logo.height
    image.paste(logo, (logo_x, logo_y), logo)
