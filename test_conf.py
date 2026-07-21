with open("configurator.html", "r") as f:
    text = f.read()
    if "Text & Typography" in text:
        print("YES")
    else:
        print("NO")
