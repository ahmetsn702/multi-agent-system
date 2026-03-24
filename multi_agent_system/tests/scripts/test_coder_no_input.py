"""
Test: Coder Agent'ın input() kullanmadığını doğrula
"""
import asyncio
import pytest
from agents.coder_agent import CoderAgent
from core.base_agent import Task

@pytest.mark.asyncio
async def test_coder_no_input():
    """Coder'ın iki sayı toplayan kod yazmasını test et - input() olmamalı"""
    coder = CoderAgent()
    
    task = Task(
        task_id="test_no_input",
        description="İki sayıyı toplayan basit bir Python scripti yaz. Sayılar komut satırı argümanı olarak alınmalı (sys.argv).",
        assigned_to="coder",
        context={
            "project_slug": "test-no-input",
            "research": "Basit toplama işlemi, sys.argv kullan"
        }
    )
    
    print("🧪 Test başlıyor: Coder Agent - No input() rule")
    print("=" * 60)
    
    # Think
    thought = await coder.think(task)
    print(f"✅ Think tamamlandı: {thought.reasoning[:100]}...")
    
    # Act
    result = await coder.act(thought, task)
    print(f"✅ Act tamamlandı: {result.success}")
    
    # Sonucu kontrol et
    if result.success and result.content:
        saved_files = result.content.get("saved_files", [])
        print(f"\n📁 Oluşturulan dosyalar: {len(saved_files)}")
        
        # Her dosyayı kontrol et
        has_input = False
        for file_path in saved_files:
            # saved_files liste içinde string path'ler
            if isinstance(file_path, dict):
                filepath = file_path.get("path", "")
            else:
                filepath = file_path
                
            print(f"\n📄 Dosya: {filepath}")
            
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                if 'input(' in content:
                    print(f"  ❌ HATA: input() bulundu!")
                    has_input = True
                    # input() içeren satırları göster
                    for i, line in enumerate(content.splitlines(), 1):
                        if 'input(' in line:
                            print(f"    Satır {i}: {line.strip()}")
                else:
                    print(f"  ✅ input() YOK")
                    
                # sys.argv kullanımını kontrol et
                if 'sys.argv' in content:
                    print(f"  ✅ sys.argv kullanılmış")
                    
            except Exception as e:
                print(f"  ⚠️  Dosya okunamadı: {e}")
        
        print("\n" + "=" * 60)
        if has_input:
            print("❌ TEST BAŞARISIZ: Kod hala input() içeriyor!")
        else:
            print("✅ TEST BAŞARILI: Kod input() içermiyor!")
        print("=" * 60)
    else:
        print("❌ Coder başarısız oldu")

if __name__ == "__main__":
    asyncio.run(test_coder_no_input())
