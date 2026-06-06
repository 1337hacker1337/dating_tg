import os

OUTPUT_FILE = "repopack-output.txt"
EXCLUDE_DIRS = {'.venv', 'venv', '__pycache__', '.git', '.idea', '.vscode'}
ALLOWED_EXTENSIONS = {'.py', '.json', '.sql', '.md', '.html'}

with open(OUTPUT_FILE, 'w', encoding='utf-8') as outfile:
    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for file in files:
            if file in [OUTPUT_FILE, 'pack.py']:
                continue
            if os.path.splitext(file)[1] in ALLOWED_EXTENSIONS:
                path = os.path.relpath(os.path.join(root, file))
                outfile.write(f"\n\n--- FILE: {path} ---\n\n")
                try:
                    with open(os.path.join(root, file), 'r', encoding='utf-8') as infile:
                        outfile.write(infile.read())
                except Exception:
                    pass

print(f"Готово! Всё упаковано в файл: {OUTPUT_FILE}")
