import re

with open('main.py', 'r') as f:
    content = f.read()

# Top Gradient
top_logic_old = """
    # --- TOP GRADIENT (vectorised) ---
    top_height = int(height * 0.4)
    top_max_alpha = 220
    t_top = np.linspace(0, 1, top_height, dtype=np.float32)
    eased_top = ((1 - t_top) * top_max_alpha).astype(np.uint8)
    top_array = np.broadcast_to(eased_top[:, np.newaxis], (top_height, width)).copy()
    top_overlay = Image.fromarray(top_array, mode="L")
    top_tinted = Image.new("RGBA", (width, top_height), (0, 0, 0, 0))
    top_tinted.putalpha(top_overlay)
    image.paste(top_tinted, (0, 0), mask=top_tinted)
"""

top_logic_new = """
    # --- TOP GRADIENT (vectorised) ---
    if cfg.gradient_top_enable:
        top_height = int(height * 0.4)
        top_max_alpha = 220
        t_top = np.linspace(0, 1, top_height, dtype=np.float32)
        eased_top = ((1 - t_top) * top_max_alpha).astype(np.uint8)
        top_array = np.broadcast_to(eased_top[:, np.newaxis], (top_height, width)).copy()
        top_overlay = Image.fromarray(top_array, mode="L")

        dom = _get_dominant_color(image) if getattr(cfg, 'dominant_color_logic', False) else (0, 0, 0)
        top_tinted = Image.new("RGBA", (width, top_height), (dom[0], dom[1], dom[2], 0))
        top_tinted.putalpha(top_overlay)
        image.paste(top_tinted, (0, 0), mask=top_tinted)
"""

content = content.replace(top_logic_old.strip(), top_logic_new.strip())

# Bottom Gradient and Frosted Glass
bottom_logic_old = """
# --- BOTTOM GRADIENT (vectorised) ---
    bottom_height = int(height * 0.5)
    bottom_start = height - bottom_height

    if cfg.rating_display_mode == 4:
        # Stile Minimal ITA: Frosted Glass
        bottom_crop = image.crop((0, bottom_start, width, height))
        blurred_bottom = bottom_crop.filter(ImageFilter.GaussianBlur(radius=12))

        t_blur = np.linspace(0, 1, bottom_height, dtype=np.float32)
        eased_blur = ((t_blur ** 1.5) * 255).astype(np.uint8)
        blur_array = np.broadcast_to(eased_blur[:, np.newaxis], (bottom_height, width)).copy()
        blur_mask = Image.fromarray(blur_array, mode="L")

        image.paste(blurred_bottom, (0, bottom_start), mask=blur_mask)
        bottom_max_alpha = 230
        bottom_curve = 1.2
    else:
        bottom_max_alpha = 225 if cfg.rating_display_mode == 3 else 255
        bottom_curve = 1.2

    t_bot = np.linspace(0, 1, bottom_height, dtype=np.float32)
    eased_bot = ((1 - (1 - t_bot) ** bottom_curve) * bottom_max_alpha).astype(np.uint8)
    bottom_array = np.broadcast_to(eased_bot[:, np.newaxis], (bottom_height, width)).copy()
    bottom_overlay = Image.fromarray(bottom_array, mode="L")
    bottom_tinted = Image.new("RGBA", (width, bottom_height), (0, 0, 0, 0))
    bottom_tinted.putalpha(bottom_overlay)
    image.paste(bottom_tinted, (0, bottom_start), mask=bottom_tinted)
"""

bottom_logic_new = """
# --- BOTTOM GRADIENT (vectorised) ---
    bottom_height = int(height * 0.5)
    bottom_start = height - bottom_height

    if getattr(cfg, 'frosted_glass_intensity', 0) > 0:
        bottom_crop = image.crop((0, bottom_start, width, height))
        blurred_bottom = bottom_crop.filter(ImageFilter.GaussianBlur(radius=cfg.frosted_glass_intensity))

        t_blur = np.linspace(0, 1, bottom_height, dtype=np.float32)
        eased_blur = ((t_blur ** 1.5) * 255).astype(np.uint8)
        blur_array = np.broadcast_to(eased_blur[:, np.newaxis], (bottom_height, width)).copy()
        blur_mask = Image.fromarray(blur_array, mode="L")

        image.paste(blurred_bottom, (0, bottom_start), mask=blur_mask)

    if getattr(cfg, 'gradient_bottom_enable', True):
        bottom_max_alpha = 230 if getattr(cfg, 'frosted_glass_intensity', 0) > 0 else (225 if cfg.rating_display_mode == 3 else 255)
        bottom_curve = 1.2

        t_bot = np.linspace(0, 1, bottom_height, dtype=np.float32)
        eased_bot = ((1 - (1 - t_bot) ** bottom_curve) * bottom_max_alpha).astype(np.uint8)
        bottom_array = np.broadcast_to(eased_bot[:, np.newaxis], (bottom_height, width)).copy()
        bottom_overlay = Image.fromarray(bottom_array, mode="L")

        dom = _get_dominant_color(image) if getattr(cfg, 'dominant_color_logic', False) else (0, 0, 0)
        bottom_tinted = Image.new("RGBA", (width, bottom_height), (dom[0], dom[1], dom[2], 0))
        bottom_tinted.putalpha(bottom_overlay)
        image.paste(bottom_tinted, (0, bottom_start), mask=bottom_tinted)
"""

content = content.replace(bottom_logic_old.strip(), bottom_logic_new.strip())

with open('main.py', 'w') as f:
    f.write(content)
