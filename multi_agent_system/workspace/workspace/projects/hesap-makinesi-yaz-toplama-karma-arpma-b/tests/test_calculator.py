import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from calculator import add, subtract, multiply, divide
except ImportError:
    # Eğer src dizini farklı bir yapıdaysa veya modül bulunamıyorsa 
    # sys.path'i mevcut dizini içerecek şekilde güncelliyoruz
    sys.path.insert(0, str(Path(__file__).parent))
    from calculator import add, subtract, multiply, divide

def test_add():
    """Toplama fonksiyonunu test eder."""
    assert add(2, 3) == 5
    assert add(-1, 1) == 0

def test_subtract():
    """Cikarma fonksiyonunu test eder."""
    assert subtract(5, 3) == 2
    assert subtract(3, 5) == -2

def test_multiply():
    """Carpma fonksiyonunu test eder."""
    assert multiply(2, 3) == 6
    assert multiply(0, 5) == 0

def test_divide():
    """Bolme fonksiyonunu test eder."""
    assert divide(6, 3) == 2.0
    with pytest.raises(ZeroDivisionError):
        divide(5, 0)