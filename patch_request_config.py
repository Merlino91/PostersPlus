import re

with open('main.py', 'r') as f:
    content = f.read()

config_fields = """
    # Nuovi attributi V2
    frosted_glass_intensity: int = field(default_factory=lambda: _cfg.FROSTED_GLASS_INTENSITY)
    gradient_top_enable: bool = field(default_factory=lambda: _cfg.GRADIENT_TOP_ENABLE)
    gradient_bottom_enable: bool = field(default_factory=lambda: _cfg.GRADIENT_BOTTOM_ENABLE)
    dominant_color_logic: bool = field(default_factory=lambda: _cfg.DOMINANT_COLOR_LOGIC)
    sash_style: str = field(default_factory=lambda: _cfg.SASH_STYLE)
    text_font_family: str = field(default_factory=lambda: _cfg.TEXT_FONT_FAMILY)
    text_drop_shadow: bool = field(default_factory=lambda: _cfg.TEXT_DROP_SHADOW)
    use_original_logo_color: bool = field(default_factory=lambda: _cfg.USE_ORIGINAL_LOGO_COLOR)
    minimal_pill_scale: float = field(default_factory=lambda: _cfg.MINIMAL_PILL_SCALE)
"""

content = content.replace("    sash_badge_y: float = 0.04   # badge top-edge  as fraction of poster height",
                          "    sash_badge_y: float = 0.04   # badge top-edge  as fraction of poster height\n" + config_fields)

parser_logic = """
    def _s(key, default):
        return params.get(key, default).strip() if key in params else default

    cfg.frosted_glass_intensity = _i("frosted_glass_intensity", cfg.frosted_glass_intensity, 0, 100)
    cfg.gradient_top_enable = _b("gradient_top_enable", cfg.gradient_top_enable)
    cfg.gradient_bottom_enable = _b("gradient_bottom_enable", cfg.gradient_bottom_enable)
    cfg.dominant_color_logic = _b("dominant_color_logic", cfg.dominant_color_logic)
    cfg.sash_style = _s("sash_style", cfg.sash_style)
    cfg.text_font_family = _s("text_font_family", cfg.text_font_family)
    cfg.text_drop_shadow = _b("text_drop_shadow", cfg.text_drop_shadow)
    cfg.use_original_logo_color = _b("use_original_logo_color", cfg.use_original_logo_color)
    cfg.minimal_pill_scale = _f("minimal_pill_scale", cfg.minimal_pill_scale, 0.1, 5.0)
"""

content = content.replace("    cfg.sash_badge              = _b(\"sash_badge\",             cfg.sash_badge)",
                          "    cfg.sash_badge              = _b(\"sash_badge\",             cfg.sash_badge)\n" + parser_logic)

with open('main.py', 'w') as f:
    f.write(content)
