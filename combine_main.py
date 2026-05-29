with open("main.py", "r") as f:
    text = f.read()

with open("build_poster_new2.txt", "r") as f:
    new_bp = f.read()

# find end of build_poster
start_idx = text.find("def build_poster(")
end_idx = text.find("async def _cache_prune_loop")

text = text[:start_idx] + new_bp + "\n\n" + text[end_idx:]

with open("main.py", "w") as f:
    f.write(text)
