import sys
from typing import Union

def topla(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
    """
    İki sayıyı toplar.

    Args:
        a: Toplanacak ilk sayı.
        b: Toplanacak ikinci sayı.

    Returns:
        İki sayının toplamı.
    """
    return a + b

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Kullanım: python main.py <sayi1> <sayi2>")
        sys.exit(1)

    try:
        num1 = float(sys.argv[1])
        num2 = float(sys.argv[2])
        result = topla(num1, num2)
        print(f"Toplam: {result}")
    except ValueError:
        print("Hata: Lütfen geçerli sayısal değerler girin.")
        sys.exit(1)
    except Exception as e:
        print(f"Beklenmeyen bir hata oluştu: {e}")
        sys.exit(1)