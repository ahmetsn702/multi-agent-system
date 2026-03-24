import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from decimal import Decimal
import pytest
from calculator import topla, cikar, carp, bolme


def test_topla():
    """Toplama fonksiyonunu test eder."""
    assert topla(Decimal('5'), Decimal('3')) == Decimal('8')
    assert topla(Decimal('-2'), Decimal('7')) == Decimal('5')
    assert topla(Decimal('0'), Decimal('0')) == Decimal('0')


def test_cikar():
    """Çıkarma fonksiyonunu test eder."""
    assert cikar(Decimal('5'), Decimal('3')) == Decimal('2')
    assert cikar(Decimal('-2'), Decimal('7')) == Decimal('-9')
    assert cikar(Decimal('0'), Decimal('0')) == Decimal('0')


def test_carp():
    """Çarpma fonksiyonunu test eder."""
    assert carp(Decimal('5'), Decimal('3')) == Decimal('15')
    assert carp(Decimal('-2'), Decimal('7')) == Decimal('-14')
    assert carp(Decimal('0'), Decimal('5')) == Decimal('0')


def test_bolme_normal():
    """Bölme fonksiyonunu normal durumlar için test eder."""
    assert bolme(Decimal('10'), Decimal('2')) == Decimal('5')
    assert bolme(Decimal('-6'), Decimal('3')) == Decimal('-2')
    assert bolme(Decimal('7'), Decimal('1')) == Decimal('7')


def test_bolme_sifira_bolme():
    """Bölme fonksiyonunu sıfıra bölme hatası için test eder."""
    with pytest.raises(ValueError, match="Sıfıra bölme hatası! Bölen sıfır olamaz."):
        bolme(Decimal('10'), Decimal('0'))
