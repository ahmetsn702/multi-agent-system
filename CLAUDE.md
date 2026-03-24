# CLAUDE.md - Multi-Agent Orchestration System (MAOS)

## Proje Ozeti

MAOS, kullanici hedeflerini tamamen calisir yazilim projelerine donusturen bir multi-agent orkestrasyon sistemidir. 17 uzman ajan, ReAct (Reason-Act-Observe) dongusu icerisinde koordineli calisarak gorev planlama, arastirma, kod yazma, kalite degerlendirme ve calistirma adimlarini otonom olarak gerceklestirir.

**Temel Yetenekler:**
- Fazli yurume (phased execution) ile kompleks proje yonetimi
- Maliyet optimizasyonlu coklu LLM provider destegi (Vertex AI + Blackbox + Groq)
- Vektor bellek (ChromaDB) ile ogrenme
- 4 arayuz: CLI, Web Dashboard, Telegram Bot, REST API
- Sandbox izolasyonu ile guvenli dosya islemleri
- Google Cloud Vertex AI entegrasyonu (Gemini 2.5 Flash)

## Onemli: Aktif Kod Dizini

**Aktif codebase `multi_agent_system/` klasorudur.** Kok dizindeki `agents/`, `core/`, `config/`, `tools/`, `ui/`, `api/` klasorleri eski versiyondur (OpenRouter + Groq, 5 ajan). Yeni gelistirmeler `multi_agent_system/` altinda yapilmalidir.

| | Kok dizin (eski) | `multi_agent_system/` (aktif) |
|---|---|---|
| Ajan sayisi | 6 | 17 |
| Provider | OpenRouter + Groq | Vertex AI + Blackbox |
| Ana model | gpt-4o-mini + llama-70b | gemini-2.5-flash |
| Vertex AI | Yok | Tam entegrasyon |
| Telegram bot | Yok | Var |
| Cluster mode | Yok | Var |

## Dosya Yapisi

```
Multi-Agent/
├── multi_agent_system/        # <<< AKTIF KOD BURASI >>>
│   ├── agents/                # 17 ajan implementasyonu
│   │   ├── planner_agent.py   # Gorev dekompoze (flat/phased)
│   │   ├── researcher_agent.py# Web arama + bilgi sentezi
│   │   ├── architect_agent.py # Mimari tasarim
│   │   ├── coder_agent.py     # Kod uretimi + auto-fix
│   │   ├── critic_agent.py    # Kalite puanlama (1-10)
│   │   ├── executor_agent.py  # Calistirma + hata cozme
│   │   ├── security_agent.py  # Guvenlik analizi
│   │   ├── optimizer_agent.py # Performans optimizasyonu
│   │   ├── linter_agent.py    # Kod linting
│   │   ├── tester_agent.py    # Test yazma/calistirma
│   │   ├── builder_agent.py   # Build/paketleme
│   │   ├── docs_agent.py      # Dokumantasyon uretimi
│   │   ├── profiler_agent.py  # Kullanici profil analizi
│   │   ├── analyzer_agent.py  # Kod analizi
│   │   └── ui_tester_agent.py # UI test
│   │
│   ├── core/                  # Cekirdek altyapi
│   │   ├── orchestrator.py    # Ana ReAct dongusu + durum yonetimi
│   │   ├── base_agent.py      # Abstract BaseAgent + Task/Response tipleri
│   │   ├── llm_client.py      # Vertex AI + Blackbox LLM istemcisi
│   │   ├── memory.py          # 2 katmanli bellek (short-term + long-term)
│   │   ├── memory_agent.py    # ChromaDB vektor bellek ajani
│   │   ├── message_bus.py     # Async pub/sub mesaj yolu
│   │   ├── vector_memory.py   # Vektor bellek implementasyonu
│   │   ├── cluster_manager.py # Cluster mode yonetimi
│   │   └── cluster_runner.py  # Paralel model calistirma
│   │
│   ├── api/                   # FastAPI web sunucu + dashboard
│   │   ├── main_api.py        # Endpointler, auth, SSE streaming
│   │   ├── dashboard_ws.py    # WebSocket dashboard
│   │   └── static/            # HTML/CSS/JS varliklari
│   │
│   ├── tools/                 # Ajan araci implementasyonlari
│   │   ├── code_runner.py     # Python kod calistirma
│   │   ├── file_manager.py    # Sandboxlu dosya islemleri
│   │   ├── file_editor.py     # Dosya duzenleme
│   │   ├── shell_executor.py  # Kabuk komutu calistirma
│   │   ├── web_search.py      # DuckDuckGo entegrasyonu
│   │   ├── project_indexer.py # Proje dosya indeksleme
│   │   ├── tool_registry.py   # Arac kayit sistemi
│   │   ├── docker_runner.py   # Docker container calistirma
│   │   ├── git_manager.py     # Git islemleri
│   │   ├── code_analyzer.py   # Statik kod analizi
│   │   ├── interactive_shell.py # Interaktif kabuk
│   │   ├── project_templates.py # Proje sablonlari
│   │   ├── requirements_generator.py # requirements.txt uretimi
│   │   └── simple_search.py   # Basit arama
│   │
│   ├── ui/                    # Kullanici arayuzleri
│   │   ├── cli.py             # Interaktif terminal CLI
│   │   └── dashboard.py       # Terminal dashboard
│   │
│   ├── telegram_bot/          # Telegram bot entegrasyonu
│   ├── config/
│   │   └── settings.py        # Model routing, fiyatlama, token butceleri
│   ├── tests/                 # Test dosyalari
│   ├── docs/                  # Dokumantasyon
│   ├── utils/                 # Yardimci moduller
│   ├── main.py                # CLI giris noktasi
│   ├── conftest.py            # Pytest fixtures
│   ├── requirements.txt       # Python bagimliliklar
│   ├── .env.example           # Ortam degiskeni sablonu
│   └── pytest.ini             # Pytest yapilandirmasi
│
├── agents/                    # (ESKI) Kok dizin ajan implementasyonlari
├── core/                      # (ESKI) Kok dizin cekirdek altyapi
├── config/                    # (ESKI) Kok dizin yapilandirma
├── tools/                     # (ESKI) Kok dizin araclar
├── ui/                        # (ESKI) Kok dizin arayuzler
├── api/                       # (ESKI) Kok dizin API
├── tests/                     # Kok dizin testleri (her iki versiyon icin)
├── raporlar/                  # Raporlar ve dokumantasyon
├── scriptler/                 # Yardimci scriptler
├── promptlar/                 # Prompt PDF'leri (gitignore'da)
├── workspace/                 # Uretilen projeler + runtime verisi
│
├── .env                       # API anahtarlari (gitignore'da)
├── .env.example               # Ortam degiskeni sablonu
├── main.py                    # Kok dizin CLI giris noktasi (eski)
├── requirements.txt           # Python bagimliliklar
└── pytest.ini                 # Pytest yapilandirmasi
```

## Model Routing Tablosu (Aktif — `multi_agent_system/config/settings.py`)

### Vertex AI Ajanlari (Ana pipeline — Gemini 2.5 Flash)

| Ajan | Model | Provider | Maliyet | Max Output | Timeout |
|------|-------|----------|---------|------------|---------|
| planner | gemini-2.5-flash | Vertex AI | Ucretsiz* | 8192 tok | 120s |
| researcher | gemini-2.5-flash | Vertex AI | Ucretsiz* | 4096 tok | 120s |
| architect | gemini-2.5-flash | Vertex AI | Ucretsiz* | 4096 tok | 120s |
| coder | gemini-2.5-flash | Vertex AI | Ucretsiz* | 8192 tok | 120s |
| coder_fast | gemini-2.5-flash | Vertex AI | Ucretsiz* | 8192 tok | 120s |
| critic | gemini-2.5-flash | Vertex AI | Ucretsiz* | 4096 tok | 120s |
| executor | gemini-2.5-flash | Vertex AI | Ucretsiz* | 4096 tok | 120s |
| optimizer | gemini-2.5-flash | Vertex AI | Ucretsiz* | 4096 tok | 120s |
| orchestrator | gemini-2.5-flash | Vertex AI | Ucretsiz* | 4096 tok | 120s |

### Blackbox Ajanlari (Yardimci pipeline)

| Ajan | Model | Provider | Maliyet | Max Output |
|------|-------|----------|---------|------------|
| security | claude-haiku-4.5 | Blackbox | $0.80 / $4.00 | 16000 tok |
| docs | claude-haiku-4.5 | Blackbox | $0.80 / $4.00 | 16000 tok |
| tester | claude-haiku-4.5 | Blackbox | $0.80 / $4.00 | 16000 tok |
| ui_tester | claude-haiku-4.5 | Blackbox | $0.80 / $4.00 | 16000 tok |
| profiler | claude-haiku-4.5 | Blackbox | $0.80 / $4.00 | 16000 tok |
| analyzer | claude-haiku-4.5 | Blackbox | $0.80 / $4.00 | 16000 tok |
| linter | qwen3-coder:free | Blackbox | Ucretsiz | 8000 tok |
| builder | devstral-small | Blackbox | $0.10 / $0.30 | 8000 tok |

*\*Vertex AI: GCP free tier / kredi kullanimi*

### Provider Yapilandirmasi

| Provider | Endpoint | Env Key | Auth |
|----------|----------|---------|------|
| Vertex AI | google-genai SDK | `VERTEX_PROJECT` + `VERTEX_LOCATION` | GCP ADC (`gcloud auth application-default login`) |
| Blackbox | `https://api.blackbox.ai/chat/completions` | `BLACKBOX_API_KEY` | Bearer token |
| Groq | `https://api.groq.com/openai/v1/chat/completions` | `GROQ_API_KEY` | Bearer token (tanimli, routing'de kullanilmiyor) |
| Cerebras | `https://api.cerebras.ai/v1/chat/completions` | `CEREBRAS_API_KEY` | Bearer token (tanimli, routing'de kullanilmiyor) |

### LLM Client Mimari (`multi_agent_system/core/llm_client.py`)

```
LLMClient(agent_id)
    |
    __new__() → provider == "vertex"?
    |                |
    | YES            | NO
    v                v
VertexAIClient   LLMClient (httpx)
(google-genai)   (Blackbox/Groq/Cerebras)
```

Factory pattern: `LLMClient("planner")` cagirildiginda routing `vertex` ise `VertexAIClient` doner. Cagiran kod farki bilmez.

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
Architect --> [Mimari tasarim]  (yeni)
    |
    v
Coder --> [Kod + testler]
    |
    v
Critic --> [Puan: 1-10]
    |--- >= 7.0 --> Devam
    |--- 4.0-6.9 --> Revizyon (Coder'a geri)
    |--- < 4.0 --> Yeniden planlama (Planner'a geri)
    |
    v
Security --> [Guvenlik analizi]  (yeni)
    |
    v
Executor --> [Calistir + sonuc]
    |
    v
Tester --> [Test calistir]  (yeni)
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
- Yeni ajan eklerken `multi_agent_system/core/base_agent.py`'den turet
- Model routing'i `multi_agent_system/config/settings.py` icindeki `MODEL_ROUTING`'e ekle
- Vertex AI ajanlari icin `VertexAIClient` otomatik kullanilir (factory pattern)

## Bilinen Buglar ve TODO'lar

### Bilinen Buglar
- `app.py` vs `main.py` import cakismasi: Coder bazen test dosyalarinda yanlis import uretir
- Critic timeout: Bazi durumlarda critic agent timeout aliyor
- `main.py` korunma sorunu: Orchestrator bazi durumlarda mevcut main.py'yi ust yaziyor
- `stream_to_console()` kok dizin llm_client.py'de hardcoded `OPENROUTER_BASE_URL` kullaniyor (legacy bug)

### TODO'lar
- [ ] Kok dizindeki eski kodun (agents/, core/, config/ vb.) tamamen kaldirilmasi veya arsivlenmesi
- [ ] Pre-commit hook ekle (.env commit onleme)
- [ ] CI/CD pipeline kurulumu
- [ ] Telegram bot deploy rehberi
- [ ] Cluster mode dokumantasyonu

## Testlerin Calistirilmasi

```bash
# Aktif kod testleri (multi_agent_system icinden)
cd multi_agent_system
pytest

# Kok dizin testleri
pytest tests/

# Verbose cikti
pytest -v
```

## .env Gereksinimleri

### `multi_agent_system/.env` (aktif kod)

```env
# Vertex AI (zorunlu — ana pipeline)
# Auth: gcloud auth application-default login
VERTEX_PROJECT=your-gcp-project-id
VERTEX_LOCATION=us-central1

# Blackbox (zorunlu — yardimci ajanlar)
BLACKBOX_API_KEY=your_blackbox_key

# Groq (opsiyonel — tanimli ama aktif routing'de yok)
GROQ_API_KEY=your_groq_key

# Telegram Bot (opsiyonel)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_USER_ID=your_user_id

# Cluster Mode (opsiyonel)
CLUSTER_MODE=false
```

### Kok dizin `.env` (eski versiyon)

```env
OPENROUTER_API_KEY=your_openrouter_key    # sk-or-v1-... formati
GROQ_API_KEY=your_groq_key                # gsk_... formati
```

## Hizli Baslangic

```bash
# 1. Bagimliklar
pip install -r multi_agent_system/requirements.txt

# 2. GCP auth (Vertex AI icin)
gcloud auth application-default login

# 3. Ortam degiskenleri
cp multi_agent_system/.env.example multi_agent_system/.env
# .env dosyasini duzenle, VERTEX_PROJECT ve BLACKBOX_API_KEY ekle

# 4. CLI ile calistir
cd multi_agent_system
python main.py "Flask ile basit TODO uygulamasi yaz"

# 5. Web dashboard (opsiyonel)
python -m api.main_api
```
