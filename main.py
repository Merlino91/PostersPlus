#main.py
import asyncio
import hashlib
import hmac
import io
import logging
import os
import re
import httpx
import json
import time
import numpy as np
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, HTMLResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S", force=True)
for _uv_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
    _uv_logger = logging.getLogger(_uv_name); _uv_logger.handlers = []; _uv_logger.propagate = True

class _TruncateUrlFilter(logging.Filter):
    _MAX = 80
    _KEY_RE = re.compile(r'((?:tmdb_key|mdblist_key|fanart_key|access_key|api_key|apikey)=)[^&\s\'\"]*', re.IGNORECASE)
    @classmethod
    def _redact(cls, value): return cls._KEY_RE.sub(r'\1***', value) if isinstance(value, str) else value
    def filter(self, record: logging.LogRecord) -> bool:
        if record.name == "uvicorn.access" and isinstance(record.args, tuple) and len(record.args) >= 3:
            path = record.args[2]
            if isinstance(path, str):
                path = self._KEY_RE.sub(r'\1***', path)
                if len(path) > self._MAX: path = path[: self._MAX] + "…"
                record.args = (record.args[0], record.args[1], path) + record.args[3:]
        if isinstance(record.msg, str): record.msg = self._redact(record.msg)
        if isinstance(record.args, tuple): record.args = tuple(self._redact(a) for a in record.args)
        elif isinstance(record.args, dict): record.args = {k: self._redact(v) for k, v in record.args.items()}
        if record.exc_info and not record.exc_text:
            import traceback; record.exc_text = self._redact("".join(traceback.format_exception(*record.exc_info)))
        elif record.exc_text: record.exc_text = self._redact(record.exc_text)
        return True

_url_filter = _TruncateUrlFilter()
for _handler in logging.getLogger().handlers: _handler.addFilter(_url_filter)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

_render_inflight: dict[str, "asyncio.Future[bytes]"] = {}
_quality_bg_inflight: set[str] = set()
_quality_bg_semaphore: "asyncio.Semaphore | None" = None
_rating_fetch_inflight: dict[str, asyncio.Event] = {}
_rating_backoff: dict[str, float] = {} 
_rating_fail_count: dict[str, int] = {}
_mdblist_semaphore: "asyncio.Semaphore | None" = None
_mdblist_key_cooldown: dict[str, float] = {}

from age_badge import draw_quality_age_badge, draw_tier_bar
from awards import FETCH_FAILED, _RateLimited, draw_award_badge, draw_award_sash, parse_mdblist_awards
from cache import (
    get_cached_quality, set_cached_quality, get_cached_rating, set_cached_rating,
    get_cached_final_poster, set_cached_final_poster, init_db, is_digital_release,
    delete_cached_tmdb_metadata, prune_caches, get_aod_mapping, update_aod_mapping,
    get_sys_meta, set_sys_meta
)
from digital_release import digital_release_poll_loop
import config as _cfg
from discovery import (
    ALL_PRIORITY_SLOTS, FESTIVAL_KEYWORDS, DiscoveryMeta, extract_discovery_meta, pick_sash,
)
from quality import BadgeItem, fetch_quality_from_aiostreams, get_resized_badge, parse_quality, render_badges_left
from ratings import calculate_weighted_score, draw_score_bar, fetch_rating, draw_score_bar_vertical
from tmdb import composite_logo, fetch_logo, fetch_poster_metadata, fetch_poster_image, fetch_backdrop_image, fetch_trending_rank

_HTTP_CLIENT: httpx.AsyncClient | None = None

def _make_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=12.0, write=5.0, pool=5.0), limits=httpx.Limits(max_connections=40, max_keepalive_connections=20, keepalive_expiry=30), headers={"Accept-Encoding": "identity"}, http2=False)

_TMDB_ID_RE  = re.compile(r'^\d{1,10}$')
_IMDB_ID_RE  = re.compile(r'^tt\d{1,10}$')
_VALID_TYPES = frozenset({"movie", "tv", "series"})

def _check_imdb_id(val: str) -> None:
    if val and not _IMDB_ID_RE.match(val): raise HTTPException(status_code=400, detail="Invalid imdb_id")

def _resolve_tmdb_key(query_key: str) -> str | None: return query_key if query_key else _cfg.SERVER_TMDB_KEY if _cfg.SERVER_TMDB_KEY else None
def _resolve_mdblist_key(query_key: str) -> str | None: return query_key if query_key else _cfg.SERVER_MDBLIST_KEY if _cfg.SERVER_MDBLIST_KEY else None
def _resolve_fanart_key(query_key: str) -> str | None: return query_key if query_key else _cfg.SERVER_FANART_KEY if _cfg.SERVER_FANART_KEY else None

@dataclass
class RequestConfig:
    show_award_sash: bool = field(default_factory=lambda: _cfg.SHOW_AWARD_SASH)
    badge_display_mode: int = field(default_factory=lambda: _cfg.BADGE_DISPLAY_MODE)
    rating_display_mode: int = field(default_factory=lambda: _cfg.SHOW_RATING_DISPLAY_MODE)
    accent_bar_font_size_ratio: float = field(default_factory=lambda: _cfg.ACCENT_BAR_MODE_FONT_SIZE_RATIO)
    numeric_score_font_size_ratio: float = field(default_factory=lambda: _cfg.NUMERIC_SCORE_MODE_FONT_SIZE_RATIO)
    accent_bar_y_offset: float = field(default_factory=lambda: _cfg.ACCENT_BAR_MODE_FONT_Y_OFFSET)
    numeric_score_y_offset: float = field(default_factory=lambda: _cfg.NUMERIC_SCORE_MODE_FONT_Y_OFFSET)
    score_glow_threshold: int = field(default_factory=lambda: _cfg.SCORE_GLOW_THRESHOLD)
    score_glow_blur: int = field(default_factory=lambda: _cfg.SCORE_GLOW_BLUR)
    score_glow_alpha: int = field(default_factory=lambda: _cfg.SCORE_GLOW_ALPHA)
    minimalist_mode_font_size_ratio: float = field(default_factory=lambda: _cfg.MINIMALIST_MODE_FONT_SIZE_RATIO)
    minimalist_mode_font_x_offset: float = field(default_factory=lambda: _cfg.MINIMALIST_MODE_FONT_X_OFFSET)
    minimalist_mode_font_y_offset: float = field(default_factory=lambda: _cfg.MINIMALIST_MODE_FONT_Y_OFFSET)
    logo_max_w_ratio: float = field(default_factory=lambda: _cfg.LOGO_MAX_W_RATIO)
    logo_max_h_ratio: float = field(default_factory=lambda: _cfg.LOGO_MAX_H_RATIO)
    logo_bottom_ratio: float = field(default_factory=lambda: _cfg.LOGO_BOTTOM_RATIO)
    badge_height: int = field(default_factory=lambda: _cfg.BADGE_HEIGHT)
    badge_gap: int = field(default_factory=lambda: _cfg.BADGE_GAP)
    badge_anchor_x: float = field(default_factory=lambda: _cfg.BADGE_ANCHOR_X_RATIO)
    badge_anchor_y: float = field(default_factory=lambda: _cfg.BADGE_ANCHOR_Y_RATIO)
    movie_weights: dict | None = None
    tv_weights: dict | None = None
    logo_language: str = field(default_factory=lambda: _cfg.DEFAULT_LOGO_LANGUAGE)
    sash_priority: list[str] = field(default_factory=lambda: list(_cfg.SASH_PRIORITY))
    muted: bool = False
    textless: bool = False
    score_color_mode: int = 2
    sash_badge: bool = False 
    sash_badge_x: float = 0.62 
    sash_badge_y: float = 0.04 
    frosted_glass_intensity: int = field(default_factory=lambda: _cfg.FROSTED_GLASS_INTENSITY)
    gradient_top_intensity: int = field(default_factory=lambda: _cfg.GRADIENT_TOP_INTENSITY)
    gradient_bottom_intensity: int = field(default_factory=lambda: _cfg.GRADIENT_BOTTOM_INTENSITY)
    dom_color_top: bool = field(default_factory=lambda: _cfg.DOM_COLOR_TOP)
    dom_color_bot: bool = field(default_factory=lambda: _cfg.DOM_COLOR_BOT)
    dom_color_sash: bool = field(default_factory=lambda: _cfg.DOM_COLOR_SASH)
    sash_style: str = field(default_factory=lambda: _cfg.SASH_STYLE)
    text_font_family: str = field(default_factory=lambda: _cfg.TEXT_FONT_FAMILY)
    text_drop_shadow: bool = field(default_factory=lambda: _cfg.TEXT_DROP_SHADOW)
    use_original_logo_color: bool = field(default_factory=lambda: _cfg.USE_ORIGINAL_LOGO_COLOR)
    minimal_pill_scale: float = field(default_factory=lambda: _cfg.MINIMAL_PILL_SCALE)

def _parse_bool(val: str | None, default: bool) -> bool: return default if val is None else val.strip().lower() not in ("0", "false", "no")
def _parse_weights(raw: str | None, sources: list[str]) -> dict | None:
    if not raw: return None
    out = {}
    try:
        for part in raw.split(","):
            if ":" not in part: continue
            key, val = part.split(":", 1)
            if key.strip().lower() in sources: out[key.strip().lower()] = max(0.0, min(1.0, float(val)))
    except Exception: return None
    return out if out else None

def _parse_sash_priority(raw: str | None) -> list[str]:
    if not raw: return list(_cfg.SASH_PRIORITY)
    tokens = [s.strip() for s in raw.split(",") if s.strip()]
    excluded  = {t[1:] for t in tokens if t.startswith("-") and t[1:] in ALL_PRIORITY_SLOTS}
    active    = [t for t in tokens if not t.startswith("-") and t in ALL_PRIORITY_SLOTS]
    if not active and not excluded: return list(_cfg.SASH_PRIORITY)
    active_set = set(active)
    for slot in _cfg.SASH_PRIORITY:
        if slot not in active_set and slot not in excluded: active.append(slot)
    return active

def build_request_config(params: dict) -> RequestConfig:
    cfg = RequestConfig()
    def _b(k, d): return _parse_bool(params.get(k), d)
    def _f(k, d, lo, hi):
        try: return max(lo, min(hi, float(params[k]))) if k in params else d
        except Exception: return d
    def _i(k, d, lo, hi):
        try: return max(lo, min(hi, int(params[k]))) if k in params else d
        except Exception: return d
    def _s(k, d): return params.get(k, d).strip() if k in params else d

    cfg.show_award_sash = _b("show_award_sash", cfg.show_award_sash)
    cfg.muted = _b("muted", cfg.muted)
    cfg.textless = _b("textless", cfg.textless)
    cfg.sash_badge = _b("sash_badge", cfg.sash_badge)
    cfg.frosted_glass_intensity = _i("frosted_glass_intensity", cfg.frosted_glass_intensity, 0, 250)
    cfg.gradient_top_intensity = _i("gradient_top_intensity", cfg.gradient_top_intensity, 0, 100)
    cfg.gradient_bottom_intensity = _i("gradient_bottom_intensity", cfg.gradient_bottom_intensity, 0, 100)
    cfg.dom_color_top = _b("dom_color_top", cfg.dom_color_top)
    cfg.dom_color_bot = _b("dom_color_bot", cfg.dom_color_bot)
    cfg.dom_color_sash = _b("dom_color_sash", cfg.dom_color_sash)
    cfg.sash_style = _s("sash_style", cfg.sash_style)
    font_family = _s("text_font_family", cfg.text_font_family)
    cfg.text_font_family = font_family if font_family in ("Inter", "Ubuntu", "Roboto", "Montserrat", "BebasNeue", "Poppins") else "Inter"
    cfg.text_drop_shadow = _b("text_drop_shadow", cfg.text_drop_shadow)
    cfg.use_original_logo_color = _b("use_original_logo_color", cfg.use_original_logo_color)
    cfg.minimal_pill_scale = _f("minimal_pill_scale", cfg.minimal_pill_scale, 0.1, 5.0)
    cfg.sash_badge_x = _f("sash_badge_x", cfg.sash_badge_x, 0.0, 1.0)
    cfg.sash_badge_y = _f("sash_badge_y", cfg.sash_badge_y, 0.0, 1.0)
    cfg.score_color_mode = _i("score_color_mode", cfg.score_color_mode, 0, 2)
    cfg.badge_display_mode = _i("badge_display_mode", cfg.badge_display_mode, 0, 4)
    cfg.rating_display_mode = _i("rating_display_mode", cfg.rating_display_mode, 0, 4)
    cfg.accent_bar_font_size_ratio = _f("accent_bar_font_size_ratio", cfg.accent_bar_font_size_ratio, 0.0, 0.5)
    cfg.numeric_score_font_size_ratio = _f("numeric_score_font_size_ratio", cfg.numeric_score_font_size_ratio, 0.0, 0.5)
    cfg.accent_bar_y_offset = _f("accent_bar_y_offset", cfg.accent_bar_y_offset, 0.0, 1.0)
    cfg.numeric_score_y_offset = _f("numeric_score_y_offset", cfg.numeric_score_y_offset, 0.0, 1.0)
    cfg.score_glow_threshold = _i("score_glow_threshold", cfg.score_glow_threshold, 0, 100)
    cfg.score_glow_blur = _i("score_glow_blur", cfg.score_glow_blur, 0, 50)
    cfg.score_glow_alpha = _i("score_glow_alpha", cfg.score_glow_alpha, 0, 255)
    cfg.minimalist_mode_font_size_ratio = _f("minimalist_mode_font_size_ratio", cfg.minimalist_mode_font_size_ratio, 0.0, 0.5)
    cfg.minimalist_mode_font_x_offset = _f("minimalist_mode_font_x_offset", cfg.minimalist_mode_font_x_offset, 0.0, 1.0)
    cfg.minimalist_mode_font_y_offset = _f("minimalist_mode_font_y_offset", cfg.minimalist_mode_font_y_offset, 0.0, 1.0)
    cfg.logo_max_w_ratio = _f("logo_max_w_ratio", cfg.logo_max_w_ratio, 0.0, 1.5)
    cfg.logo_max_h_ratio = _f("logo_max_h_ratio", cfg.logo_max_h_ratio, 0.0, 1.0)
    cfg.logo_bottom_ratio = _f("logo_bottom_ratio", cfg.logo_bottom_ratio, 0.0, 1.0)
    cfg.badge_height = _i("badge_height", cfg.badge_height, 1, 200)
    cfg.badge_gap = _i("badge_gap", cfg.badge_gap, 0, 100)
    cfg.badge_anchor_x = _f("badge_anchor_x", cfg.badge_anchor_x, 0.0, 1.0)
    cfg.badge_anchor_y = _f("badge_anchor_y", cfg.badge_anchor_y, 0.0, 1.0)
    cfg.movie_weights = _parse_weights(params.get("movie_weights"), list(_cfg.MOVIE_WEIGHTS.keys()))
    cfg.tv_weights = _parse_weights(params.get("tv_weights"), list(_cfg.TV_WEIGHTS.keys()))
    cfg.logo_language = params.get("logo_language", cfg.logo_language).strip().lower()
    cfg.sash_priority = _parse_sash_priority(params.get("sash_priority"))
    return cfg

async def _resolved(value): return value
async def _with_retry(coro_fn, *args, **kwargs):
    result = await coro_fn(*args, **kwargs)
    return await coro_fn(*args, **kwargs) if result is FETCH_FAILED else result

def _text_center(draw: ImageDraw.ImageDraw, text: str, font, cx: float, cy: float) -> tuple[float, float]:
    bbox = draw.textbbox((0, 0), text, font=font)
    x = cx - (bbox[2] - bbox[0]) / 2 - bbox[0]
    if hasattr(font, 'getmetrics'):
        ascent, descent = font.getmetrics()
        y = cy - (ascent + descent) / 2 - descent + int(ascent * 0.22)
    else:
        y = cy - (bbox[3] - bbox[1]) / 2 - bbox[1]
    return x, y

def _get_dominant_color(image: Image.Image) -> tuple[int, int, int]:
    small = image.copy(); small.thumbnail((50, 50)); colors = small.convert("RGB").getcolors(2500)
    if not colors: return (100, 100, 100)
    colors.sort(key=lambda t: t[0], reverse=True)
    for count, color in colors:
        if 40 < (0.299 * color[0] + 0.587 * color[1] + 0.114 * color[2]) < 215: return color
    return colors[0][1]

def draw_custom_top_tag(image: Image.Image, text: str, scale: float = 1.0, bg_color: tuple = (20, 20, 20), font_family: str = "Inter", drop_shadow: bool = False) -> Image.Image:
    width, height = image.size
    try: font = ImageFont.truetype(os.path.join(_FONTS_DIR, f"{font_family}-Bold.ttf"), int(24 * scale))
    except IOError: font = ImageFont.load_default()
    draw = ImageDraw.Draw(image); bbox = draw.textbbox((0, 0), text, font=font)
    pad_x, pad_y = int(20 * scale), int(12 * scale)
    pill_w, pill_h = (bbox[2] - bbox[0]) + pad_x * 2, (bbox[3] - bbox[1]) + pad_y * 2
    pill_x, pill_y, r = (width - pill_w) // 2, 0, int(10 * scale)
    overlay = Image.new("RGBA", (width, height), (0,0,0,0))
    if drop_shadow:
        shadow_layer = Image.new("RGBA", (width, height), (0,0,0,0)); shadow_draw = ImageDraw.Draw(shadow_layer)
        shadow_draw.rounded_rectangle([pill_x, pill_y, pill_x + pill_w, pill_y + pill_h], radius=r, fill=(0,0,0, 180))
        shadow_draw.rectangle([pill_x, pill_y, pill_x + pill_w, pill_y + r], fill=(0,0,0, 180))
        shifted = Image.new("RGBA", (width, height), (0,0,0,0)); shifted.paste(shadow_layer.filter(ImageFilter.GaussianBlur(int(5 * scale))), (0, int(3 * scale)))
        overlay = Image.alpha_composite(overlay, shifted)
    pill_layer = Image.new("RGBA", (width, height), (0,0,0,0)); pill_draw = ImageDraw.Draw(pill_layer)
    pill_draw.rounded_rectangle([pill_x, pill_y, pill_x + pill_w, pill_y + pill_h], radius=r, fill=(*bg_color[:3], 240))
    pill_draw.rectangle([pill_x, pill_y, pill_x + pill_w, pill_y + r], fill=(*bg_color[:3], 240))
    text_color = (250, 250, 250) if (0.299 * bg_color[0] + 0.587 * bg_color[1] + 0.114 * bg_color[2]) < 140 else (15, 15, 15)
    text_y = pill_y + (pill_h - sum(font.getmetrics())) // 2 if hasattr(font, 'getmetrics') else pill_y + pad_y
    pill_draw.text((pill_x + pad_x, text_y), text, font=font, fill=text_color)
    return Image.alpha_composite(image.convert("RGBA"), Image.alpha_composite(overlay, pill_layer))

async def _background_quality_fetch(imdb_id: str, media_type: str, season: int, episode: int, release_date: str | None) -> None:
    global _quality_bg_semaphore
    if _quality_bg_semaphore is None: _quality_bg_semaphore = asyncio.Semaphore(_cfg.QUALITY_BG_CONCURRENCY)
    try:
        async with _quality_bg_semaphore:
            if _HTTP_CLIENT: await _with_retry(fetch_quality_from_aiostreams, _HTTP_CLIENT, imdb_id, media_type, season, episode, release_date)
    except Exception as exc: logger.warning(f"Background quality fetch failed for {imdb_id}: {exc}")
    finally: _quality_bg_inflight.discard(imdb_id)

def _make_fallback_canvas(genre_ids: list[int] | None = None) -> Image.Image:
    tint = (1.0, 1.0, 1.4)
    if genre_ids:
        for gid in _cfg.GENRE_PRIORITY:
            if gid in set(genre_ids) and _cfg.GENRE_MAP.get(gid) in {"Horror":(3.2,0.3,0.3), "Sci-Fi":(0.3,1.2,3.2), "Action":(3.0,0.8,0.3), "Comedy":(2.6,2.4,0.3), "Drama":(0.3,0.3,2.6)}: # Trimmed for brevity
                tint = {"Horror":(3.2,0.3,0.3), "Sci-Fi":(0.3,1.2,3.2), "Action":(3.0,0.8,0.3), "Comedy":(2.6,2.4,0.3), "Drama":(0.3,0.3,2.6)}[_cfg.GENRE_MAP[gid]]; break
    r, g, b = tint; H, W = _cfg.POSTER_HEIGHT, _cfg.POSTER_WIDTH
    v = (10 + 8 * np.sin(np.linspace(0, np.pi, H, dtype=np.float32))).astype(np.float32)
    arr = np.zeros((H, W, 4), dtype=np.uint8); arr[:, :, 3] = 255
    arr[:, :, 0] = np.minimum(255, v * r).astype(np.uint8)[:, np.newaxis]
    arr[:, :, 1] = np.minimum(255, v * g).astype(np.uint8)[:, np.newaxis]
    arr[:, :, 2] = np.minimum(255, v * b).astype(np.uint8)[:, np.newaxis]
    return Image.fromarray(arr, "RGBA")

def build_poster(image: Image.Image, score: int | str, genre: str, cfg: RequestConfig, logo: Image.Image | None = None, fallback_title: str | None = None, discovery_meta: DiscoveryMeta | None = None, quality_tokens: list[str] | None = None, release_year: str | None = None, age_rating: int | None = None, no_poster: bool = False) -> Image.Image:
    width, height = image.size; draw = ImageDraw.Draw(image)
    dom_color = _get_dominant_color(image) if (cfg.dom_color_top or cfg.dom_color_bot or cfg.dom_color_sash) else (0, 0, 0)

    if cfg.gradient_top_intensity > 0:
        top_h = int(height * 0.25); top_alpha = int((cfg.gradient_top_intensity / 100) * 255)
        eased_top = ((1 - np.linspace(0, 1, top_h, dtype=np.float32)) * top_alpha).astype(np.uint8)
        top_tinted = Image.new("RGBA", (width, top_h), (*(dom_color if cfg.dom_color_top else (0,0,0)), 0))
        top_tinted.putalpha(Image.fromarray(np.broadcast_to(eased_top[:, np.newaxis], (top_h, width)).copy(), mode="L"))
        image.paste(top_tinted, (0, 0), mask=top_tinted)

    bot_h = int(height * 0.45); bot_start = height - bot_h
    if getattr(cfg, 'frosted_glass_intensity', 0) > 0:
        blurred = ImageEnhance.Contrast(ImageEnhance.Color(image.crop((0, bot_start, width, height)).filter(ImageFilter.GaussianBlur(cfg.frosted_glass_intensity / 10.0))).enhance(1.4)).enhance(1.15)
        blurred_arr = np.clip(np.array(blurred).astype(np.float32) + np.random.normal(0, 5, (bot_h, width, 3)).astype(np.float32), 0, 255).astype(np.uint8)
        blur_mask = Image.fromarray(((np.linspace(0, 1, bot_h, dtype=np.float32) ** 1.5) * 255).astype(np.uint8)[:, np.newaxis] * np.ones((1, width), dtype=np.uint8), mode="L")
        image.paste(Image.fromarray(blurred_arr, "RGBA"), (0, bot_start), mask=blur_mask)

    if cfg.gradient_bottom_intensity > 0:
        bot_alpha = int((cfg.gradient_bottom_intensity / 100) * 255)
        eased_bot = ((1 - (1 - np.linspace(0, 1, bot_h, dtype=np.float32)) ** 1.2) * bot_alpha).astype(np.uint8)
        bot_tinted = Image.new("RGBA", (width, bot_h), (*(dom_color if cfg.dom_color_bot else (0,0,0)), 0))
        bot_tinted.putalpha(Image.fromarray(np.broadcast_to(eased_bot[:, np.newaxis], (bot_h, width)).copy(), mode="L"))
        image.paste(bot_tinted, (0, bot_start), mask=bot_tinted)

    tokens = quality_tokens or []
    if cfg.badge_display_mode == 1: draw_quality_age_badge(image, age_rating, tokens, anchor_x_ratio=cfg.badge_anchor_x, anchor_y_ratio=cfg.badge_anchor_y, badge_height=cfg.badge_height)
    elif cfg.badge_display_mode == 3: draw_quality_age_badge(image, age_rating, [], anchor_x_ratio=cfg.badge_anchor_x, anchor_y_ratio=cfg.badge_anchor_y, badge_height=cfg.badge_height, always_silver=True)
    elif cfg.badge_display_mode == 4: draw_tier_bar(image, tokens, anchor_x_ratio=cfg.badge_anchor_x, anchor_y_ratio=cfg.badge_anchor_y, bar_height=cfg.badge_height)
    elif cfg.badge_display_mode == 2:
        filt = [t for t in tokens if t in {"4K", "1080P", "REMUX", "WEBDL", "DV", "HDR10+", "HDR10"}]
        if filt: render_badges_left(image, [(get_resized_badge(t, cfg.badge_height), _cfg.QUALITY_LABELS.get(t, t)) for t in filt], x_start=int(width*cfg.badge_anchor_x), y_top=int(height*cfg.badge_anchor_y), badge_height=cfg.badge_height, badge_gap=cfg.badge_gap)

    if logo: composite_logo(image, logo, max_w_ratio=cfg.logo_max_w_ratio, max_h_ratio=cfg.logo_max_h_ratio, bottom_ratio=cfg.logo_bottom_ratio)
    elif fallback_title:
        f_size = int(width * 0.1); title_cy = height - int(height * 0.20)
        while True:
            try: font = ImageFont.truetype(os.path.join(_FONTS_DIR, f"{cfg.text_font_family}-Bold.ttf"), f_size)
            except IOError: font = ImageFont.load_default(); break
            if (draw.textbbox((0, 0), fallback_title, font=font)[2] - draw.textbbox((0, 0), fallback_title, font=font)[0]) <= int(width * 0.82) or f_size <= 24: break
            f_size -= 2 
        tx, ty = _text_center(draw, fallback_title, font, width / 2, title_cy); soff = max(2, int(f_size * 0.04))
        draw.text((tx + soff, ty + soff), fallback_title, font=font, fill=(0, 0, 0, 180)); draw.text((tx, ty), fallback_title, font=font, fill=(255, 255, 255, 255))

    if cfg.rating_display_mode in (1, 2):
        r_font = int(width * (cfg.accent_bar_font_size_ratio if cfg.rating_display_mode == 1 else cfg.numeric_score_font_size_ratio))
        try: font_meta = ImageFont.truetype(os.path.join(_FONTS_DIR, f"{cfg.text_font_family}-Bold.ttf"), r_font)
        except IOError: font_meta = ImageFont.load_default()
        label = f"{genre} · {release_year}" if cfg.rating_display_mode == 1 and release_year else (f"{genre} ★ {score}" if cfg.rating_display_mode == 2 else genre)
        tx, ty = _text_center(draw, label, font_meta, width / 2, height * (cfg.accent_bar_y_offset if cfg.rating_display_mode == 1 else cfg.numeric_score_y_offset))
        draw.text((tx + 2, ty - int(r_font * 0.10) + 2), label, font=font_meta, fill=(0, 0, 0, 150)); draw.text((tx, ty - int(r_font * 0.10)), label, font=font_meta, fill=(200, 200, 200, 255))
        if cfg.rating_display_mode == 1: draw_score_bar(image, score, glow_threshold=cfg.score_glow_threshold, glow_blur=cfg.score_glow_blur, glow_alpha=cfg.score_glow_alpha, color_mode=cfg.score_color_mode)
    elif cfg.rating_display_mode == 3:
        try: font_meta = ImageFont.truetype(os.path.join(_FONTS_DIR, f"{cfg.text_font_family}-Bold.ttf"), int(width * cfg.minimalist_mode_font_size_ratio))
        except IOError: font_meta = ImageFont.load_default()
        y, right_edge, f_size = round(height * cfg.minimalist_mode_font_y_offset), width - int(width * cfg.minimalist_mode_font_x_offset), int(width * cfg.minimalist_mode_font_size_ratio)
        year_w = (draw.textbbox((0, 0), str(release_year or ""), font=font_meta)[2] - draw.textbbox((0, 0), str(release_year or ""), font=font_meta)[0]) if release_year else 0
        pip_w = max(4, int(f_size * 0.18)); pip_x = right_edge - year_w - int(f_size * 0.55) - pip_w
        draw.text((pip_x - int(f_size * 0.55) - (draw.textbbox((0, 0), genre, font=font_meta)[2] - draw.textbbox((0, 0), genre, font=font_meta)[0]), y), genre, font=font_meta, fill=(235, 235, 235, 255))
        if release_year: draw.text((pip_x + pip_w + int(f_size * 0.55), y), str(release_year), font=font_meta, fill=(235, 235, 235, 255))
        if score not in ("N/A", None): draw_score_bar_vertical(image, score, x=pip_x, y_center=round(y + f_size * 0.60), height=int(f_size * 1.4), width=pip_w, color_mode=cfg.score_color_mode)

    if cfg.show_award_sash and discovery_meta:
        sash_result = pick_sash(discovery_meta, cfg.sash_priority)
        if sash_result:
            if cfg.sash_style == "minimal_pill": image = draw_custom_top_tag(image, sash_result[0], scale=cfg.minimal_pill_scale, bg_color=dom_color if cfg.dom_color_sash else (20, 20, 20), font_family=cfg.text_font_family, drop_shadow=cfg.text_drop_shadow)
            elif cfg.sash_style == "corner_badge" or cfg.sash_badge: image = draw_award_badge(image, sash_result[0], sash_type=sash_result[1], x_ratio=cfg.sash_badge_x, y_ratio=cfg.sash_badge_y)
            else: image = draw_award_sash(image, sash_result[0], sash_type=sash_result[1], muted=cfg.muted)
    return image

async def _update_aod_loop():
    await asyncio.sleep(10)
    while True:
        last_update = get_sys_meta("aod_last_update")
        now = time.time()
        if not last_update or now - float(last_update) > 604800:
            logger.info("Checking AOD Database updates...")
            try:
                if _HTTP_CLIENT:
                    resp = await _HTTP_CLIENT.get(_cfg.AOD_URL, timeout=45.0)
                    if resp.status_code == 200:
                        def _parse():
                            data = resp.json(); m = []
                            for item in data.get("data", []):
                                k, t, mt = None, None, "tv"
                                for src in item.get("sources", []):
                                    if "kitsu.io/anime/" in src: k = src.split("/")[-1]
                                    elif "themoviedb.org/tv/" in src: t = src.split("/")[-1]; mt = "tv"
                                    elif "themoviedb.org/movie/" in src: t = src.split("/")[-1]; mt = "movie"
                                if k and t: m.append((k, t, mt))
                            return m
                        mappings = await asyncio.get_running_loop().run_in_executor(None, _parse)
                        if mappings:
                            update_aod_mapping(mappings); set_sys_meta("aod_last_update", str(now))
                            logger.info(f"AOD database updated with {len(mappings)} entries.")
            except Exception as e: logger.error(f"Failed to update AOD: {e}")
        await asyncio.sleep(86400)

async def _cache_prune_loop() -> None:
    await asyncio.sleep(300)
    while True:
        await asyncio.get_running_loop().run_in_executor(None, prune_caches)
        _now = asyncio.get_running_loop().time()
        for k in [k for k, v in _rating_backoff.items() if v <= _now]: del _rating_backoff[k]
        for k in [k for k, v in _mdblist_key_cooldown.items() if v <= _now]: del _mdblist_key_cooldown[k]
        await asyncio.sleep(21600)   

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _HTTP_CLIENT, _configurator_html
    init_db(); _HTTP_CLIENT = _make_http_client(); _configurator_html = _load_configurator_html()
    asyncio.create_task(_cache_prune_loop()); asyncio.create_task(digital_release_poll_loop(_HTTP_CLIENT)); asyncio.create_task(_update_aod_loop())
    yield
    await _HTTP_CLIENT.aclose()

app = FastAPI(lifespan=lifespan)
BASE_DIR = os.path.dirname(os.path.abspath(__file__)); _FONTS_DIR = os.path.join(BASE_DIR, "fonts")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

@app.middleware("http")
async def remove_server_header(request: Request, call_next):
    response = await call_next(request); response.headers["server"] = "unknown"; return response

@app.get("/server-caps")
async def server_caps(access_key: str = ""):
    if _cfg.ACCESS_KEY and not hmac.compare_digest(access_key, _cfg.ACCESS_KEY): raise HTTPException(status_code=403, detail="Unauthorized")
    return {"tmdb_key_set": bool(_cfg.SERVER_TMDB_KEY), "mdblist_key_set": bool(_cfg.SERVER_MDBLIST_KEY), "fanart_key_set": bool(_cfg.SERVER_FANART_KEY), "aiostreams_configured": bool(_cfg.AIOSTREAMS_URL and _cfg.AIOSTREAMS_AUTH)}

def _load_configurator_html() -> str:
    try:
        with open(os.path.join(os.path.dirname(__file__), "configurator.html"), "r", encoding="utf-8") as f: return f.read()
    except Exception: return "<h1>Configurator not found</h1>"

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
    if not _resolve_tmdb_key(tmdb_key): raise HTTPException(status_code=400, detail="No TMDB API key")
    resp = await _HTTP_CLIENT.get("https://api.themoviedb.org/3/search/multi", params={"api_key": _resolve_tmdb_key(tmdb_key), "query": q, "include_adult": "false", "page": "1"})
    return Response(content=resp.content, media_type="application/json", status_code=resp.status_code)

@app.get("/resolve-imdb")
async def resolve_imdb(tmdb_id: str, type: str = "movie", tmdb_key: str = "", access_key: str = ""):
    if _cfg.ACCESS_KEY and not hmac.compare_digest(access_key, _cfg.ACCESS_KEY): raise HTTPException(status_code=403, detail="Unauthorized")
    if not _resolve_tmdb_key(tmdb_key): raise HTTPException(status_code=400, detail="No TMDB API key")
    resp = await _HTTP_CLIENT.get(f"https://api.themoviedb.org/3/{'tv' if type == 'tv' else 'movie'}/{tmdb_id}/external_ids", params={"api_key": _resolve_tmdb_key(tmdb_key)})
    return Response(content=resp.content, media_type="application/json", status_code=resp.status_code)


@app.get("/poster")
async def get_poster(
    request: Request, tmdb_id: str = "", imdb_id: str = "", kitsu_id: str = "", type: str = "movie", quality: str = "", season: int = 1, episode: int = 1,
    access_key: str = "", mdblist_key: str = "", tmdb_key: str = "", fanart_key: str = "", debug: str | None = None,
):
    if _cfg.ACCESS_KEY and not hmac.compare_digest(access_key, _cfg.ACCESS_KEY): raise HTTPException(status_code=403, detail="Unauthorized")

    if not tmdb_id and kitsu_id:
        mapping = get_aod_mapping(kitsu_id)
        if mapping: tmdb_id, type = mapping
    
    if not tmdb_id: raise HTTPException(status_code=400, detail="Missing tmdb_id or valid kitsu_id")

    _check_tmdb_id(tmdb_id); _check_imdb_id(imdb_id); _check_type(type)
    effective_tmdb_key, effective_mdblist_key, effective_fanart_key = _resolve_tmdb_key(tmdb_key), _resolve_mdblist_key(mdblist_key), _resolve_fanart_key(fanart_key)
    if not effective_tmdb_key: raise HTTPException(status_code=400, detail="No TMDB API key available.")

    raw_params = { k: v for k, v in request.query_params.items() if k not in ("tmdb_id", "imdb_id", "kitsu_id", "mdblist_key", "tmdb_key", "fanart_key", "type", "quality", "season", "episode", "access_key", "debug") }
    rcfg = build_request_config(raw_params)

    if not quality:
        final_cache_key = f"{imdb_id}:{type}:" + hashlib.md5("&".join(f"{k}={v}" for k, v in sorted(raw_params.items())).encode()).hexdigest()[:8]
        cached_jpeg = get_cached_final_poster(final_cache_key)
        if cached_jpeg is not None:
            if request.headers.get("if-none-match") == f'"{final_cache_key}"': return Response(status_code=304)
            r = Response(content=cached_jpeg, media_type="image/jpeg"); r.headers["ETag"] = f'"{final_cache_key}"'
            if _cfg.CDN_CACHE_TTL > 0: r.headers["Cache-Control"] = f"public, max-age={_cfg.CDN_CACHE_TTL}"
            return r
    else: final_cache_key = None

    _render_fut = None
    if final_cache_key is not None:
        if final_cache_key in _render_inflight:
            try:
                r = Response(content=await _render_inflight[final_cache_key], media_type="image/jpeg"); r.headers["ETag"] = f'"{final_cache_key}"'
                if _cfg.CDN_CACHE_TTL > 0: r.headers["Cache-Control"] = f"public, max-age={_cfg.CDN_CACHE_TTL}"
                return r
            except Exception: pass
        _render_fut = asyncio.get_running_loop().create_future(); _render_fut.add_done_callback(lambda f: f.exception() if not f.cancelled() and f.exception() else None); _render_inflight[final_cache_key] = _render_fut

    cached_rating = get_cached_rating(imdb_id)
    if cached_rating is not None: (cached_ratings_dict, cached_genre, cached_release_date, cached_award_wins, cached_award_noms, cached_awards_fetched, cached_festival_label, cached_age_rating, cached_is_cult, cached_is_true_story, cached_is_metacritic) = cached_rating
    else: cached_ratings_dict = cached_genre = cached_release_date = cached_festival_label = cached_age_rating = None; cached_award_wins = []; cached_award_noms = []; cached_awards_fetched = cached_is_cult = cached_is_true_story = cached_is_metacritic = False

    release_date_for_quality_ttl, rating_already_cached, _rating_event_to_set, _rating_backoff_active = cached_release_date, cached_rating is not None, None, False

    if not rating_already_cached and effective_mdblist_key:
        _loop_now = asyncio.get_running_loop().time()
        if _loop_now < _mdblist_key_cooldown.get(effective_mdblist_key, 0.0): effective_mdblist_key = None; _rating_backoff_active = True
        if effective_mdblist_key:
            if imdb_id in _rating_backoff and _loop_now < _rating_backoff[imdb_id]: effective_mdblist_key = None; _rating_backoff_active = True
            elif imdb_id in _rating_backoff: del _rating_backoff[imdb_id]; _rating_fail_count.pop(imdb_id, None)

    if not rating_already_cached and effective_mdblist_key:
        if imdb_id in _rating_fetch_inflight:
            await _rating_fetch_inflight[imdb_id].wait()
            _refreshed = get_cached_rating(imdb_id)
            if _refreshed is not None: (cached_ratings_dict, cached_genre, cached_release_date, cached_award_wins, cached_award_noms, cached_awards_fetched, cached_festival_label, cached_age_rating, cached_is_cult, cached_is_true_story, cached_is_metacritic) = _refreshed; rating_already_cached = True; release_date_for_quality_ttl = cached_release_date
            elif imdb_id in _rating_backoff and asyncio.get_running_loop().time() < _rating_backoff[imdb_id]: effective_mdblist_key = None
        else: _rating_event_to_set = asyncio.Event(); _rating_fetch_inflight[imdb_id] = _rating_event_to_set

    if quality: quality_tokens = parse_quality(quality); cached_tokens = None
    else: cached_tokens = get_cached_quality(imdb_id, release_date_for_quality_ttl); quality_tokens = cached_tokens or []
    quality_pending = False
    if rcfg.badge_display_mode in (1, 2, 4) and not quality and cached_tokens is None:
        if imdb_id not in _quality_bg_inflight: _quality_bg_inflight.add(imdb_id); asyncio.create_task(_background_quality_fetch(imdb_id, type, season, episode, release_date_for_quality_ttl))
        quality_pending = True

    try:
        genre_ids, is_textless, logos, release_year, title, poster_path, backdrop_path, tmdb_data = await fetch_poster_metadata(_HTTP_CLIENT, tmdb_id, effective_tmdb_key, type, rcfg.logo_language)
        _use_backdrop = bool(backdrop_path) and (poster_path is None or not is_textless)
        if _use_backdrop: is_textless = True         

        if rating_already_cached or not effective_mdblist_key: rating_coro = _resolved((cached_ratings_dict, cached_genre, cached_release_date, [], cached_age_rating))
        else:
            global _mdblist_semaphore
            if _mdblist_semaphore is None: _mdblist_semaphore = asyncio.Semaphore(_cfg.MDBLIST_CONCURRENCY)
            async def _fetch_rating_gated():
                async with _mdblist_semaphore: return await _with_retry(fetch_rating, _HTTP_CLIENT, imdb_id, effective_mdblist_key, genre_ids, type, movie_weights=rcfg.movie_weights or _cfg.MOVIE_WEIGHTS, tv_weights=rcfg.tv_weights or _cfg.TV_WEIGHTS)
            rating_coro = _fetch_rating_gated()

        is_no_poster = poster_path is None and not _use_backdrop
        if _use_backdrop: _image_coro = fetch_backdrop_image(_HTTP_CLIENT, tmdb_id, backdrop_path)
        elif is_no_poster: _image_coro = _resolved(_make_fallback_canvas(genre_ids))
        else: _image_coro = fetch_poster_image(_HTTP_CLIENT, tmdb_id, type, poster_path)

        (image, logo, rating_result, trending_rank) = await asyncio.gather(_image_coro, fetch_logo(_HTTP_CLIENT, tmdb_id, type, effective_tmdb_key, effective_fanart_key, logos, rcfg.logo_language, getattr(rcfg, 'use_original_logo_color', False)) if (is_textless and not is_no_poster) else _resolved(None), rating_coro, fetch_trending_rank(_HTTP_CLIENT, tmdb_id, effective_tmdb_key, type))

        rate_limited, rating_failed = isinstance(rating_result, _RateLimited), not rating_already_cached and effective_mdblist_key and (rating_result is FETCH_FAILED or isinstance(rating_result, _RateLimited))
        if rating_failed:
            if rate_limited:
                _global_window = min(min(float(rating_result.retry_after), 3600.0) if rating_result.retry_after else 3600.0, 120.0)
                if effective_mdblist_key and asyncio.get_running_loop().time() + _global_window > _mdblist_key_cooldown.get(effective_mdblist_key, 0.0): _mdblist_key_cooldown[effective_mdblist_key] = asyncio.get_running_loop().time() + _global_window
            else:
                _rating_fail_count[imdb_id] = _rating_fail_count.get(imdb_id, 0) + 1
            _rating_backoff[imdb_id] = asyncio.get_running_loop().time() + min(30 * (4 ** (_rating_fail_count.get(imdb_id, 1) - 1)), 3600.0)
            ratings_dict, genre, rel, score, keywords, award_wins, award_noms, festival_label, age_rating, is_cult, is_true_story, is_metacritic = {}, cached_genre or next((_cfg.GENRE_MAP.get(g, "") for g in _cfg.GENRE_PRIORITY if g in set(genre_ids) and _cfg.GENRE_MAP.get(g, "")), "Unknown"), cached_release_date, "N/A", [], cached_award_wins, cached_award_noms, cached_festival_label, cached_age_rating, cached_is_cult, cached_is_true_story, cached_is_metacritic
        else:
            ratings_dict, genre, rel, keywords, age_rating = rating_result
            genre = genre or next((_cfg.GENRE_MAP.get(g, "") for g in _cfg.GENRE_PRIORITY if g in set(genre_ids) and _cfg.GENRE_MAP.get(g, "")), "Unknown")
            if not rating_already_cached and not _rating_backoff_active: _rating_fail_count.pop(imdb_id, None)
            score = calculate_weighted_score(ratings_dict, rcfg.tv_weights or _cfg.TV_WEIGHTS if type in ("tv", "series") else rcfg.movie_weights or _cfg.MOVIE_WEIGHTS) if isinstance(ratings_dict, dict) else ratings_dict
            if rating_already_cached: award_wins, award_noms, festival_label, age_rating, is_cult, is_true_story, is_metacritic = cached_award_wins, cached_award_noms, cached_festival_label, cached_age_rating, cached_is_cult, cached_is_true_story, cached_is_metacritic
            else:
                award_wins, award_noms = parse_mdblist_awards(keywords, tmdb_id=tmdb_id)
                kw_names = {(kw.get("name") or "").lower().strip() for kw in keywords}
                festival_label = next((label for kw, label in FESTIVAL_KEYWORDS.items() if kw in kw_names), None)
                is_cult, is_true_story, is_metacritic = bool({"cult-classic", "cult-film"} & kw_names), "based-on-true-story" in kw_names, "metacritic-must-see" in kw_names

        if not rating_failed and not rating_already_cached and effective_mdblist_key: set_cached_rating(imdb_id, ratings_dict if isinstance(ratings_dict, dict) else {}, genre, rel, award_wins, award_noms, awards_fetched=True, festival_label=festival_label, age_rating=age_rating, is_cult=is_cult, is_true_story=is_true_story, is_metacritic=is_metacritic)

        discovery_meta = extract_discovery_meta(tmdb_data=tmdb_data, media_type=type, award_wins=award_wins, award_noms=award_noms, trending_rank=trending_rank, release_date=rel, keywords=keywords if not rating_already_cached else [], festival_label_override=festival_label, is_cult_override=is_cult, is_true_story_override=is_true_story, is_metacritic_override=is_metacritic, is_digital_release_override=is_digital_release(imdb_id))

        if debug and debug.strip() in ("1", "true"): return JSONResponse({"status": "ok"})

        def _composite_and_encode() -> bytes:
            result = build_poster(image, score, genre, rcfg, logo=logo if (is_textless and not is_no_poster and not rcfg.textless) else None, fallback_title=title if is_no_poster else (title if is_textless and not logo and not rcfg.textless else None), discovery_meta=discovery_meta, quality_tokens=quality_tokens, release_year=release_year, age_rating=age_rating, no_poster=is_no_poster)
            buf = io.BytesIO(); result.convert("RGB").save(buf, format="JPEG", quality=_cfg.JPEG_QUALITY); return buf.getvalue()

        img_bytes = await asyncio.get_running_loop().run_in_executor(None, _composite_and_encode)

        if final_cache_key is not None and not quality_pending and not rating_failed and not _rating_backoff_active: set_cached_final_poster(final_cache_key, img_bytes)
        if _render_fut is not None: _render_fut.set_result(img_bytes)

        r = Response(content=img_bytes, media_type="image/jpeg")
        if final_cache_key is not None: r.headers["ETag"] = f'"{final_cache_key}"'
        if _cfg.CDN_CACHE_TTL > 0: r.headers["Cache-Control"] = f"public, max-age={_cfg.CDN_CACHE_TTL}"
        return r

    except Exception as exc:
        if _render_fut is not None and not _render_fut.done(): _render_fut.set_exception(exc)
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        if _rating_event_to_set is not None: _rating_event_to_set.set(); _rating_fetch_inflight.pop(imdb_id, None)
        if final_cache_key is not None: _render_inflight.pop(final_cache_key, None)
