with open("main.py", "r") as f:
    text = f.read()

text = text.replace("from tmdb import composite_logo, fetch_logo, fetch_poster_metadata, fetch_poster_image, fetch_backdrop_image, fetch_trending_rank", "from tmdb import composite_logo, fetch_logo, fetch_poster_metadata, fetch_poster_image, fetch_backdrop_image, fetch_trending_rank, ensure_light_logo")

with open("main.py", "w") as f:
    f.write(text)
