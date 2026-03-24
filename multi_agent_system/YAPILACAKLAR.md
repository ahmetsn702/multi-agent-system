# Multi-Agent Sistem — Kalan İşler

## ✅ Tamamlanan (Bu Sohbette)
- Kimi K2 Thinking timeout (600s) + `<think>` tag temizleme
- Orchestrator faz öncesi otomatik `pip install` (`_pre_install_project_deps`)
- **Devin tarzı interaktif Executor** (`agents/executor_agent.py` — tamamen yeniden yazıldı)
- **Stateful shell session** (`tools/interactive_shell.py` — yeni dosya)
- SYSTEM_PROMPT `{{}}` escape fix
- Mini test başarılı: `[Executor] 🔧 Adım 1/15: list_dir → src` ✅

## 🔴 Yapılması Gereken

### 1. Tam Proje Testi (ÖNCELİK 1)
Yeni Devin tarzı Executor ile tam proje testi henüz yapılmadı:
```bash
python main.py "Python ile asenkron web crawler yaz. SQLite'a kaydetsin ve seo_raporu.md üretsin."
```
- Executor'ın `[Executor] 🔧 Adım X/15` loglarının terminalde görünmesi gerekiyor
- Model hata alınca kendisi `pip install` yapıp tekrar denemeli
- Hedef: 8/8 görev tamamlanması

### 2. Orchestrator `_pre_install_project_deps` İyileştirmesi
- `database`, `crawler`, `models` gibi proje-içi modüller pip install edilmeye çalışılıyor (hata veriyor ama zararsız)
- Çözüm: `_pre_install_project_deps`'te proje src/ klasöründeki dosya isimlerini STDLIB'e ekle

### 3. Executor İyileştirmeleri (Opsiyonel)
- `MAX_STEPS = 15` yeterli mi test et
- Executor modeli (şu an `openai/gpt-oss-120b`) yeterli mi — daha güçlü model gerekebilir
- `write_file` tool ile model kendi hata düzeltmesi yapabiliyor mu test et

### 4. Faz 2-3 Boş Iterasyon Sorunu
- Önceki testlerde Faz 2 ve 3'te 10 iterasyon boşa gidiyordu
- Muhtemelen yeni Executor ile düzelecek ama doğrulanması gerekiyor

## 📁 Değiştirilen Dosyalar
| Dosya | Ne Yapıldı |
|-------|-----------|
| `agents/executor_agent.py` | Tamamen yeniden yazıldı (Devin ReAct) |
| `tools/interactive_shell.py` | Yeni dosya (stateful shell) |
| `core/orchestrator.py` | `import sys` + `_pre_install_project_deps` eklendi |
| `core/llm_client.py` | Model bazlı dinamik timeout |
| `config/settings.py` | `MODEL_TIMEOUTS` eklendi |
| `agents/planner_agent.py` | Kimi K2 `<think>` temizleme |
