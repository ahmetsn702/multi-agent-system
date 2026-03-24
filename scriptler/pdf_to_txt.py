import sys
try:
    import fitz
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "PyMuPDF", "--quiet"])
    import fitz

# Example usage:
# doc = fitz.open("path/to/input.pdf")
# text = ""
# for page in doc:
#     text += page.get_text()
# with open("output.txt", "w", encoding="utf-8") as f:
#     f.write(text)
