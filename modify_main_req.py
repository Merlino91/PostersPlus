with open("main.py", "r") as f:
    text = f.read()

import re
replacement = """    logo_max_w_ratio:  float = field(default_factory=lambda: _cfg.LOGO_MAX_W_RATIO)
    logo_max_h_ratio:  float = field(default_factory=lambda: _cfg.LOGO_MAX_H_RATIO)
    logo_bottom_ratio: float = field(default_factory=lambda: _cfg.LOGO_BOTTOM_RATIO)
    badge_height:      int   = field(default_factory=lambda: _cfg.BADGE_HEIGHT)
    badge_gap:         int   = field(default_factory=lambda: _cfg.BADGE_GAP)
    badge_anchor_x:    float = field(default_factory=lambda: _cfg.BADGE_ANCHOR_X_RATIO)
    badge_anchor_y:    float = field(default_factory=lambda: _cfg.BADGE_ANCHOR_Y_RATIO)
    logo_language:     str   = field(default_factory=lambda: _cfg.DEFAULT_LOGO_LANGUAGE)
    textless:          bool  = False
    sash_priority:     list[str] | None = None
    sash_badge:        bool  = False
    sash_style:        str   = "ribbon"  # ribbon, badge, pill
    sash_badge_x:      float = 0.62
    sash_badge_y:      float = 0.04
    sash_pill_scale:   float = field(default_factory=lambda: _cfg.SASH_PILL_SCALE)
    sash_pill_dominant_color: bool = field(default_factory=lambda: _cfg.SASH_PILL_DOMINANT_COLOR)
    sash_shadow:       bool  = field(default_factory=lambda: _cfg.SASH_SHADOW)
    muted:             bool  = False

    # Overlays
    bottom_frosted_glass_intensity: int = field(default_factory=lambda: _cfg.BOTTOM_FROSTED_GLASS_INTENSITY)
    top_gradient_enabled: bool = field(default_factory=lambda: _cfg.TOP_GRADIENT_ENABLED)
    bottom_gradient_enabled: bool = field(default_factory=lambda: _cfg.BOTTOM_GRADIENT_ENABLED)
    gradient_color_mode: str = field(default_factory=lambda: _cfg.GRADIENT_COLOR_MODE)
    top_gradient_intensity: int = field(default_factory=lambda: _cfg.TOP_GRADIENT_INTENSITY)
    bottom_gradient_intensity: int = field(default_factory=lambda: _cfg.BOTTOM_GRADIENT_INTENSITY)

    # Typography
    text_drop_shadow: bool = field(default_factory=lambda: _cfg.TEXT_DROP_SHADOW)
    font_family: str = field(default_factory=lambda: _cfg.FONT_FAMILY)

    # Logo
    logo_original_colors: bool = field(default_factory=lambda: _cfg.LOGO_ORIGINAL_COLORS)"""

text = re.sub(r'    logo_max_w_ratio:\s*float = field\(default_factory=lambda: _cfg\.LOGO_MAX_W_RATIO\).*?muted:\s*bool\s*=\s*False',
              replacement, text, flags=re.DOTALL)

with open("main.py", "w") as f:
    f.write(text)
