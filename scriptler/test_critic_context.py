"""
Test Critic agent context filtering
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "multi_agent_system"))

from core.base_agent import Task
from core.orchestrator import Orchestrator


def test_critic_context():
    print("\n" + "="*70)
    print("CRITIC AGENT CONTEXT TEST")
    print("="*70)
    
    # Simulate a full context that Critic would receive
    full_context = {
        "content": "def hello():\n    print('Hello World')\n\nhello()",  # KOD - BU ÖNEMLİ!
        "content_type": "code",
        "original_task": "Basit hello world fonksiyonu yaz",
        "revision_count": 0,
        # Gereksiz context (diğer ajanlardan kalan)
        "research": "Web araması sonuçları " * 100,
        "planner_output": "Plan detayları " * 100,
        "existing_files": ["file1.py", "file2.py", "file3.py"],
        "phase_info": "Faz 2 bilgisi",
        "test_failures": "Test hataları",
        "lint_issues": "Lint sorunları",
        "unnecessary_data": "Gereksiz veri " * 200,
    }
    
    print(f"\n1. ORIJINAL CONTEXT:")
    print(f"   Toplam alan sayısı: {len(full_context)}")
    print(f"   Boyut: {len(str(full_context)):,} karakter")
    print(f"\n   İçerik:")
    for key in full_context.keys():
        value_preview = str(full_context[key])[:50]
        print(f"     - {key}: {value_preview}...")
    
    # Create a Critic task
    task = Task(
        task_id="critic_test",
        description="Kodu incele",
        assigned_to="critic",
        context=full_context.copy(),
    )
    
    # Apply context filtering
    orch = Orchestrator(agents={}, message_bus=None)
    filtered_task = orch._build_context_for_agent(task)
    
    print(f"\n2. FİLTRELENMİŞ CONTEXT (Critic için):")
    print(f"   Toplam alan sayısı: {len(filtered_task.context)}")
    print(f"   Boyut: {len(str(filtered_task.context)):,} karakter")
    print(f"\n   İçerik:")
    for key, value in filtered_task.context.items():
        value_preview = str(value)[:50]
        print(f"     - {key}: {value_preview}...")
    
    # Check if code is present
    print(f"\n3. KRİTİK KONTROL:")
    if "content" in filtered_task.context:
        code = filtered_task.context["content"]
        print(f"   ✅ 'content' alanı mevcut")
        print(f"   ✅ Kod uzunluğu: {len(code)} karakter")
        print(f"\n   Kod içeriği:")
        print("   " + "-"*66)
        for line in code.split('\n'):
            print(f"   {line}")
        print("   " + "-"*66)
    else:
        print(f"   ❌ 'content' alanı YOK! Critic kodu göremez!")
    
    if "content_type" in filtered_task.context:
        print(f"   ✅ 'content_type' mevcut: {filtered_task.context['content_type']}")
    else:
        print(f"   ❌ 'content_type' YOK!")
    
    if "original_task" in filtered_task.context:
        print(f"   ✅ 'original_task' mevcut: {filtered_task.context['original_task']}")
    else:
        print(f"   ❌ 'original_task' YOK!")
    
    # Calculate reduction
    original_size = len(str(full_context))
    filtered_size = len(str(filtered_task.context))
    reduction = ((original_size - filtered_size) / original_size) * 100
    
    print(f"\n4. PERFORMANS:")
    print(f"   Orijinal: {original_size:,} karakter (~{original_size//4:,} token)")
    print(f"   Filtrelenmiş: {filtered_size:,} karakter (~{filtered_size//4:,} token)")
    print(f"   Azalma: {reduction:.1f}%")
    
    # Verify Critic can work with this context
    print(f"\n5. SONUÇ:")
    required_fields = ["content", "content_type", "original_task", "revision_count"]
    missing_fields = [f for f in required_fields if f not in filtered_task.context]
    
    if not missing_fields:
        print(f"   ✅ Tüm gerekli alanlar mevcut")
        print(f"   ✅ Critic agent düzgün çalışabilir")
    else:
        print(f"   ❌ Eksik alanlar: {missing_fields}")
        print(f"   ❌ Critic agent ÇALIŞAMAZ!")
    
    print("\n" + "="*70)


if __name__ == "__main__":
    test_critic_context()
