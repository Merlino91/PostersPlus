with open("build_poster_orig.txt", "r") as f:
    orig = f.read()

# Make the changes required to build_poster to use the new fields in RequestConfig
import re

new_func = orig
new_func = re.sub(
r'    # --- TOP GRADIENT \(vectorised\) ---.*?(?=# --- Badge / quality overlay ---)',
r'''
    dom_color = _get_dominant_color(image)
    if cfg.sash_pill_dominant_color or cfg.gradient_color_mode == "dominant":
        text_color = _get_text_color(dom_color)
    else:
        text_color = (255, 255, 255)

    # --- TOP GRADIENT (vectorised) ---
    if cfg.top_gradient_enabled:
        top_height = int(height * 0.4)
        top_max_alpha = cfg.top_gradient_intensity
        t_top = np.linspace(0, 1, top_height, dtype=np.float32)
        eased_top = ((1 - t_top) * top_max_alpha).astype(np.uint8)
        top_array = np.broadcast_to(eased_top[:, np.newaxis], (top_height, width)).copy()
        top_overlay = Image.fromarray(top_array, mode="L")

        if cfg.gradient_color_mode == "dominant":
            top_tinted = Image.new("RGBA", (width, top_height), dom_color + (0,))
        else:
            top_tinted = Image.new("RGBA", (width, top_height), (0, 0, 0, 0))

        top_tinted.putalpha(top_overlay)
        image.paste(top_tinted, (0, 0), mask=top_tinted)

    # --- BOTTOM GRADIENT / FROSTED GLASS (vectorised) ---
    bottom_height = int(height * 0.5)
    bottom_start = height - bottom_height

    if cfg.rating_display_mode == 4:
        # Stile Minimal ITA: Frosted Glass
        bottom_crop = image.crop((0, bottom_start, width, height))
        blurred_bottom = bottom_crop.filter(ImageFilter.GaussianBlur(radius=cfg.bottom_frosted_glass_intensity))

        t_blur = np.linspace(0, 1, bottom_height, dtype=np.float32)
        eased_blur = ((t_blur ** 1.5) * 255).astype(np.uint8)
        blur_array = np.broadcast_to(eased_blur[:, np.newaxis], (bottom_height, width)).copy()
        blur_mask = Image.fromarray(blur_array, mode="L")

        image.paste(blurred_bottom, (0, bottom_start), mask=blur_mask)
        bottom_max_alpha = cfg.bottom_gradient_intensity if cfg.bottom_gradient_enabled else 0
        bottom_curve = 1.2
    else:
        if cfg.bottom_gradient_enabled:
            bottom_max_alpha = cfg.bottom_gradient_intensity
        else:
            bottom_max_alpha = 0
        bottom_curve = 1.2

    if bottom_max_alpha > 0:
        t_bot = np.linspace(0, 1, bottom_height, dtype=np.float32)
        eased_bot = ((1 - (1 - t_bot) ** bottom_curve) * bottom_max_alpha).astype(np.uint8)
        bottom_array = np.broadcast_to(eased_bot[:, np.newaxis], (bottom_height, width)).copy()
        bottom_overlay = Image.fromarray(bottom_array, mode="L")

        if cfg.gradient_color_mode == "dominant":
            bottom_tinted = Image.new("RGBA", (width, bottom_height), dom_color + (0,))
        else:
            bottom_tinted = Image.new("RGBA", (width, bottom_height), (0, 0, 0, 0))

        bottom_tinted.putalpha(bottom_overlay)
        image.paste(bottom_tinted, (0, bottom_start), mask=bottom_tinted)

''', new_func, flags=re.DOTALL)

with open("build_poster_new.txt", "w") as fout:
    fout.write(new_func)
