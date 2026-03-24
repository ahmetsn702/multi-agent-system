import sys
from typing import Union

MAX_RETRY = 3

class CalculatorError(Exception):
    """Hesap makinesi hatası için özel istisna sınıfı.

    Attributes:
        message -- Hata mesajı
    """
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)

def add(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
    """İki sayıyı toplar.

    Args:
        a: İlk sayı
        b: İkinci sayı

    Returns:
        İki sayının toplamı
    """
    try:
        return a + b
    except TypeError as e:
        raise CalculatorError(f"Geçersiz giriş: {e}") from e

def subtract(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
    """İki sayıdan çıkarma yapar.

    Args:
        a: İlk sayı
        b: İkinci sayı

    Returns:
        İki sayının farkı
    """
    try:
        return a - b
    except TypeError as e:
        raise CalculatorError(f"Geçersiz giriş: {e}") from e

def multiply(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
    """İki sayıyı çarpar.

    Args:
        a: İlk sayı
        b: İkinci sayı

    Returns:
        İki sayının çarpımı
    """
    try:
        return a * b
    except TypeError as e:
        raise CalculatorError(f"Geçersiz giriş: {e}") from e

def divide(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
    """İki sayıyı böler.

    Args:
        a: İlk sayı
        b: İkinci sayı

    Returns:
        İki sayının bölümü

    Raises:
        CalculatorError: Sıfıra bölme hatası
    """
    try:
        if b == 0:
            raise CalculatorError("Sıfıra bölme hatası")
        return a / b
    except TypeError as e:
        raise CalculatorError(f"Geçersiz giriş: {e}") from e

def main():
    """Komut satırı argümanlarını kullanarak hesap makinesi işlemlerini gerçekleştirir.

    Komut satırı argümanları:
        1. İşlem (add, subtract, multiply, divide)
        2. İlk sayı
        3. İkinci sayı
    """
    if len(sys.argv) != 4:
        print("Kullanım: python calculator.py <işlem> <sayı1> <sayı2>")
        sys.exit(1)

    operation = sys.argv[1]
    try:
        a = float(sys.argv[2])
        b = float(sys.argv[3])
    except ValueError as e:
        print(f"Geçersiz sayı: {e}")
        sys.exit(1)

    try:
        if operation == "add":
            result = add(a, b)
        elif operation == "subtract":
            result = subtract(a, b)
        elif operation == "multiply":
            result = multiply(a, b)
        elif operation == "divide":
            result = divide(a, b)
        else:
            print("Geçersiz işlem. Kullanılabilir işlemler: add, subtract, multiply, divide")
            sys.exit(1)
        print(f"Sonuç: {result}")
    except CalculatorError as e:
        print(f"Hata: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()