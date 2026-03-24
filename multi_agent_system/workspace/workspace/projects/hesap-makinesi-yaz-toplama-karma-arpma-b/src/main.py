import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def add(a, b): return a + b
def subtract(a, b): return a - b
def multiply(a, b): return a * b
def divide(a, b): return a / b if b != 0 else "Hata: Sifira bolme hatasi."

def main() -> None:
    if len(sys.argv) < 4:
        print("Kullanim: python app.py <add|subtract|multiply|divide> <s1> <s2>")
        return

    operation = sys.argv[1]
    try:
        num1 = float(sys.argv[2])
        num2 = float(sys.argv[3])
    except ValueError:
        print("Hata: Sayilar gecerli birer sayi olmalidir.")
        return

    try:
        if operation == "add":
            print(f"Sonuc: {add(num1, num2)}")
        elif operation == "subtract":
            print(f"Sonuc: {subtract(num1, num2)}")
        elif operation == "multiply":
            print(f"Sonuc: {multiply(num1, num2)}")
        elif operation == "divide":
            print(f"Sonuc: {divide(num1, num2)}")
        else:
            print("Hata: Gecersiz islem.")
    except Exception as e:
        print(f"Islem hatasi: {e}")

if __name__ == "__main__":
    main()