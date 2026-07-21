with open("discovery.py", "r") as f:
    text = f.read()

text = text.replace('"Season Finale"', '"Finale di Stagione"')

with open("discovery.py", "w") as f:
    f.write(text)
