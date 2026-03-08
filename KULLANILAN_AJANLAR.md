# Multi-Agent Orchestration System (MAOS) - Ajanlar

## 📋 Sistem Ajanları

### 1. 🧠 Planner Agent (Planlayıcı Ajan)
- **ID**: `planner`
- **Rol**: Strateji ve Ayrıştırma
- **Görev**: Karmaşık kullanıcı hedeflerini uzman ajanlara atanmak üzere küçük, uygulanabilir alt görevlere böler
- **Yetenekler**: 
  - Task decomposition (görev ayrıştırma)
  - Dependency mapping (bağımlılık haritası)
  - Strategic planning (stratejik planlama)
- **Model**: Qwen 3 235B (qwen/qwen3-235b-a22b-2507)

---

### 2. 🔍 Researcher Agent (Araştırmacı Ajan)
- **ID**: `researcher`
- **Rol**: Bilgi Toplama ve Sentezleme
- **Görev**: İnternette arama yapar ve karmaşık konuları özlü, alıntılı raporlar halinde sentezler
- **Yetenekler**:
  - Web search (web araması)
  - Information synthesis (bilgi sentezi)
  - Documentation analysis (dokümantasyon analizi)
- **Model**: GPT-OSS 120B (openai/gpt-oss-120b)
- **Özellik**: Critic tarafından incelenmez (sadece araştırma metni üretir)

---

### 3. 💻 Coder Agent (Yazılımcı Ajan)
- **ID**: `coder`
- **Rol**: Kod Üretimi, İnceleme ve Hata Ayıklama
- **Görev**: Her fonksiyon için testlerle birlikte temiz, verimli ve iyi belgelenmiş kod yazar
- **Yetenekler**:
  - Code generation (kod üretimi)
  - Debugging (hata ayıklama)
  - Refactoring (kod iyileştirme)
  - Testing (test yazma)
- **Model**: Qwen 2.5 Coder 32B (qwen/qwen-2.5-coder-32b-instruct)
- **Özel Özellikler**:
  - ✅ Auto-fix: Syntax hatalarını otomatik düzeltir
  - ✅ Truncation detection: Kesilen kodu tespit eder
  - ✅ [FILE:] format enforcement: Zorunlu dosya formatı
  - ✅ Unterminated string fixer: AST tabanlı string düzeltme
  - ✅ Max 2 retry: Syntax hatası için 2 deneme hakkı
  - ✅ Banned filenames: output.py, script.py gibi isimler yasak

---

### 4. 🔍 Critic Agent (Eleştirmen Ajan)
- **ID**: `critic`
- **Rol**: Kalite Güvence ve Geri Bildirim
- **Görev**: Ajan çıktılarını inceler ve puanlanmış, eyleme dönüştürülebilir geri bildirimler sağlar
- **Yetenekler**:
  - Review (inceleme)
  - Feedback (geri bildirim)
  - Quality assurance (kalite güvence)
  - Scoring (puanlama)
- **Model**: GPT-OSS 120B (openai/gpt-oss-120b)
- **Threshold**: 5.0/10 (bu puanın altında retry)
- **Özellik**: Sadece Coder çıktılarını inceler, Researcher'ı atlar

---

### 5. 🧪 Tester Agent (Test Ajanı)
- **ID**: `tester`
- **Rol**: Otomatik Test Çalıştırma
- **Görev**: Coder'in yazdığı pytest testlerini çalıştırır, başarısız olanları raporlar
- **Yetenekler**:
  - Test execution (test çalıştırma)
  - Pytest integration
  - Test reporting (test raporlama)
- **Özellik**: LLM kullanmaz, sadece pytest çalıştırır

---

### 6. 📝 Linter Agent (Linter Ajanı)
- **ID**: `linter`
- **Rol**: Kod Kalitesi Analizi
- **Görev**: Kod kalitesini flake8 ve pylint ile analiz eder
- **Yetenekler**:
  - Linting (kod analizi)
  - Python quality (Python kalite kontrolü)
  - Flake8 integration
  - Pylint integration
- **Özellik**: LLM kullanmaz, statik analiz araçları kullanır

---

### 7. ⚙️ Executor Agent (Yürütücü Ajan)
- **ID**: `executor`
- **Rol**: Sistem Operasyonları ve Dosya Yönetimi
- **Görev**: Çalışma alanı sanal ortamında komutları güvenli bir şekilde yürütür ve dosyaları yönetir
- **Yetenekler**:
  - Shell execution (komut çalıştırma)
  - File management (dosya yönetimi)
  - Environment setup (ortam kurulumu)
  - Python execution (Python kodu çalıştırma)
- **Model**: GPT-OSS 120B (openai/gpt-oss-120b)

---

### 8. 👤 Profiler Agent (Profil Analisti)
- **ID**: `profiler`
- **Rol**: Kullanıcı Profili Çıkarma
- **Görev**: Tüm oturum ve proje verilerini analiz ederek kullanıcı profilini txt olarak kaydeder
- **Yetenekler**:
  - User profiling (kullanıcı profilleme)
  - Data analysis (veri analizi)
  - Pattern recognition (örüntü tanıma)
- **Model**: GPT-OSS 120B (openai/gpt-oss-120b)

---

## 🔄 Ajan İş Akışı

```
1. Planner → Görevi alt görevlere böler
2. Researcher → Gerekli bilgileri toplar (Critic atlar)
3. Coder → Kod yazar (auto-fix, truncation check)
4. Tester → Testleri çalıştırır
5. Linter → Kod kalitesini kontrol eder
6. Critic → Coder çıktısını puanlar (threshold: 5.0)
7. Executor → Kodu çalıştırır ve test eder
8. Profiler → Kullanıcı profilini günceller
```

---

## 🎯 Önemli Özellikler

### Cluster Mode
- **Durum**: Aktif (CLUSTER_MODE=true)
- **Özellik**: 2 model paralel çalışır (Qwen Coder + GPT-OSS)
- **Avantaj**: Daha hızlı kod üretimi

### Auto-Fix System (Coder)
- Regex tabanlı yaygın hata düzeltme
- AST tabanlı unterminated string düzeltme
- Truncation detection ve retry
- Max 2 syntax retry denemesi
- Başarısız dosyalar kaydedilmez

### Critic Optimization
- Threshold: 6.0 → 5.0 (daha az retry)
- Puanlama stabilitesi: 0.5 adımlarla
- Sadece Coder çıktılarını inceler
- Researcher muaf

### Memory System
- Geçmiş projeleri hatırlar
- Context'e otomatik ekler
- Pattern recognition

---

## 📊 Model Dağılımı

| Ajan | Model | Token Limit |
|------|-------|-------------|
| Planner | Qwen 3 235B | 8000 |
| Researcher | GPT-OSS 120B | 4000 |
| Coder | Qwen 2.5 Coder 32B | 8000 |
| Critic | GPT-OSS 120B | 4000 |
| Executor | GPT-OSS 120B | 2000 |
| Profiler | GPT-OSS 120B | 4000 |
| Tester | - (pytest) | - |
| Linter | - (flake8/pylint) | - |

---

## 💰 Maliyet Optimizasyonu

- Context pruning: Gereksiz token'ları kaldırır
- Selective agent activation: Sadece gerekli ajanlar çalışır
- Researcher Critic bypass: %15-20 maliyet tasarrufu
- Auto-fix: LLM retry sayısını azaltır
- Truncation detection: Gereksiz token harcamasını önler

---

## 🔧 Yapılandırma

Tüm ajanlar `multi_agent_system/agents/` klasöründe:
- `planner_agent.py`
- `researcher_agent.py`
- `coder_agent.py`
- `critic_agent.py`
- `tester_agent.py`
- `linter_agent.py`
- `executor_agent.py`
- `profiler_agent.py`

Orchestrator: `multi_agent_system/core/orchestrator.py`
