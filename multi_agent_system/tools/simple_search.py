"""
tools/simple_search.py
SimpleSearch: Vektor DB olmadan basit metin benzerligi.
Kucuk projeler icin yeterli, buyuk projeler icin
ileride ChromaDB/FAISS entegre edilebilir.
"""
import re
from pathlib import Path


def search_relevant_files(project_path: str, query: str, top_k: int = 3) -> list:
    """
    Kullanicinin istegi ile en alakali proje dosyalarini bul.
    TF-IDF yerine basit keyword matching kullanir.

    Args:
        project_path: Proje kok dizini
        query: Arama sorgusu
        top_k: Dondurulecek maksimum sonuc sayisi

    Returns:
        En alakali dosyalarin listesi (score'a gore sirali)
    """
    root = Path(project_path)
    src_dir = root / "src"

    if not src_dir.exists():
        return []

    query_words = set(re.findall(r'\w+', query.lower()))
    scores = []

    for py_file in src_dir.glob("*.py"):
        if py_file.name == ".gitkeep":
            continue
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore").lower()
            file_words = set(re.findall(r'\w+', content))
            score = len(query_words & file_words)
            # Dosya adi eslesmesi bonus
            if any(w in py_file.stem for w in query_words):
                score += 5
            scores.append({
                "file": py_file.name,
                "path": str(py_file),
                "score": score,
                "preview": content[:300],
            })
        except Exception:
            pass

    scores.sort(key=lambda x: x["score"], reverse=True)
    return scores[:top_k]


def get_relevant_context(project_path: str, query: str) -> str:
    """
    /open modunda kullanicinin istegi ile ilgili
    sadece alakali dosyalari LLM'e ver.
    Tum projeyi gondermek yerine token tasarrufu.

    Args:
        project_path: Proje kok dizini
        query: Kullanici isteği

    Returns:
        Alakali dosya iceriklerini iceren context string
    """
    relevant = search_relevant_files(project_path, query)
    if not relevant:
        return "Ilgili dosya bulunamadi."

    context_parts = []
    for item in relevant:
        content = Path(item["path"]).read_text(encoding="utf-8", errors="ignore")
        context_parts.append(f"=== {item['file']} ===\n{content[:2000]}")

    return "\n\n".join(context_parts)
