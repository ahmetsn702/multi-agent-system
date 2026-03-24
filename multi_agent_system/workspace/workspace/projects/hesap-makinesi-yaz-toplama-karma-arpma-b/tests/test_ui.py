import pytest
from ui import main

def test_ui_structure():
    """
    UI fonksiyonunun varligini ve basit yapisini kontrol eder.
    """
    assert callable(main)