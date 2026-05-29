import py_compile
try:
    py_compile.compile('main.py', doraise=True)
    py_compile.compile('tmdb.py', doraise=True)
    print("Syntax OK")
except py_compile.PyCompileError as e:
    print(f"Syntax Error: {e}")
