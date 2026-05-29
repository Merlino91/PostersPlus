import re

with open('discovery.py', 'r') as f:
    content = f.read()

content = content.replace('"short_film":  "Short Film",', '"short_film":  "Cortometraggio",')
content = content.replace('"mini_series": "Mini Series",', '"mini_series": "Mini Serie",')
content = content.replace('"binge_ready": "Binge Ready",', '"binge_ready": "Da Fare Maratona",')

content = content.replace('LANGUAGE_LABELS.get(lang, "Foreign")', 'LANGUAGE_LABELS.get(lang, "Lingua Originale")')

content = content.replace('return "Newly Streaming"', 'return "Nuovi Episodi"')
content = content.replace('return "Must-See" if meta.is_metacritic_must_see else None', 'return "Da Non Perdere" if meta.is_metacritic_must_see else None')
content = content.replace('return "True Story" if meta.is_true_story else None', 'return "Tratto da una storia vera" if meta.is_true_story else None')

with open('discovery.py', 'w') as f:
    f.write(content)
