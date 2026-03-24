# CLAUDE.md - Multi-Agent Orchestration System (MAOS)

## Proje Ozeti

MAOS, kullanici hedeflerini tamamen calisir yazilim projelerine donusturen bir multi-agent orkestrasyon sistemidir. 9 uzman ajan, ReAct (Reason-Act-Observe) dongusu icerisinde koordineli calisarak gorev planlama, arastirma, kod yazma, kalite degerlendirme ve calistirma adimlarini otonom olarak gerceklestirir.

**Temel Yetenekler:**
- Fazli yurume (phased execution) ile kompleks proje yonetimi
- Maliyet optimizasyonlu coklu LLM provider destegi (OpenRouter + Groq)
- Vektor bellek (ChromaDB) ile ogrenme
- 4 arayuz: CLI, Web Dashboard, Telegram Bot, REST API
- Sandbox izolasyonu ile guvenli dosya islemleri

## Dosya Yapisi

```
Multi-Agent/
├── agents/                 # Ajan implementasyonlari
│   ├── planner_agent.py    # Gorev dekompoze (flat/phased)
│   ├── researcher_agent.py # Web arama + bilgi sentezi
│   ├── coder_agent.py      # Kod uretimi + auto-fix
│   ├── critic_agent.py     # Kalite puanlama (1-10)
│   ├── executor_agent.py   # Calistirma + hata cozme
│   └── profiler_agent.py   # Kullanici profil analizi
│
├── core/                   # Cekirdek altyapi
│   ├── orchestrator.py     # Ana ReAct dongusu + durum yonetimi
│   ├── base_agent.py       # Abstract BaseAgent + Task/Response tipleri
│   ├── llm_client.py       # OpenRouter/Groq LLM istemcisi (async httpx)
│   ├── memory.py           # 2 katmanli bellek (short-term + long-term)
│   └── message_bus.py      # Async pub/sub mesaj yolu (oncelik kuyrugu)
│
├── api/                    # FastAPI web sunucu + dashboard
│   ├── main_api.py         # Endpointler, auth, SSE streaming
│   └── static/             # HTML/CSS/JS varliklari
│
├── tools/                  # Ajan araci implementasyonlari
│   ├── code_runner.py      # Python kod calistirma
│   ├── file_manager.py     # Sandboxlu dosya islemleri
│   ├── file_editor.py      # Dosya duzenleme
│   ├── shell_executor.py   # Kabuk komutu calistirma (guvenlik kontrolleri)
│   ├── web_search.py       # DuckDuckGo entegrasyonu
│   ├── project_indexer.py  # Proje dosya indeksleme
│   └── tool_registry.py    # Arac kayit sistemi
│
├── ui/                     # Kullanici arayuzleri
│   ├── cli.py              # Interaktif terminal CLI
│   └── dashboard.py        # Terminal dashboard
│
├── config/
│   └── settings.py         # Model routing, fiyatlama, token butceleri
│
├── tests/                  # Test dosyalari (pytest)
├── workspace/              # Uretilen projeler + runtime verisi
├── raporlar/               # Raporlar ve dokumantasyon
├── scriptler/              # Yardimci scriptler
├── multi_agent_system/     # Eski/paralel implementasyon (legacy)
├── promptlar/              # Prompt PDF'leri (gitignore'da)
│
├── .env                    # API anahtarlari (gitignore'da)
├── .env.example            # Ortam degiskeni sablonu
├── main.py                 # CLI giris noktasi
├── requirements.txt        # Python bagimliliklar
└── pytest.ini              # Pytest yapilandirmasi
```

## Model Routing Tablosu

| Ajan | Model | Provider | Maliyet (1M token) | Timeout |
|------|-------|----------|---------------------|---------|
| Planner | xiaomi/mimo-v2-pro | OpenRouter | $0.15 / $0.60 | 120s |
| Researcher | llama-3.3-70b-versatile | Groq | Ucretsiz | 60s |
| Coder | openai/gpt-4o-mini | OpenRouter | $0.15 / $0.60 | 60s |
| Critic | llama-3.3-70b-versatile | Groq | Ucretsiz | 60s |
| Executor | Yok (yerel calistirma) | - | - | 60s |
| Profiler | Orchestrator modelini kullanir | - | - | - |

**Provider Yapilandirmasi:**
- OpenRouter: `https://openrouter.ai/api/v1/chat/completions` (env: `OPENROUTER_API_KEY`)
- Groq: `https://api.groq.com/openai/v1/chat/completions` (env: `GROQ_API_KEY`)

## Mimari Akis

```
Kullanici Hedefi
    |
    v
Orchestrator.run(goal)
    |
    v
Planner --> [Gorev listesi / Fazlar]
    |
    v
[Her gorev icin]
    |
    v
Researcher --> [Arastirma sonuclari]
    |
    v
Coder --> [Kod + testler]
    |
    v
Critic --> [Puan: 1-10]
    |--- >= 7.0 --> Devam (Executor'a)
    |--- 4.0-6.9 --> Revizyon (Coder'a geri)
    |--- < 4.0 --> Yeniden planlama (Planner'a geri)
    |
    v
Executor --> [Calistir + sonuc]
    |
    v
Memory'e kaydet --> Proje dizinini dondur
```

**ReAct Parametreleri:**
- MAX_ITERATIONS: 10
- CONFIDENCE_THRESHOLD: 0.6
- Max retry per task: 3

## Gelistirme Kurallari

### Code Style
- Python 3.10+, PEP 8 uyumlu
- Type hint'ler tum fonksiyonlarda
- Docstring'ler tum public metotlarda
- Async/await pattern'i (asyncio tabanli)
- Path yonetimi: `Path(__file__).parent` kullan, hardcoded path yazma

### Commit Convention
- `feat:` yeni ozellik
- `fix:` hata duzeltme
- `chore:` temizlik, bakim
- `docs:` dokumantasyon
- `security:` guvenlik duzeltmeleri
- Turkce commit mesajlari kabul edilir

### Onemli Kurallar
- `.env` dosyalari ASLA commit edilmez
- Workspace altindaki uretilen projeler gitignore'dadir
- `promptlar/` klasoru hassas bilgi icerebilir, gitignore'dadir
- Kisisel yollar (C:\Users\...) kodda veya raporlarda kullanilmaz
- Yeni ajan eklerken `core/base_agent.py`'den turet, `MODEL_ROUTING`'e ekle

## Bilinen Buglar ve TODO'lar

### Bilinen Buglar
- `app.py` vs `main.py` import cakismasi: Coder bazen test dosyalarinda yanlis import uretir (bkz: `tests/BUG_COUNTEREXAMPLE_app_py_main_py.md`)
- Critic timeout: Bazi durumlarda critic agent timeout aliyor (bkz: `tests/test_critic_timeout_cost_bugs.py`)
- `main.py` korunma sorunu: Orchestrator bazi durumlarda mevcut main.py'yi ust yaziyor (bkz: `tests/test_main_py_preservation.py`)

### TODO'lar
- [ ] Linter agent implementasyonu (README'de bahsediliyor, kod yok)
- [ ] Tester agent implementasyonu (README'de bahsediliyor, kod yok)
- [ ] Builder agent implementasyonu (README'de bahsediliyor, kod yok)
- [ ] Memory agent (ChromaDB) tam entegrasyonu
- [ ] Telegram bot deploy rehberi
- [ ] `multi_agent_system/` legacy kodunun temizlenmesi veya birlestirilmesi
- [ ] Pre-commit hook ekle (.env commit onleme)
- [ ] CI/CD pipeline kurulumu

## Testlerin Calistirilmasi

```bash
# Tum testler
pytest

# Belirli test dosyasi
pytest tests/test_agents.py

# Verbose cikti
pytest -v

# Belirli test fonksiyonu
pytest tests/test_agents.py::test_planner_agent -v
```

**Pytest Yapilandirmasi** (`pytest.ini`):
- `asyncio_mode = auto`
- Test dosyalari: `tests/` dizini

## .env Gereksinimleri

`.env.example` dosyasini `.env` olarak kopyalayip doldurun:

```env
# Zorunlu - LLM Providerlari
OPENROUTER_API_KEY=your_openrouter_key    # sk-or-v1-... formati
GROQ_API_KEY=your_groq_key                # gsk_... formati

# Opsiyonel - Web API
WEB_PASSWORD=your_password                # Dashboard giris sifresi
ALLOWED_ORIGINS=http://localhost:3000      # CORS izinleri

# Opsiyonel - Telegram Bot
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_USER_ID=your_user_id
```

## Hizli Baslangic

```bash
# 1. Bagimliklar
pip install -r requirements.txt

# 2. Ortam degiskenleri
cp .env.example .env
# .env dosyasini duzenle, API anahtarlarini ekle

# 3. CLI ile calistir
python main.py "Flask ile basit TODO uygulamasi yaz"

# 4. Web dashboard (opsiyonel)
python -m api.main_api
```
