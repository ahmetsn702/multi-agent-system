from decimal import Decimal


def topla(a: Decimal, b: Decimal) -> Decimal:
    """İki sayıyı toplar.

    Args:
        a: İlk sayı (Decimal).
        b: İkinci sayı (Decimal).

    Returns:
        İki sayının toplamı (Decimal).
    """
    return a + b


def cikar(a: Decimal, b: Decimal) -> Decimal:
    """İlk sayıdan ikinciyi çıkarır.

    Args:
        a: Çıkarılacak sayı (Decimal).
        b: Çıkarılacak sayı (Decimal).

    Returns:
        Çıkarma sonucunu (Decimal).
    """
    return a - b


def carp(a: Decimal, b: Decimal) -> Decimal:
    """İki sayıyı çarpar.

    Args:
        a: İlk sayı (Decimal).
        b: İkinci sayı (Decimal).

    Returns:
        İki sayının çarpımı (Decimal).
    """
    return a * b


def bolme(a: Decimal, b: Decimal) -> Decimal:
    """İlk sayıyı ikincisine böler.

    Args:
        a: Bölünen sayı (Decimal).
        b: Bölen sayı (Decimal).

    Returns:
        Bölme sonucunu (Decimal).

    Raises:
        ValueError: Bölen sıfır ise hata verir.
    """
    try:
        return a / b
    except ZeroDivisionError:
        raise ValueError("Sıfıra bölme hatası! Bölen sıfır olamaz.")
