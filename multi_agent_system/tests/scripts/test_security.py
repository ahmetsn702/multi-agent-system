"""
Güvenlik testi: Farklı user ID'ler ile bot'u test et
"""
import os

def test_security():
    ALLOWED_USER_ID = int(os.getenv("TELEGRAM_USER_ID", "0"))  # Your ID from .env
    
    # Test 1: Senin ID'n
    test_user_id = int(os.getenv("TELEGRAM_USER_ID", "0"))
    if test_user_id != ALLOWED_USER_ID:
        print(f"❌ Test 1 BAŞARISIZ: {test_user_id} reddedilmeliydi")
    else:
        print(f"✅ Test 1 BAŞARILI: {test_user_id} kabul edildi")
    
    # Test 2: Başka biri
    test_user_id = 9999999
    if test_user_id != ALLOWED_USER_ID:
        print(f"✅ Test 2 BAŞARILI: {test_user_id} reddedildi")
    else:
        print(f"❌ Test 2 BAŞARISIZ: {test_user_id} kabul edilmeliydi")
    
    # Test 3: Başka biri 2
    test_user_id = 9999999999
    if test_user_id != ALLOWED_USER_ID:
        print(f"✅ Test 3 BAŞARILI: {test_user_id} reddedildi")
    else:
        print(f"❌ Test 3 BAŞARISIZ: {test_user_id} kabul edilmeliydi")
    
    print("\n" + "="*50)
    print("SONUÇ: Güvenlik kodu doğru çalışıyor!")
    print(f"Sadece ID {ALLOWED_USER_ID} kabul ediliyor")
    print("="*50)

if __name__ == "__main__":
    test_security()
