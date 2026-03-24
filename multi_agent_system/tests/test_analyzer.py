"""
tests/test_analyzer.py
AnalyzerAgent ve code_analyzer aracı için birim testleri.
"""
import os
import sys
import tempfile
import zipfile
from pathlib import Path

import pytest

from tools.code_analyzer import (
    analyze_project,
    analyze_from_source,
    read_zip,
    _extract_python_info,
    _find_suspicious,
)


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def temp_project(tmp_path):
    """Geçici proje klasörü oluştur."""
    src = tmp_path / "src"
    src.mkdir()

    # Basit Python dosyası
    (src / "main.py").write_text(
        '''import os
import sys

def merhaba(isim: str) -> str:
    """Selamlama fonksiyonu."""
    try:
        return f"Merhaba, {isim}!"
    except:  # bare except
        pass

password = "supersecret123"  # hardcoded şifre

if __name__ == "__main__":
    print(merhaba("Dünya"))
''',
        encoding="utf-8",
    )

    # Test dosyası
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text(
        '''import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from main import merhaba

def test_merhaba():
    assert merhaba("Ahmet") == "Merhaba, Ahmet!"
''',
        encoding="utf-8",
    )

    return tmp_path


@pytest.fixture
def temp_zip(temp_project, tmp_path):
    """Proje klasörünü ZIP olarak sıkıştır."""
    zip_path = tmp_path / "proje.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for f in temp_project.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(temp_project))
    return zip_path


# ── Birim Testler ─────────────────────────────────────────────────────────


class TestExtractPythonInfo:
    """_extract_python_info() birim testleri."""

    def test_fonksiyon_tespiti(self):
        """Fonksiyon isimleri doğru çıkarılmalı."""
        code = "def foo(): pass\ndef bar(): pass"
        info = _extract_python_info(code, "test.py")
        assert "foo" in info["functions"]
        assert "bar" in info["functions"]

    def test_sinif_tespiti(self):
        """Sınıf isimleri doğru çıkarılmalı."""
        code = "class MyClass:\n    pass"
        info = _extract_python_info(code, "test.py")
        assert "MyClass" in info["classes"]

    def test_import_tespiti(self):
        """Import'lar doğru çıkarılmalı."""
        code = "import os\nfrom pathlib import Path"
        info = _extract_python_info(code, "test.py")
        assert "os" in info["imports"]
        assert "pathlib" in info["imports"]

    def test_syntax_hatasi(self):
        """Syntax hatalı dosyalarda syntax_error True olmalı."""
        code = "def broken(:\n    pass"
        info = _extract_python_info(code, "broken.py")
        assert info.get("syntax_error") is True

    def test_has_main(self):
        """__main__ bloğu tespiti."""
        code = 'if __name__ == "__main__":\n    pass'
        info = _extract_python_info(code, "main.py")
        assert info["has_main"] is True


class TestFindSuspicious:
    """_find_suspicious() birim testleri."""

    def test_bare_except(self):
        """Bare except tespiti."""
        code = "try:\n    pass\nexcept:\n    pass"
        issues = _find_suspicious(code, "test.py")
        descriptions = [i["description"] for i in issues]
        assert any("Bare except" in d for d in descriptions)

    def test_hardcoded_password(self):
        """Hardcoded şifre tespiti."""
        code = 'password = "secret123"'
        issues = _find_suspicious(code, "test.py")
        descriptions = [i["description"] for i in issues]
        assert any("şifre" in d.lower() for d in descriptions)

    def test_eval_tespiti(self):
        """eval() güvenlik riski tespiti."""
        code = "result = eval(user_input)"
        issues = _find_suspicious(code, "test.py")
        descriptions = [i["description"] for i in issues]
        assert any("eval" in d.lower() for d in descriptions)

    def test_temiz_kod(self):
        """Temiz kodda sorun bulunmamalı."""
        code = "def temiz():\n    return 42"
        issues = _find_suspicious(code, "clean.py")
        assert len(issues) == 0


class TestAnalyzeProject:
    """analyze_project() entegrasyon testleri."""

    def test_mevcut_klasor(self, temp_project):
        """Geçerli klasör analizi."""
        result = analyze_project(str(temp_project))
        assert "error" not in result
        assert result["stats"]["python_files"] >= 1
        assert "structure" in result
        assert result["stats"]["file_count"] >= 1

    def test_olmayan_klasor(self):
        """Olmayan klasörde hata döndürmeli."""
        result = analyze_project("/olmayan/yol/buraya")
        assert "error" in result

    def test_sorun_tespiti(self, temp_project):
        """Şüpheli kalıplar tespit edilmeli."""
        result = analyze_project(str(temp_project))
        # main.py'de bare except ve hardcoded password var
        assert result["stats"]["issue_count"] > 0

    def test_dependency_graph(self, temp_project):
        """Bağımlılık grafiği oluşturulmalı."""
        result = analyze_project(str(temp_project))
        assert isinstance(result["dependency_graph"], dict)


class TestReadZip:
    """read_zip() testleri."""

    def test_gecerli_zip(self, temp_zip):
        """Geçerli ZIP analiz edilebilmeli."""
        result = read_zip(str(temp_zip))
        assert "error" not in result
        assert result["stats"]["python_files"] >= 1

    def test_olmayan_zip(self):
        """Olmayan ZIP'te hata döndürmeli."""
        result = read_zip("/olmayan/proje.zip")
        assert "error" in result


class TestAnalyzeFromSource:
    """analyze_from_source() kaynak tipi tespiti testleri."""

    def test_klasor_kaynak(self, temp_project):
        """Klasör yolu tanınmalı."""
        result = analyze_from_source(str(temp_project))
        assert "error" not in result

    def test_zip_kaynak(self, temp_zip):
        """ZIP kaynağı tanınmalı."""
        result = analyze_from_source(str(temp_zip))
        assert "error" not in result

    def test_tanimsiz_kaynak(self):
        """Tanımsız kaynak için hata döndürmeli."""
        result = analyze_from_source("/bu/kesinlikle/yok")
        assert "error" in result
