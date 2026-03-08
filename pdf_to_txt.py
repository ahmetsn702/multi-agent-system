import sys
try:
    import fitz
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "PyMuPDF", "--quiet"])
    import fitz

doc = fitz.open(r"c:\Users\ahmed\OneDrive\Masaüstü\Multi-Agent\linter agent prompt.pdf")
text = ""
for page in doc:
    text += page.get_text()

with open(r"c:\Users\ahmed\OneDrive\Masaüstü\Multi-Agent\linter_prompt.txt", "w", encoding="utf-8") as f:
    f.write(text)
