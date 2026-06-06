#main.py
import asyncio
import hashlib
import hmac
import io
import logging
import os
import re
import time
import json
import httpx
import numpy as np
from datetime import datetime
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, HTMLResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True,
)
for _uv_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
    _uv_logger = logging.getLogger(_uv_name)
    _uv_logger.handlers = []
    _uv_logger.propagate = True


class _TruncateUrlFilter(logging.Filter):
    _MAX = 80
    _KEY_RE = re.compile(
        r'((?:tmdb_key|mdblist_key|fanart_key|access_key|api_key|apikey)=)[^&\s\'\"]*',
        re.IGNORECASE,
    )

    @classmethod
    def _redact(cls, value):
        if isinstance(value, str):
            return cls._KEY_RE.sub(r'\1***', value)
        return value

    def filter(self, record: logging.LogRecord) -> bool:
        if (
            record.name == "uvicorn.access"
            and isinstance(record.args, tuple)
            and len(record.args) >= 3
        ):
            path = record.args[2]
            if isinstance(path, str):
                path = self._KEY_RE.sub(r'\1***', path)
                if len(path) > self._MAX:
                    path = path[: self._MAX] + "…"
                record.args = (record.args[0], record.args[1], path) + record.args[3:]

        if isinstance(record.msg, str):
            record.msg = self._redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(self._redact(a) for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: self._redact(v) for k, v in record.args.items()}

        if record.exc_info and not record.exc_text:
            import traceback
            record.exc_text = self._redact(
                "".join(traceback.format_exception(*record.exc_info))
            )
        elif record.exc_text:
            record.exc_text = self._redact(record.exc_text)

        return True


_url_filter = _TruncateUrlFilter()
for _handler in logging.getLogger().handlers:
    _handler.addFilter(_url_filter)

logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

_render_inflight: dict[str, "asyncio.Future[bytes]"] = {}
_quality_bg_inflight: set[str] = set()
_quality_bg_semaphore: "asyncio.Semaphore | None" = None

_rating_fetch_inflight:         dict[str, asyncio.Event] = {}
_rating_backoff:                dict[str, float]          = {} 
_rating_fail_count:             dict[str, int]            = {}
_mdblist_semaphore:             "asyncio.Semaphore | None" = None

_mdblist_key_cooldown: dict[str, float] = {}


async def _background_quality_fetch(
    imdb_id: str,
    media_type: str,
    season: int,
    episode: int,
    release_date: str | None,
) -> None:
    global _quality_bg_semaphore
    if _quality_bg_semaphore is None:
        _quality_bg_semaphore = asyncio.Semaphore(_cfg.QUALITY_BG_CONCURRENCY)
    try:
        async with _quality_bg_semaphore:
            if _HTTP_CLIENT is None:
                return
            await _with_retry(
                fetch_quality_from_aiostreams,
                _HTTP_CLIENT, imdb_id, media_type, season, episode, release_date,
            )
            logger.info(f"Background quality fetch complete for {imdb_id}")
    except Exception as exc:
        logger.warning(f"Background quality fetch failed for {imdb_id}: {exc}")
    finally:
        _quality_bg_inflight.discard(imdb_id)


from age_badge import draw_quality_age_badge, draw_tier_bar
from awards import FETCH_FAILED, _RateLimited, draw_award_badge, draw_award_sash, parse_mdblist_awards
from cache import (
    get_cached_quality,
    get_cached_rating,
    get_cached_final_poster,
    set_cached_final_poster,
    init_db,
    is_digital_release,
    set_cached_rating,
    delete_cached_tmdb_metadata,
    prune_caches,
    get_aod_mapping,
    update_aod_mapping,
    get_sys_meta,
    set_sys_meta
)
from digital_release import digital_release_poll_loop
import config as _cfg
from discovery import (
    ALL_PRIORITY_SLOTS,
    FESTIVAL_KEYWORDS,
    DiscoveryMeta,
    extract_discovery_meta,
    pick_sash,
)
from quality import (
    BadgeItem,
    fetch_quality_from_aiostreams,
    get_resized_badge,
    parse_quality,
    render_badges_left,
)
from ratings import calculate_weighted_score, draw_score_bar, fetch_rating, draw_score_bar_vertical
from tmdb import composite_logo, fetch_logo, fetch_poster_metadata, fetch_poster_image, fetch_backdrop_image, fetch_trending_rank


_HTTP_CLIENT: httpx.AsyncClient | None = None

def _make_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(connect=5.0, read=12.0, write=5.0, pool=5.0),
        limits=httpx.Limits(
            max_connections=40,
            max_keepalive_connections=20,
            keepalive_expiry=30,
        ),
        headers={"Accept-Encoding": "identity"},
        http2=False,
    )

_TMDB_ID_RE  = re.compile(r'^\d{1,10}$')
_IMDB_ID_RE  = re.compile(r'^tt\d{1,10}$')
_VALID_TYPES = frozenset({"movie", "tv", "series"})


def _check_tmdb_id(val: str) -> None:
    if not _TMDB_ID_RE.match(val):
        raise HTTPException(status_code=400, detail="Invalid tmdb_id")

def _check_imdb_id(val: str) -> None:
    if val and not _IMDB_ID_RE.match(val):
        raise HTTPException(status_code=400, detail="Invalid imdb_id")

def _check_type(val: str) -> None:
    if val not in _VALID_TYPES:
        raise HTTPException(status_code=400, detail="Invalid type")

def _resolve_tmdb_key(query_key: str) -> str | None:
    if query_key: return query_key
    if _cfg.SERVER_TMDB_KEY: return _cfg.SERVER_TMDB_KEY
    return None

# NUOVO: Gestione intelligente della rotazione chiavi MDBList
def _resolve_mdblist_key(query_key: str) -> str | None:
    if query_key: return query_key
    keys = getattr(_cfg, 'SERVER_MDBLIST_KEYS', [])
    if not keys: return None
    
    try:
        now = asyncio.get_running_loop().time()
    except RuntimeError:
        now = time.time()
        
    for k in keys:
        if now >= _mdblist_key_cooldown.get(k, 0.0):
            return k
    return None # Tutte le chiavi sono in cooldown

def _resolve_fanart_key(query_key: str) -> str | None:
    if query_key: return query_key
    if getattr(_cfg, 'SERVER_FANART_KEY', None): return _cfg.SERVER_FANART_KEY
    return None


@dataclass
class RequestConfig:
    show_award_sash:     bool = field(default_factory=lambda: _cfg.SHOW_AWARD_SASH)
    badge_display_mode:  int  = field(default_factory=lambda: _cfg.BADGE_DISPLAY_MODE)
    rating_display_mode: int  = field(default_factory=lambda: _cfg.SHOW_RATING_DISPLAY_MODE)

    accent_bar_font_size_ratio:    float = field(default_factory=lambda: _cfg.ACCENT_BAR_MODE_FONT_SIZE_RATIO)
    numeric_score_font_size_ratio: float = field(default_factory=lambda: _cfg.NUMERIC_SCORE_MODE_FONT_SIZE_RATIO)
    accent_bar_y_offset:           float = field(default_factory=lambda: _cfg.ACCENT_BAR_MODE_FONT_Y_OFFSET)
    numeric_score_y_offset:        float = field(default_factory=lambda: _cfg.NUMERIC_SCORE_MODE_FONT_Y_OFFSET)
    score_glow_threshold:          int   = field(default_factory=lambda: _cfg.SCORE_GLOW_THRESHOLD)
    score_glow_blur:               int   = field(default_factory=lambda: _cfg.SCORE_GLOW_BLUR)
    score_glow_alpha:              int   = field(default_factory=lambda: _cfg.SCORE_GLOW_ALPHA)
    minimalist_mode_font_size_ratio:  float = field(default_factory=lambda: _cfg.MINIMALIST_MODE_FONT_SIZE_RATIO)
    minimalist_mode_font_x_offset: float = field(default_factory=lambda: _cfg.MINIMALIST_MODE_FONT_X_OFFSET)
    minimalist_mode_font_y_offset: float = field(default_factory=lambda: _cfg.MINIMALIST_MODE_FONT_Y_OFFSET)

    logo_max_w_ratio:  float = field(default_factory=lambda: _cfg.LOGO_MAX_W_RATIO)
    logo_max_h_ratio:  float = field(default_factory=lambda: _cfg.LOGO_MAX_H_RATIO)
    logo_bottom_ratio: float = field(default_factory=lambda: _cfg.LOGO_BOTTOM_RATIO)

    badge_height:    int   = field(default_factory=lambda: _cfg.BADGE_HEIGHT)
    badge_gap:       int   = field(default_factory=lambda: _cfg.BADGE_GAP)
    badge_anchor_x:  float = field(default_factory=lambda: _cfg.BADGE_ANCHOR_X_RATIO)
    badge_anchor_y:  float = field(default_factory=lambda: _cfg.BADGE_ANCHOR_Y_RATIO)

    movie_weights: dict | None = None
    tv_weights:    dict | None = None

    logo_language: str = field(default_factory=lambda: _cfg.DEFAULT_LOGO_LANGUAGE)
    sash_priority: list[str] = field(default_factory=lambda: list(_cfg.SASH_PRIORITY))
    muted: bool = False
    textless: bool = False
    score_color_mode: int = getattr(_cfg, 'SCORE_COLOR_MODE', 2)
    sash_badge: bool = False 
    sash_badge_x: float = 0.62 
    sash_badge_y: float = 0.04 

    frosted_glass_intensity: int = field(default_factory=lambda: getattr(_cfg, 'FROSTED_GLASS_INTENSITY', 25))
    gradient_top_intensity: int = field(default_factory=lambda: getattr(_cfg, 'GRADIENT_TOP_INTENSITY', 50))
    gradient_bottom_intensity: int = field(default_factory=lambda: getattr(_cfg, 'GRADIENT_BOTTOM_INTENSITY', 80))
    dom_color_top: bool = field(default_factory=lambda: getattr(_cfg, 'DOM_COLOR_TOP', False))
    dom_color_bot: bool = field(default_factory=lambda: getattr(_cfg, 'DOM_COLOR_BOT', False))
    dom_color_sash: bool = field(default_factory=lambda: getattr(_cfg, 'DOM_COLOR_SASH', False))
    sash_style: str = field(default_factory=lambda: getattr(_cfg, 'SASH_STYLE', "ribbon"))
    text_font_family: str = field(default_factory=lambda: getattr(_cfg, 'TEXT_FONT_FAMILY', "Inter"))
    text_drop_shadow: bool = field(default_factory=lambda: getattr(_cfg, 'TEXT_DROP_SHADOW', False))
    use_original_logo_color: bool = field(default_factory=lambda: getattr(_cfg, 'USE_ORIGINAL_LOGO_COLOR', False))
    minimal_pill_scale: float = field(default_factory=lambda: getattr(_cfg, 'MINIMAL_PILL_SCALE', 1.0))


def _parse_bool(val: str | None, default: bool) -> bool:
    if val is None: return default
    return val.strip().lower() not in ("0", "false", "no")

def _parse_weights(raw: str | None, sources: list[str]) -> dict | None:
    if not raw: return None
    out = {}
    try:
        for part in raw.split(","):
            part = part.strip()
            if ":" not in part: continue
            key, val = part.split(":", 1)
            key = key.strip().lower()
            if key in sources:
                out[key] = max(0.0, min(1.0, float(val)))
    except Exception: return None
    return out if out else None

def _parse_sash_priority(raw: str | None) -> list[str]:
    if not raw: return list(_cfg.SASH_PRIORITY)
    tokens = [s.strip() for s in raw.split(",") if s.strip()]
    excluded  = {t[1:] for t in tokens if t.startswith("-") and t[1:] in ALL_PRIORITY_SLOTS}
    active    = [t      for t in tokens if not t.startswith("-") and t in ALL_PRIORITY_SLOTS]
    if not active and not excluded: return list(_cfg.SASH_PRIORITY)
    active_set = set(active)
    for slot in _cfg.SASH_PRIORITY:
        if slot not in active_set and slot not in excluded:
            active.append(slot)
    return active


def build_request_config(params: dict) -> RequestConfig:
    cfg = RequestConfig()
    def _b(key, default): return _parse_bool(params.get(key), default)
    def _f(key, default, lo: float, hi: float):
        try: return max(lo, min(hi, float(params[key]))) if key in params else default
        except (ValueError, TypeError): return default
    def _i(key, default, lo: int, hi: int):
        try: return max(lo, min(hi, int(params[key]))) if key in params else default
        except (ValueError, TypeError): return default
    def _s(key, default): return params.get(key, default).strip() if key in params else default

    cfg.show_award_sash         = _b("show_award_sash",        cfg.show_award_sash)
    cfg.muted                   = _b("muted",                  cfg.muted)
    cfg.textless                = _b("textless",               cfg.textless)
    cfg.sash_badge              = _b("sash_badge",             cfg.sash_badge)

    cfg.frosted_glass_intensity = _i("frosted_glass_intensity", cfg.frosted_glass_intensity, 0, 250)
    cfg.gradient_top_intensity = _i("gradient_top_intensity", cfg.gradient_top_intensity, 0, 100)
    cfg.gradient_bottom_intensity = _i("gradient_bottom_intensity", cfg.gradient_bottom_intensity, 0, 100)
    
    cfg.dom_color_top = _b("dom_color_top", cfg.dom_color_top)
    cfg.dom_color_bot = _b("dom_color_bot", cfg.dom_color_bot)
    cfg.dom_color_sash = _b("dom_color_sash", cfg.dom_color_sash)
    
    cfg.sash_style = _s("sash_style", cfg.sash_style)
    
    font_family = _s("text_font_family", cfg.text_font_family)
    if font_family not in ("Inter", "Ubuntu", "Roboto", "Montserrat", "BebasNeue", "Poppins"):
        font_family = "Inter"
    cfg.text_font_family = font_family

    cfg.text_drop_shadow = _b("text_drop_shadow", cfg.text_drop_shadow)
    cfg.use_original_logo_color = _b("use_original_logo_color", cfg.use_original_logo_color)
    cfg.minimal_pill_scale = _f("minimal_pill_scale", cfg.minimal_pill_scale, 0.1, 5.0)

    cfg.sash_badge_x            = _f("sash_badge_x",           cfg.sash_badge_x,           0.0, 1.0)
    cfg.sash_badge_y            = _f("sash_badge_y",           cfg.sash_badge_y,           0.0, 1.0)
    cfg.score_color_mode        = _i("score_color_mode",       cfg.score_color_mode,       0,   2)
    cfg.badge_display_mode      = _i("badge_display_mode",     cfg.badge_display_mode,     0,   4)
    cfg.rating_display_mode     = _i("rating_display_mode",    cfg.rating_display_mode,    0,   4)

    cfg.accent_bar_font_size_ratio    = _f("accent_bar_font_size_ratio",    cfg.accent_bar_font_size_ratio,    0.0, 0.5)
    cfg.numeric_score_font_size_ratio = _f("numeric_score_font_size_ratio", cfg.numeric_score_font_size_ratio, 0.0, 0.5)
    cfg.accent_bar_y_offset           = _f("accent_bar_y_offset",           cfg.accent_bar_y_offset,           0.0, 1.0)
    cfg.numeric_score_y_offset        = _f("numeric_score_y_offset",        cfg.numeric_score_y_offset,        0.0, 1.0)
    cfg.score_glow_threshold          = _i("score_glow_threshold",          cfg.score_glow_threshold,          0,   100)
    cfg.score_glow_blur               = _i("score_glow_blur",               cfg.score_glow_blur,               0,   50)
    cfg.score_glow_alpha              = _i("score_glow_alpha",              cfg.score_glow_alpha,              0,   255)
    cfg.minimalist_mode_font_size_ratio = _f("minimalist_mode_font_size_ratio", cfg.minimalist_mode_font_size_ratio, 0.0, 0.5)
    cfg.minimalist_mode_font_x_offset = _f("minimalist_mode_font_x_offset", cfg.minimalist_mode_font_x_offset, 0.0, 1.0)
    cfg.minimalist_mode_font_y_offset = _f("minimalist_mode_font_y_offset", cfg.minimalist_mode_font_y_offset, 0.0, 1.0)

    cfg.logo_max_w_ratio  = _f("logo_max_w_ratio",  cfg.logo_max_w_ratio,  0.0, 1.5)
    cfg.logo_max_h_ratio  = _f("logo_max_h_ratio",  cfg.logo_max_h_ratio,  0.0, 1.0)
    cfg.logo_bottom_ratio = _f("logo_bottom_ratio", cfg.logo_bottom_ratio, 0.0, 1.0)

    cfg.badge_height   = _i("badge_height",   cfg.badge_height,   1,   200)
    cfg.badge_gap      = _i("badge_gap",      cfg.badge_gap,      0,   100)
    cfg.badge_anchor_x = _f("badge_anchor_x", cfg.badge_anchor_x, 0.0, 1.0)
    cfg.badge_anchor_y = _f("badge_anchor_y", cfg.badge_anchor_y, 0.0, 1.0)

    all_sources = list(_cfg.MOVIE_WEIGHTS.keys())
    cfg.movie_weights = _parse_weights(params.get("movie_weights"), all_sources)

    tv_sources = list(_cfg.TV_WEIGHTS.keys())
    cfg.tv_weights = _parse_weights(params.get("tv_weights"), tv_sources)

    cfg.logo_language = (params.get("logo_language", cfg.logo_language).strip().lower())
    cfg.sash_priority = _parse_sash_priority(params.get("sash_priority"))

    return cfg


async def _resolved(value): return value
async def _with_retry(coro_fn, *args, **kwargs):
    result = await coro_fn(*args, **kwargs)
    if result is FETCH_FAILED:
        result = await coro_fn(*args, **kwargs)
    return result

def _text_center(draw: ImageDraw.ImageDraw, text: str, font, cx: float, cy: float) -> tuple[float, float]:
    bbox = draw.textbbox((0, 0), text, font=font)
    bbox_width = bbox[2] - bbox[0]
    x = cx - bbox_width / 2 - bbox[0]
    if hasattr(font, 'getmetrics'):
        ascent, descent = font.getmetrics()
        optical_adjust = int(ascent * 0.22)
        y = cy - (ascent + descent) / 2 - descent + optical_adjust
    else:
        bbox_height = bbox[3] - bbox[1]
        y = cy - bbox_height / 2 - bbox[1]
    return x, y

def _get_dominant_color(image: Image.Image) -> tuple[int, int, int]:
    small_img = image.copy()
    small_img.thumbnail((50, 50))
    small_img = small_img.convert("RGB")
    colors = small_img.getcolors(2500)
    if not colors: return (100, 100, 100)
    colors.sort(key=lambda t: t[0], reverse=True)
    for count, color in colors:
        luminanza = 0.299 * color[0] + 0.587 * color[1] + 0.114 * color[2]
        if 40 < luminanza < 215: return color
    return colors[0][1]

def draw_custom_top_tag(image: Image.Image, text: str, scale: float = 1.0, bg_color: tuple = (20, 20, 20), font_family: str = "Inter", drop_shadow: bool = False) -> Image.Image:
    width, height = image.size
    base_font_size = int(24 * scale)
    try: font = ImageFont.truetype(os.path.join(_FONTS_DIR, f"{font_family}-Bold.ttf"), base_font_size)
    except IOError: font = ImageFont.load_default()

    draw = ImageDraw.Draw(image)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    
    pad_x = int(20 * scale)
    pad_y = int(12 * scale)
    pill_w = text_w + pad_x * 2
    pill_h = text_h + pad_y * 2
    
    pill_x = (width - pill_w) // 2
    pill_y = 0 
    r = int(10 * scale) 
    
    overlay = Image.new("RGBA", (width, height), (0,0,0,0))
    
    if drop_shadow:
        shadow_layer = Image.new("RGBA", (width, height), (0,0,0,0))
        shadow_draw = ImageDraw.Draw(shadow_layer)
        shadow_draw.rounded_rectangle([pill_x, pill_y, pill_x + pill_w, pill_y + pill_h], radius=r, fill=(0,0,0, 180))
        shadow_draw.rectangle([pill_x, pill_y, pill_x + pill_w, pill_y + r], fill=(0,0,0, 180))
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(int(5 * scale)))
        
        shifted_shadow = Image.new("RGBA", (width, height), (0,0,0,0))
        shifted_shadow.paste(shadow_layer, (0, int(3 * scale)))
        overlay = Image.alpha_composite(overlay, shifted_shadow)

    pill_layer = Image.new("RGBA", (width, height), (0,0,0,0))
    pill_draw = ImageDraw.Draw(pill_layer)
    pill_draw.rounded_rectangle([pill_x, pill_y, pill_x + pill_w, pill_y + pill_h], radius=r, fill=(*bg_color[:3], 240))
    pill_draw.rectangle([pill_x, pill_y, pill_x + pill_w, pill_y + r], fill=(*bg_color[:3], 240))
    
    lum = 0.299 * bg_color[0] + 0.587 * bg_color[1] + 0.114 * bg_color[2]
    text_color = (250, 250, 250) if lum < 140 else (15, 15, 15)
    
    text_x = pill_x + pad_x
    if hasattr(font, 'getmetrics'):
        ascent, descent = font.getmetrics()
        text_y = pill_y + (pill_h - (ascent + descent)) // 2
    else:
        text_y = pill_y + pad_y
        
    pill_draw.text((text_x, text_y), text, font=font, fill=text_color)
    overlay = Image.alpha_composite(overlay, pill_layer)
    
    return Image.alpha_composite(image.convert("RGBA"), overlay)


def _make_fallback_canvas(genre_ids: list[int] | None = None) -> Image.Image:
    tint = (1.0, 1.0, 1.4)
    if genre_ids:
        gid_set = set(genre_ids)
        for gid in _cfg.GENRE_PRIORITY:
            if gid in gid_set:
                name = _cfg.GENRE_MAP.get(gid)
                if name == "Horror": tint = (3.2, 0.3, 0.3)
                elif name == "Thriller": tint = (0.4, 2.2, 0.5)
                elif name == "Mystery": tint = (1.0, 0.3, 3.0)
                elif name == "Sci-Fi": tint = (0.3, 1.2, 3.2)
                elif name == "Fantasy": tint = (1.6, 0.3, 3.0)
                elif name == "Action": tint = (3.0, 0.8, 0.3)
                elif name == "Adventure": tint = (2.6, 1.5, 0.3)
                elif name == "Animation": tint = (0.4, 0.8, 3.2)
                elif name == "Comedy": tint = (2.6, 2.4, 0.3)
                elif name == "Crime": tint = (2.4, 0.2, 0.2)
                elif name == "Documentary": tint = (0.3, 2.2, 2.4)
                elif name == "Drama": tint = (0.3, 0.3, 2.6)
                elif name == "Family": tint = (2.6, 1.2, 0.3)
                elif name == "History": tint = (2.2, 1.1, 0.3)
                elif name == "Music": tint = (2.8, 0.3, 2.2)
                elif name == "Romance": tint = (3.0, 0.3, 0.9)
                elif name == "War": tint = (0.9, 1.6, 0.3)
                elif name == "Western": tint = (2.8, 1.1, 0.2)
                elif name == "Kids": tint = (0.3, 1.1, 3.0)
                elif name == "Reality": tint = (2.4, 0.8, 0.3)
                elif name == "Soap": tint = (2.6, 0.3, 0.9)
                elif name == "Talk": tint = (0.3, 1.6, 2.4)
                elif name == "News": tint = (0.3, 0.5, 2.6)
                break
    r_mult, g_mult, b_mult = tint
    W, H = _cfg.POSTER_WIDTH, _cfg.POSTER_HEIGHT
    t    = np.linspace(0, np.pi, H, dtype=np.float32)
    v    = (10 + 8 * np.sin(t)).astype(np.float32)
    arr  = np.zeros((H, W, 4), dtype=np.uint8)
    arr[:, :, 0] = np.minimum(255, v * r_mult).astype(np.uint8)[:, np.newaxis]
    arr[:, :, 1] = np.minimum(255, v * g_mult).astype(np.uint8)[:, np.newaxis]
    arr[:, :, 2] = np.minimum(255, v * b_mult).astype(np.uint8)[:, np.newaxis]
    arr[:, :, 3] = 255
    return Image.fromarray(arr, "RGBA")


async def _update_aod_loop():
    await asyncio.sleep(10)
    while True:
        last_update = get_sys_meta("aod_last_update")
        now = time.time()
        if not last_update or now - float(last_update) > 604800:
            logger.info("Checking Anime Mapping Database updates...")
            try:
                if _HTTP_CLIENT:
                    resp = await _HTTP_CLIENT.get(getattr(_cfg, "AOD_URL", "https://raw.githubusercontent.com/Fribb/anime-lists/master/anime-list-full.json"), timeout=45.0)
                    if resp.status_code == 200:
                        def _parse():
                            data = resp.json()
                            m = []
                            for item in data:
                                # Estrae SOLO numeri dal tmdb_id per evitare il crash "tv/123"
                                t_raw = str(item.get("themoviedb_id", ""))
                                t_match = re.search(r'\d+', t_raw)
                                if not t_match: continue
                                t = t_match.group(0)
                                
                                mt = "movie" if str(item.get("type", "")).upper() == "MOVIE" else "tv"
                                
                                # Aggiunge alla mappatura Kitsu
                                k = item.get("kitsu_id")
                                if k: m.append((f"kitsu_{k}", t, mt))
                                
                                # Aggiunge alla mappatura MAL
                                mal = item.get("mal_id")
                                if mal: m.append((f"mal_{mal}", t, mt))
                            return m
                        mappings = await asyncio.get_running_loop().run_in_executor(None, _parse)
                        if mappings:
                            update_aod_mapping(mappings)
                            set_sys_meta("aod_last_update", str(now))
                            logger.info(f"Anime mapping database updated with {len(mappings)} entries.")
            except Exception as e: logger.error(f"Failed to update Anime mapping: {e}")
        await asyncio.sleep(86400)


async def _cache_prune_loop() -> None:
    await asyncio.sleep(300)
    while True:
        logger.info("Running scheduled cache prune")
        await asyncio.get_running_loop().run_in_executor(None, prune_caches)
        _now = asyncio.get_running_loop().time()
        expired = [k for k, v in _rating_backoff.items() if v <= _now]
        for k in expired: del _rating_backoff[k]
        expired_cooldowns = [k for k, v in _mdblist_key_cooldown.items() if v <= _now]
        for k in expired_cooldowns: del _mdblist_key_cooldown[k]
        await asyncio.sleep(6 * 3600)   


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _HTTP_CLIENT, _configurator_html
    init_db()
    _HTTP_CLIENT = _make_http_client()
    _configurator_html = _load_configurator_html()
    prune_task   = asyncio.create_task(_cache_prune_loop())
    digital_task = asyncio.create_task(digital_release_poll_loop(_HTTP_CLIENT))
    aod_task     = asyncio.create_task(_update_aod_loop())
    yield
    prune_task.cancel()
    digital_task.cancel()
    aod_task.cancel()
    with suppress(asyncio.CancelledError): await prune_task
    with suppress(asyncio.CancelledError): await digital_task
    with suppress(asyncio.CancelledError): await aod_task
    await _HTTP_CLIENT.aclose()


app = FastAPI(lifespan=lifespan)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_FONTS_DIR = os.path.join(BASE_DIR, "fonts")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

@app.middleware("http")
async def remove_server_header(request: Request, call_next):
    response = await call_next(request)
    response.headers["server"] = "unknown"
    return response

@app.get("/server-caps")
async def server_caps(access_key: str = ""):
    if _cfg.ACCESS_KEY and not hmac.compare_digest(access_key, _cfg.ACCESS_KEY): raise HTTPException(status_code=403, detail="Unauthorized")
    return {
        "tmdb_key_set":          bool(_cfg.SERVER_TMDB_KEY),
        "mdblist_key_set":       bool(getattr(_cfg, "SERVER_MDBLIST_KEYS", [])),
        "fanart_key_set":        bool(getattr(_cfg, "SERVER_FANART_KEY", "")),
        "aiostreams_configured": bool(_cfg.AIOSTREAMS_URL and _cfg.AIOSTREAMS_AUTH),
    }

_configurator_html: str | None = None

def _load_configurator_html() -> str:
    html_path = os.path.join(os.path.dirname(__file__), "configurator.html")
    try:
        with open(html_path, "r", encoding="utf-8") as f: return f.read()
    except FileNotFoundError: return "<h1>Configurator not found</h1>"

@app.get("/health")
async def health_check(): return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
async def get_configurator(access_key: str = "", reload: str = ""):
    if _cfg.ACCESS_KEY and not hmac.compare_digest(access_key, _cfg.ACCESS_KEY): raise HTTPException(status_code=403, detail="Unauthorized")
    global _configurator_html
    if reload: _configurator_html = _load_configurator_html()
    return HTMLResponse(content=_configurator_html or _load_configurator_html())

@app.get("/search")
async def search_proxy(q: str, tmdb_key: str = "", access_key: str = ""):
    if _cfg.ACCESS_KEY and not hmac.compare_digest(access_key, _cfg.ACCESS_KEY): raise HTTPException(status_code=403, detail="Unauthorized")
    effective_key = _resolve_tmdb_key(tmdb_key)
    if not effective_key: raise HTTPException(status_code=400, detail="No TMDB API key")
    if _HTTP_CLIENT is None: raise HTTPException(status_code=503, detail="Service unavailable")
    resp = await _HTTP_CLIENT.get("https://api.themoviedb.org/3/search/multi", params={"api_key": effective_key, "query": q, "include_adult": "false", "page": "1"})
    return Response(content=resp.content, media_type="application/json", status_code=resp.status_code)

@app.get("/resolve-imdb")
async def resolve_imdb(tmdb_id: str, type: str = "movie", tmdb_key: str = "", access_key: str = ""):
    if _cfg.ACCESS_KEY and not hmac.compare_digest(access_key, _cfg.ACCESS_KEY): raise HTTPException(status_code=403, detail="Unauthorized")
    effective_key = _resolve_tmdb_key(tmdb_key)
    if not effective_key: raise HTTPException(status_code=400, detail="No TMDB API key")
    endpoint = f"https://api.themoviedb.org/3/tv/{tmdb_id}/external_ids" if type == "tv" else f"https://api.themoviedb.org/3/movie/{tmdb_id}/external_ids"
    resp = await _HTTP_CLIENT.get(endpoint, params={"api_key": effective_key})
    return Response(content=resp.content, media_type="application/json", status_code=resp.status_code)


@app.get("/poster")
async def get_poster(
    request: Request, tmdb_id: str = "", imdb_id: str = "", kitsu_id: str = "", mal_id: str = "", type: str = "movie", quality: str = "", season: int = 1, episode: int = 1,
    access_key: str = "", mdblist_key: str = "", tmdb_key: str = "", fanart_key: str = "",
    debug: str | None = None,
):
    if _cfg.ACCESS_KEY and not hmac.compare_digest(access_key, _cfg.ACCESS_KEY): raise HTTPException(status_code=403, detail="Unauthorized")

# --- 1. SANITIZER: DISTRUZIONE SEGNAPOSTO TESTUALI ---
    if "{" in tmdb_id: tmdb_id = ""
    if "{" in imdb_id: imdb_id = ""
    if "{" in kitsu_id: kitsu_id = ""
    if "{" in mal_id: mal_id = ""

    # --- 2. ANIME INTERCEPTOR SICURO (Kitsu + MAL) ---
    # Intercetta SOLO se la stringa inzia ESATTAMENTE con i prefissi noti
    # evitando falsi positivi con parole come "normal" o "animal"
    
    if not kitsu_id:
        if tmdb_id.lower().startswith("kitsu:") or tmdb_id.lower().startswith("kitsu_"):
            kitsu_id = "".join(filter(str.isdigit, tmdb_id))
            tmdb_id = ""
        elif imdb_id.lower().startswith("kitsu:") or imdb_id.lower().startswith("kitsu_"):
            kitsu_id = "".join(filter(str.isdigit, imdb_id))
            imdb_id = ""

    if not mal_id:
        if tmdb_id.lower().startswith("mal:") or tmdb_id.lower().startswith("mal_"):
            mal_id = "".join(filter(str.isdigit, tmdb_id))
            tmdb_id = ""
        elif imdb_id.lower().startswith("mal:") or imdb_id.lower().startswith("mal_"):
            mal_id = "".join(filter(str.isdigit, imdb_id))
            imdb_id = ""

    # 3. Estrae in modo sicuro solo i numeri (se passati direttamente come argomenti URL)
    if kitsu_id: kitsu_id = "".join(filter(str.isdigit, kitsu_id))
    if mal_id: mal_id = "".join(filter(str.isdigit, mal_id))
    
    if not tmdb_id:
        if kitsu_id:
            mapping = get_aod_mapping(f"kitsu_{kitsu_id}")
            if mapping: tmdb_id, type = mapping
        elif mal_id:
            mapping = get_aod_mapping(f"mal_{mal_id}")
            if mapping: tmdb_id, type = mapping

    if not tmdb_id:
        raise HTTPException(status_code=400, detail="Missing tmdb_id or valid kitsu/mal id")

    _check_tmdb_id(tmdb_id)
    if imdb_id:
        _check_imdb_id(imdb_id)
    _check_type(type)

    effective_tmdb_key    = _resolve_tmdb_key(tmdb_key)
    effective_mdblist_key = _resolve_mdblist_key(mdblist_key)
    effective_fanart_key  = _resolve_fanart_key(fanart_key)

    if not effective_tmdb_key: raise HTTPException(status_code=400, detail="No TMDB API key available.")

    raw_params = { k: v for k, v in request.query_params.items() if k not in ("tmdb_id", "imdb_id", "kitsu_id", "mal_id", "mdblist_key", "tmdb_key", "fanart_key", "type", "quality", "season", "episode", "access_key", "debug") }
    rcfg = build_request_config(raw_params)

    if not quality:
        _params_hash = hashlib.md5("&".join(f"{k}={v}" for k, v in sorted(raw_params.items())).encode()).hexdigest()[:8]
        final_cache_key = f"{imdb_id}:{type}:{_params_hash}"
        cached_jpeg = get_cached_final_poster(final_cache_key)
        if cached_jpeg is not None:
            etag = f'"{final_cache_key}"'
            if request.headers.get("if-none-match") == etag: return Response(status_code=304)
            _hit_resp = Response(content=cached_jpeg, media_type="image/jpeg")
            _hit_resp.headers["ETag"] = etag
            if _cfg.CDN_CACHE_TTL > 0: _hit_resp.headers["Cache-Control"] = f"public, max-age={_cfg.CDN_CACHE_TTL}"
            return _hit_resp
    else: final_cache_key = None

    _render_fut: "asyncio.Future[bytes] | None" = None
    if final_cache_key is not None:
        _existing_fut = _render_inflight.get(final_cache_key)
        if _existing_fut is not None:
            try:
                _coal_resp = Response(content=await _existing_fut, media_type="image/jpeg")
                _coal_resp.headers["ETag"] = f'"{final_cache_key}"'
                if _cfg.CDN_CACHE_TTL > 0: _coal_resp.headers["Cache-Control"] = f"public, max-age={_cfg.CDN_CACHE_TTL}"
                return _coal_resp
            except Exception: pass
        _render_fut = asyncio.get_running_loop().create_future()
        _render_fut.add_done_callback(lambda f: f.exception() if not f.cancelled() and f.exception() else None)
        _render_inflight[final_cache_key] = _render_fut

    cached_rating = get_cached_rating(imdb_id) if imdb_id else None

    if cached_rating is not None:
        (cached_ratings_dict, cached_genre, cached_release_date, cached_award_wins, cached_award_noms, cached_awards_fetched, cached_festival_label, cached_age_rating, cached_is_cult, cached_is_true_story, cached_is_metacritic) = cached_rating
    else:
        cached_ratings_dict = cached_genre = cached_release_date = cached_festival_label = cached_age_rating = None
        cached_award_wins = []; cached_award_noms = []; cached_awards_fetched = cached_is_cult = cached_is_true_story = cached_is_metacritic = False

    release_date_for_quality_ttl = cached_release_date
    rating_already_cached        = cached_rating is not None
    _rating_event_to_set = None; _rating_backoff_active = False 

    if imdb_id and not rating_already_cached and effective_mdblist_key:
        _loop_now = asyncio.get_running_loop().time()
        _global_cooldown = _mdblist_key_cooldown.get(effective_mdblist_key, 0.0)
        if _loop_now < _global_cooldown:
            effective_mdblist_key = None; _rating_backoff_active = True
        if effective_mdblist_key:
            _backoff_until = _rating_backoff.get(imdb_id)
            if _backoff_until is not None:
                if _loop_now < _backoff_until: effective_mdblist_key = None; _rating_backoff_active = True
                else: del _rating_backoff[imdb_id]; _rating_fail_count.pop(imdb_id, None)  

    if imdb_id and not rating_already_cached and effective_mdblist_key:
        _inflight_event = _rating_fetch_inflight.get(imdb_id)
        if _inflight_event is not None:
            await _inflight_event.wait()
            _refreshed = get_cached_rating(imdb_id)
            if _refreshed is not None:
                (cached_ratings_dict, cached_genre, cached_release_date, cached_award_wins, cached_award_noms, cached_awards_fetched, cached_festival_label, cached_age_rating, cached_is_cult, cached_is_true_story, cached_is_metacritic) = _refreshed
                rating_already_cached = True; release_date_for_quality_ttl = cached_release_date
            else:
                _loop_now2 = asyncio.get_running_loop().time(); _backoff_now2 = _rating_backoff.get(imdb_id)
                if _backoff_now2 is not None and _loop_now2 < _backoff_now2: effective_mdblist_key = None
        else:
            _rating_event_to_set = asyncio.Event(); _rating_fetch_inflight[imdb_id] = _rating_event_to_set

    if quality and imdb_id: quality_tokens = parse_quality(quality); cached_tokens = None
    elif imdb_id: cached_tokens = get_cached_quality(imdb_id, release_date_for_quality_ttl); quality_tokens = cached_tokens or []
    else: cached_tokens = None; quality_tokens = []

    quality_needs_fetch = (rcfg.badge_display_mode in (1, 2, 4) and not quality and cached_tokens is None and imdb_id)
    quality_pending = False
    if quality_needs_fetch:
        if imdb_id not in _quality_bg_inflight:
            _quality_bg_inflight.add(imdb_id)
            asyncio.create_task(_background_quality_fetch(imdb_id, type, season, episode, release_date_for_quality_ttl))
        quality_needs_fetch = False; quality_pending = True

    effective_movie_weights = rcfg.movie_weights or _cfg.MOVIE_WEIGHTS
    effective_tv_weights    = rcfg.tv_weights    or _cfg.TV_WEIGHTS
    if _HTTP_CLIENT is None: raise HTTPException(status_code=503, detail="Service unavailable")
    client = _HTTP_CLIENT

    try:
        genre_ids, is_textless, logos, release_year, title, poster_path, backdrop_path, tmdb_data = (
            await fetch_poster_metadata(client, tmdb_id, effective_tmdb_key, type, rcfg.logo_language)
        )

        _gid_set = set(genre_ids); _tmdb_genre = "Unknown"
        for _gid in _cfg.GENRE_PRIORITY:
            if _gid in _gid_set:
                _candidate = _cfg.GENRE_MAP.get(_gid, "")
                if _candidate: _tmdb_genre = _candidate; break

        _use_backdrop = bool(backdrop_path) and (poster_path is None or not is_textless)
        if _use_backdrop: is_textless = True         

        if rating_already_cached or not effective_mdblist_key or not imdb_id:
            rating_coro = _resolved((cached_ratings_dict or {}, cached_genre, cached_release_date, [], cached_age_rating))
        else:
            global _mdblist_semaphore
            if _mdblist_semaphore is None: _mdblist_semaphore = asyncio.Semaphore(_cfg.MDBLIST_CONCURRENCY)
            async def _fetch_rating_gated():
                async with _mdblist_semaphore: return await _with_retry(fetch_rating, client, imdb_id, effective_mdblist_key, genre_ids, type, movie_weights=effective_movie_weights, tv_weights=effective_tv_weights)
            rating_coro = _fetch_rating_gated()

        is_no_poster = poster_path is None and not _use_backdrop
        if _use_backdrop:
            _image_coro = fetch_backdrop_image(client, tmdb_id, backdrop_path)
        elif is_no_poster:
            _image_coro = _resolved(_make_fallback_canvas(genre_ids))
        else:
            _image_coro = fetch_poster_image(client, tmdb_id, type, poster_path)

        def build_poster_local(
            image: Image.Image, score: int | str, genre: str, cfg: RequestConfig,
            logo: Image.Image | None = None, fallback_title: str | None = None,
            discovery_meta: DiscoveryMeta | None = None, quality_tokens: list[str] | None = None,
            release_year: str | None = None, age_rating: int | None = None, no_poster: bool = False,
        ) -> Image.Image:
            width, height = image.size
            draw = ImageDraw.Draw(image)

            needs_dom = cfg.dom_color_top or cfg.dom_color_bot or cfg.dom_color_sash
            dom_color = _get_dominant_color(image) if needs_dom else (0, 0, 0)

            # --- TOP GRADIENT ---
            if cfg.gradient_top_intensity > 0:
                top_color = dom_color if cfg.dom_color_top else (0, 0, 0)
                top_height = int(height * 0.25)
                top_max_alpha = int((cfg.gradient_top_intensity / 100) * 255)
                t_top = np.linspace(0, 1, top_height, dtype=np.float32)
                eased_top = ((1 - t_top) * top_max_alpha).astype(np.uint8)
                top_array = np.broadcast_to(eased_top[:, np.newaxis], (top_height, width)).copy()
                top_overlay = Image.fromarray(top_array, mode="L")
                top_tinted = Image.new("RGBA", (width, top_height), (*top_color, 0))
                top_tinted.putalpha(top_overlay)
                image.paste(top_tinted, (0, 0), mask=top_tinted)

            # --- BOTTOM GRADIENT & GLASSMORPHISM ---
            bottom_height = int(height * 0.45) 
            bottom_start = height - bottom_height

            if getattr(cfg, 'frosted_glass_intensity', 0) > 0:
                radius = cfg.frosted_glass_intensity / 10.0
                bottom_crop = image.crop((0, bottom_start, width, height))
                blurred_bottom = bottom_crop.filter(ImageFilter.GaussianBlur(radius=radius))
                
                blurred_bottom = ImageEnhance.Color(blurred_bottom).enhance(1.4)
                blurred_bottom = ImageEnhance.Contrast(blurred_bottom).enhance(1.15)
                
                noise = np.random.normal(0, 5, (bottom_height, width, 3)).astype(np.float32)
                blurred_arr = np.array(blurred_bottom).astype(np.float32)
                blurred_arr[:,:,:3] += noise
                blurred_arr = np.clip(blurred_arr, 0, 255).astype(np.uint8)
                blurred_bottom = Image.fromarray(blurred_arr, "RGBA")

                t_blur = np.linspace(0, 1, bottom_height, dtype=np.float32)
                eased_blur = ((t_blur ** 1.5) * 255).astype(np.uint8)
                blur_array = np.broadcast_to(eased_blur[:, np.newaxis], (bottom_height, width)).copy()
                blur_mask = Image.fromarray(blur_array, mode="L")
                image.paste(blurred_bottom, (0, bottom_start), mask=blur_mask)

            if cfg.gradient_bottom_intensity > 0:
                bot_color = dom_color if cfg.dom_color_bot else (0, 0, 0)
                bottom_max_alpha = int((cfg.gradient_bottom_intensity / 100) * 255)
                bottom_curve = 1.2
                t_bot = np.linspace(0, 1, bottom_height, dtype=np.float32)
                eased_bot = ((1 - (1 - t_bot) ** bottom_curve) * bottom_max_alpha).astype(np.uint8)
                bottom_array = np.broadcast_to(eased_bot[:, np.newaxis], (bottom_height, width)).copy()
                bottom_overlay = Image.fromarray(bottom_array, mode="L")
                bottom_tinted = Image.new("RGBA", (width, bottom_height), (*bot_color, 0))
                bottom_tinted.putalpha(bottom_overlay)
                image.paste(bottom_tinted, (0, bottom_start), mask=bottom_tinted)

            # --- QUALITY BADGES ---
            mode = cfg.badge_display_mode
            tokens = quality_tokens or []
            if mode == 1:
                draw_quality_age_badge(image, age_rating, tokens, anchor_x_ratio=cfg.badge_anchor_x, anchor_y_ratio=cfg.badge_anchor_y, badge_height=cfg.badge_height)
            elif mode == 3:
                draw_quality_age_badge(image, age_rating, [], anchor_x_ratio=cfg.badge_anchor_x, anchor_y_ratio=cfg.badge_anchor_y, badge_height=cfg.badge_height, always_silver=True)
            elif mode == 4:
                draw_tier_bar(image, tokens, anchor_x_ratio=cfg.badge_anchor_x, anchor_y_ratio=cfg.badge_anchor_y, bar_height=cfg.badge_height)
            elif mode == 2:
                allowed_tokens  = {"4K", "1080P", "REMUX", "WEBDL", "DV", "HDR10+", "HDR10"}
                filtered_tokens = [t for t in tokens if t in allowed_tokens]
                if filtered_tokens:
                    bx = int(width  * cfg.badge_anchor_x); by = int(height * cfg.badge_anchor_y)
                    badge_items: list[BadgeItem] = [(get_resized_badge(token, cfg.badge_height), _cfg.QUALITY_LABELS.get(token, token)) for token in filtered_tokens]
                    render_badges_left(image, badge_items, x_start=bx, y_top=by, badge_height=cfg.badge_height, badge_gap=cfg.badge_gap)

            # --- LOGO O TITOLO FALLBACK ---
            if logo:
                composite_logo(image, logo, max_w_ratio=cfg.logo_max_w_ratio, max_h_ratio=cfg.logo_max_h_ratio, bottom_ratio=cfg.logo_bottom_ratio)
            elif fallback_title:
                try: font_size = int(width * 0.1); font = ImageFont.truetype(os.path.join(_FONTS_DIR, f"{cfg.text_font_family}-Bold.ttf"), font_size)
                except IOError: font = ImageFont.load_default()
                
                title_cy = height - int(height * 0.20)
                max_width = int(width * 0.82)
                while True:
                    bbox = draw.textbbox((0, 0), fallback_title, font=font)
                    if (bbox[2] - bbox[0]) <= max_width or font_size <= 24: break
                    font_size -= 2 
                    try: font = ImageFont.truetype(os.path.join(_FONTS_DIR, f"{cfg.text_font_family}-Bold.ttf"), font_size)
                    except IOError: break

                tx, ty = _text_center(draw, fallback_title, font, width / 2, title_cy) 
                shadow_offset = max(2, int(font_size * 0.04)) 
                draw.text((tx + shadow_offset, ty + shadow_offset), fallback_title, font=font, fill=(0, 0, 0, 180))
                draw.text((tx, ty), fallback_title, font=font, fill=(255, 255, 255, 255))
                if no_poster:
                    try: wm_font = ImageFont.truetype(os.path.join(_FONTS_DIR, f"{cfg.text_font_family}-Bold.ttf"), 18)
                    except IOError: wm_font = ImageFont.load_default()
                    wm_text = "Posters+ fallback"; wm_bb = draw.textbbox((0, 0), wm_text, font=wm_font)
                    wm_x = (width - (wm_bb[2] - wm_bb[0])) // 2; wm_y = ty + (wm_bb[3] - wm_bb[1]) + int(font_size * 1.4) 
                    draw.text((wm_x, wm_y), wm_text, font=wm_font, fill=(160, 160, 160, 110))

            # --- RATING ---
            if cfg.rating_display_mode != 0:
                if cfg.rating_display_mode == 1:
                    font_size = int(width * cfg.accent_bar_font_size_ratio)
                    label = f"{genre} · {release_year}" if release_year else genre
                    rating_cy = height * cfg.accent_bar_y_offset
                    try: font_meta = ImageFont.truetype(os.path.join(_FONTS_DIR, f"{cfg.text_font_family}-Bold.ttf"), font_size)
                    except IOError: font_meta = ImageFont.load_default()
                    tx, ty = _text_center(draw, label, font_meta, width / 2, rating_cy)
                    draw.text((tx + 2, ty - int(font_size * 0.10) + 2), label, font=font_meta, fill=(0, 0, 0, 150))
                    draw.text((tx, ty - int(font_size * 0.10)), label, font=font_meta, fill=(200, 200, 200, 255))
                    draw_score_bar(image, score, glow_threshold=cfg.score_glow_threshold, glow_blur=cfg.score_glow_blur, glow_alpha=cfg.score_glow_alpha, color_mode=cfg.score_color_mode)
                elif cfg.rating_display_mode == 2:
                    font_size = int(width * cfg.numeric_score_font_size_ratio)
                    label = f"{genre} ★ {score}"; rating_cy = height * cfg.numeric_score_y_offset
                    try: font_meta = ImageFont.truetype(os.path.join(_FONTS_DIR, f"{cfg.text_font_family}-Bold.ttf"), font_size)
                    except IOError: font_meta = ImageFont.load_default()
                    tx, ty = _text_center(draw, label, font_meta, width / 2, rating_cy)
                    draw.text((tx + 2, ty - int(font_size * 0.10) + 2), label, font=font_meta, fill=(0, 0, 0, 150))
                    draw.text((tx, ty - int(font_size * 0.10)), label, font=font_meta, fill=(200, 200, 200, 255))
                elif cfg.rating_display_mode == 3:
                    font_size = int(width * cfg.minimalist_mode_font_size_ratio)
                    try: font_meta = ImageFont.truetype(os.path.join(_FONTS_DIR, f"{cfg.text_font_family}-Bold.ttf"), font_size)
                    except IOError: font_meta = ImageFont.load_default()
                    y = round(height * cfg.minimalist_mode_font_y_offset); right_edge = width - int(width * cfg.minimalist_mode_font_x_offset)
                    year_text = str(release_year or ""); genre_text = genre
                    pip_gap = int(font_size * 0.55); pip_w = max(4, int(font_size * 0.18)); pip_h = int(font_size * 1.4)
                    genre_bb = draw.textbbox((0, 0), genre_text, font=font_meta); genre_w  = genre_bb[2] - genre_bb[0]
                    year_w = (draw.textbbox((0, 0), year_text, font=font_meta)[2] - draw.textbbox((0, 0), year_text, font=font_meta)[0]) if year_text else 0
                    pip_x = right_edge - year_w - pip_gap - pip_w; pip_cy = round(y + font_size * 0.60)
                    genre_x = pip_x - pip_gap - genre_w
                    draw.text((genre_x + 2, y + 2), genre_text, font=font_meta, fill=(0, 0, 0, 150))
                    draw.text((genre_x, y), genre_text, font=font_meta, fill=(235, 235, 235, 255))
                    if year_text:
                        year_x = pip_x + pip_w + pip_gap
                        draw.text((year_x + 2, y + 2), year_text, font=font_meta, fill=(0, 0, 0, 150))
                        draw.text((year_x, y), year_text, font=font_meta, fill=(235, 235, 235, 255))
                    if score not in ("N/A", None): draw_score_bar_vertical(image, score, x=pip_x, y_center=pip_cy, height=pip_h, width=pip_w, color_mode=cfg.score_color_mode)

            # NUOVO: INFO SASH DINAMICI
            if cfg.show_award_sash:
                dynamic_sashes = {}
                # Analizza i dati freschi da TMDB se è una serie TV
                if type in ("tv", "series") and tmdb_data:
                    status = tmdb_data.get("status", "")
                    next_ep = tmdb_data.get("next_episode_to_air")
                    
                    if next_ep and "air_date" in next_ep:
                        try:
                            d = datetime.strptime(next_ep["air_date"], "%Y-%m-%d")
                            mesi = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]
                            dynamic_sashes["next_episode"] = f"Prossimo Ep: {d.day} {mesi[d.month-1]}"
                        except Exception:
                            pass

                sash_result = None
                # Il ciclo rispetta l'ordine di priorità imposto dal file config.py / UI
                for sash_id in cfg.sash_priority:
                    if sash_id in dynamic_sashes:
                        sash_result = (dynamic_sashes[sash_id], sash_id)
                        break
                    elif discovery_meta is not None:
                        # Se non è un tag dinamico, chiediamo a discovery.py se la serie ha vinto questo premio
                        temp_res = pick_sash(discovery_meta, [sash_id])
                        if temp_res:
                            sash_result = temp_res
                            break

                if sash_result is not None:
                    label, sash_type = sash_result
                    if cfg.sash_style == "minimal_pill":
                        dom_color_pill = dom_color if cfg.dom_color_sash else (20, 20, 20)
                        image = draw_custom_top_tag(image, label, scale=cfg.minimal_pill_scale, bg_color=dom_color_pill, font_family=cfg.text_font_family, drop_shadow=cfg.text_drop_shadow)
                    elif cfg.sash_style == "corner_badge" or cfg.sash_badge:
                        image = draw_award_badge(image, label, sash_type=sash_type, x_ratio=cfg.sash_badge_x, y_ratio=cfg.sash_badge_y)
                    else:
                        image = draw_award_sash(image, label, sash_type=sash_type, muted=cfg.muted)

            return image

        (image, logo, rating_result, trending_rank) = await asyncio.gather(
            _image_coro,
            fetch_logo(client, tmdb_id, type, effective_tmdb_key, effective_fanart_key, logos, rcfg.logo_language, getattr(rcfg, 'use_original_logo_color', False)) if (is_textless and not is_no_poster) else _resolved(None),
            rating_coro,
            fetch_trending_rank(client, tmdb_id, effective_tmdb_key, type),
        )

        rate_limited  = isinstance(rating_result, _RateLimited)
        rating_failed = (imdb_id and not rating_already_cached and effective_mdblist_key and (rating_result is FETCH_FAILED or rate_limited))

        if rating_failed:
            if rate_limited:
                backoff_secs = min(float(rating_result.retry_after), 3600.0) if getattr(rating_result, 'retry_after', None) else 3600.0
                _global_window = min(backoff_secs, 120.0)
                _new_global_until = asyncio.get_running_loop().time() + _global_window
                if effective_mdblist_key:
                    _mdblist_key_cooldown[effective_mdblist_key] = _new_global_until
                    logger.warning(f"MDBList API Key in rate limit. Cooldown per {_global_window}s.")
            else:
                fail_n = _rating_fail_count.get(imdb_id, 0) + 1; _rating_fail_count[imdb_id] = fail_n
                backoff_secs = min(30 * (4 ** (fail_n - 1)), 3600.0)
            _rating_backoff[imdb_id] = asyncio.get_running_loop().time() + backoff_secs
            ratings_dict = {}; genre = cached_genre or _tmdb_genre; rel = cached_release_date; score = "N/A"
            keywords = []; award_wins = cached_award_wins; award_noms = cached_award_noms
            festival_label = cached_festival_label; age_rating = cached_age_rating
            is_cult = cached_is_cult; is_true_story = cached_is_true_story; is_metacritic = cached_is_metacritic
        else:
            ratings_dict, genre, rel, keywords, age_rating = rating_result
            genre = genre or _tmdb_genre
            if imdb_id and not rating_already_cached and not _rating_backoff_active: _rating_fail_count.pop(imdb_id, None)
            if isinstance(ratings_dict, dict): score = calculate_weighted_score(ratings_dict, effective_tv_weights if type in ("tv", "series") else effective_movie_weights)
            else: score = ratings_dict

            if rating_already_cached:
                award_wins = cached_award_wins; award_noms = cached_award_noms; festival_label = cached_festival_label; age_rating = cached_age_rating; is_cult = cached_is_cult; is_true_story = cached_is_true_story; is_metacritic = cached_is_metacritic
            else:
                award_wins, award_noms = parse_mdblist_awards(keywords, tmdb_id=tmdb_id)
                kw_names = {(kw.get("name") or "").lower().strip() for kw in keywords}
                festival_label = next((label for kw, label in FESTIVAL_KEYWORDS.items() if kw in kw_names), None)
                is_cult = bool({"cult-classic", "cult-film"} & kw_names); is_true_story = "based-on-true-story" in kw_names; is_metacritic = "metacritic-must-see" in kw_names

        if imdb_id and not rating_failed and not rating_already_cached and effective_mdblist_key:
            set_cached_rating(imdb_id, ratings_dict if isinstance(ratings_dict, dict) else {}, genre, rel, award_wins, award_noms, awards_fetched=True, festival_label=festival_label, age_rating=age_rating, is_cult=is_cult, is_true_story=is_true_story, is_metacritic=is_metacritic)

        discovery_meta = extract_discovery_meta(tmdb_data=tmdb_data, media_type=type, award_wins=award_wins, award_noms=award_noms, trending_rank=trending_rank, release_date=rel, keywords=keywords if not rating_already_cached else [], festival_label_override=festival_label, is_cult_override=is_cult, is_true_story_override=is_true_story, is_metacritic_override=is_metacritic, is_digital_release_override=is_digital_release(imdb_id) if imdb_id else False)

        if debug and debug.strip() in ("1", "true"): return JSONResponse({"status": "ok", "message": "Debug output available"})

        _bp_args = dict(
            logo=logo if (is_textless and not is_no_poster and not rcfg.textless) else None,
            fallback_title=title if is_no_poster else (title if is_textless and not logo and not rcfg.textless else None),
            discovery_meta=discovery_meta, quality_tokens=quality_tokens, release_year=release_year, age_rating=age_rating, no_poster=is_no_poster,
        )

        def _composite_and_encode() -> bytes:
            result = build_poster_local(image, score, genre, rcfg, **_bp_args)
            buf = io.BytesIO()
            result.convert("RGB").save(buf, format="JPEG", quality=_cfg.JPEG_QUALITY)
            return buf.getvalue()

        img_bytes = await asyncio.get_running_loop().run_in_executor(None, _composite_and_encode)

        if final_cache_key is not None and not quality_pending and not rating_failed and not _rating_backoff_active:
            set_cached_final_poster(final_cache_key, img_bytes)

        if _render_fut is not None: _render_fut.set_result(img_bytes)

        response = Response(content=img_bytes, media_type="image/jpeg")
        if final_cache_key is not None: response.headers["ETag"] = f'"{final_cache_key}"'
        if _cfg.CDN_CACHE_TTL > 0: response.headers["Cache-Control"] = f"public, max-age={_cfg.CDN_CACHE_TTL}"
        return response

    except Exception as exc:
        if _render_fut is not None and not _render_fut.done(): _render_fut.set_exception(exc)
        logger.exception(f"Error building poster for tmdb_id={tmdb_id}")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        if _rating_event_to_set is not None:
            _rating_event_to_set.set(); _rating_fetch_inflight.pop(imdb_id, None)
        if final_cache_key is not None: _render_inflight.pop(final_cache_key, None)
