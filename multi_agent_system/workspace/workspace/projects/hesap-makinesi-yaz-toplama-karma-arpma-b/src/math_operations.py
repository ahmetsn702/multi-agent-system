import sys
from typing import Union

MAX_RETRY = 3

class MathOperations:
    """Temel matematik işlemleri için sınıf.

    Attributes:
        MAX_RETRY (int): Maksimum deneme sayısı.
    """

    @staticmethod
    def add(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
        """İki sayıyı toplar.

        Args:
            a (Union[int, float]): İlk sayı.
            b (Union[int, float]): İkinci sayı.

        Returns:
            Union[int, float]: Toplam.
        """
        return a + b

    @staticmethod
    def subtract(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
        """İki sayıyı çıkarır.

        Args:
            a (Union[int, float]): İlk sayı.
            b (Union[int, float]): İkinci sayı.

        Returns:
            Union[int, float]: Fark.
        """
        return a - b

    @staticmethod
    def multiply(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
        """İki sayıyı çarpar.

        Args:
            a (Union[int, float]): İlk sayı.
            b (Union[int, float]): İkinci sayı.

        Returns:
            Union[int, float]: Çarpım.
        """
        return a * b

    @staticmethod
    def divide(a: Union[int, float], b: Union[int, float]) -> Union[int, float, str]:
        """İki sayıyı böler.

        Args:
            a (Union[int, float]): İlk sayı.
            b (Union[int, float]): İkinci sayı.

        Returns:
            Union[int, float, str]: Bölüm veya hata mesajı.
        """
        try:
            if b == 0:
                raise ZeroDivisionError("Sıfıra bölme hatası!")
            return a / b
        except ZeroDivisionError as e:
            return str(e)

    @staticmethod
    def calculate(operation: str, a: Union[int, float], b: Union[int, float]) -> Union[int, float, str]:
        """Belirtilen işlemi gerçekleştirir.

        Args:
            operation (str): İşlem türü (add, subtract, multiply, divide).
            a (Union[int, float]): İlk sayı.
            b (Union[int, float]): İkinci sayı.

        Returns:
            Union[int, float, str]: İşlem sonucu veya hata mesajı.
        """
        try:
            if operation == "add":
                return MathOperations.add(a, b)
            elif operation == "subtract":
                return MathOperations.subtract(a, b)
            elif operation == "multiply":
                return MathOperations.multiply(a, b)
            elif operation == "divide":
                return MathOperations.divide(a, b)
            else:
                raise ValueError("Geçersiz işlem!")
        except ValueError as e:
            return str(e)

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Kullanım: python math_operations.py <işlem> <sayı1> <sayı2>")
        sys.exit(1)

    operation = sys.argv[1]
    try:
        a = float(sys.argv[2])
        b = float(sys.argv[3])
    except ValueError:
        print("Geçersiz sayı girişi!")
        sys.exit(1)

    result = MathOperations.calculate(operation, a, b)
    print(f"Sonuç: {result}")