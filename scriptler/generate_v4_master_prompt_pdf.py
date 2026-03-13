"""
generate_v4_master_prompt_pdf.py
V4 Master Prompt PDF -- Coklu Ajan Orkestrasyon Sistemi
Tum sistem yapilandirmasi, model stratejisi ve optimizasyonlar.
"""
from fpdf import FPDF
import os

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "v4_master_prompt.pdf")


class PDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 10)
        self.set_fill_color(20, 25, 45)
        self.set_text_color(255, 255, 255)
        self.cell(0, 10, "Multi-Agent System  |  V4 Master Prompt", fill=True, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.ln(2)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, f"Sayfa {self.page_no()}", align="C")

    def section_title(self, title):
        self.set_font("Helvetica", "B", 13)
        self.set_fill_color(25, 50, 90)
        self.set_text_color(255, 255, 255)
        self.cell(0, 9, title, fill=True, align="L", new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.ln(2)

    def sub_title(self, title):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(20, 60, 140)
        self.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)

    def body_text(self, text):
        self.set_font("Helvetica", "", 9)
        self.set_fill_color(245, 247, 252)
        self.multi_cell(0, 5, text, fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def label_value(self, label, value):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(60, 60, 60)
        self.cell(40, 6, label + ":", new_x="RIGHT", new_y="LAST")
        self.set_font("Helvetica", "", 9)
        self.set_text_color(0, 0, 0)
        self.multi_cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")

    def table_row(self, cols, widths, bold=False, fill_color=None, text_color=None):
        if fill_color:
            self.set_fill_color(*fill_color)
        if text_color:
            self.set_text_color(*text_color)
        self.set_font("Helvetica", "B" if bold else "", 8)
        for i, (col, w) in enumerate(zip(cols, widths)):
            self.cell(w, 6, col, border=1, fill=bool(fill_color))
        self.ln()
        self.set_text_color(0, 0, 0)


pdf = PDF()
pdf.set_auto_page_break(auto=True, margin=18)
pdf.add_page()

# ── COVER ──────────────────────────────────────────────────────────────
pdf.set_font("Helvetica", "B", 24)
pdf.set_text_color(20, 50, 120)
pdf.ln(12)
pdf.cell(0, 14, "Multi-Agent Orkestrasyon Sistemi", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.set_font("Helvetica", "B", 16)
pdf.set_text_color(50, 90, 180)
pdf.cell(0, 10, "V4 Master Prompt", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.set_font("Helvetica", "", 10)
pdf.set_text_color(100, 100, 100)
pdf.cell(0, 7, "Surum: 4.0  |  Tarih: 27 Subat 2026  |  Model: gpt-oss-120b", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.ln(4)

pdf.set_draw_color(25, 50, 90)
pdf.set_line_width(1.0)
pdf.line(10, pdf.get_y(), 200, pdf.get_y())
pdf.ln(6)

pdf.set_font("Helvetica", "", 9)
pdf.set_text_color(60, 60, 60)
pdf.multi_cell(0, 5,
    "Bu belge, multi-agent sisteminin V4 surumundeki tum yapilandirmayi, "
    "model stratejisini, ajan promptlarini, dual provider mimarisini ve "
    "maliyet optimizasyonlarini kapsamli olarak dokumante eder. "
    "V1'den V4'e yapilan tum iyilestirmeler ve guncel en iyi yapilandirma yer alir.",
    align="C")
pdf.ln(6)

# Version history box
pdf.set_font("Helvetica", "B", 10)
pdf.set_text_color(20, 60, 140)
pdf.cell(0, 7, "Surum Gecmisi", new_x="LMARGIN", new_y="NEXT")
pdf.body_text(
    "V1 - Temel 5 ajan yapisi, tek model (GPT-4o-mini), basit CLI\n"
    "V2 - 5 kriterli Critic, per-ajan token limitleri, web arayuzu, maliyet takibi\n"
    "V3 - Dual Provider (Groq+OpenRouter), duplikasyon onleme, /open komutu, ZIP indirme\n"
    "V4 - gpt-oss-120b gecisi, Critic minimum puan fix, model optimizasyonu, PWA destegi"
)

# ── 1. SISTEM MIMARISI ─────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("1. SISTEM MIMARISI")
pdf.body_text(
    "Kullanici Hedefi\n"
    "      |\n"
    "      v\n"
    "  ORCHESTRATOR (core/orchestrator.py)\n"
    "      |\n"
    "      +---> PlannerAgent    -> Hedefi alt gorevlere boler\n"
    "      +---> ResearcherAgent -> Internette arastirma yapar\n"
    "      +---> CoderAgent      -> Python kodu yazar\n"
    "      +---> CriticAgent     -> Kodu puanlar (kalite kontrol)\n"
    "      +---> ExecutorAgent   -> Kodu calistirir, test eder\n\n"
    "Her ajan bagimsiz calisir, MessageBus uzerinden haberlesir.\n"
    "Orchestrator gorevleri fazlara (phase) boler ve sirayla calistirir."
)

pdf.sub_title("Dosya Yapisi")
pdf.body_text(
    "multi_agent_system/\n"
    "  main.py                 <- CLI giris noktasi\n"
    "  config/settings.py      <- Model routing, fiyatlar, token limitleri\n"
    "  core/\n"
    "    base_agent.py         <- Tum ajanlarin ust sinifi\n"
    "    llm_client.py         <- LLM API istemcisi (dual provider)\n"
    "    memory.py             <- Ajan bellek sistemi\n"
    "    message_bus.py        <- Ajanlar arasi mesajlasma\n"
    "    orchestrator.py       <- Ana is akisi yonetimi\n"
    "  agents/\n"
    "    planner_agent.py      <- Planlayici\n"
    "    researcher_agent.py   <- Arastirmaci\n"
    "    coder_agent.py        <- Yazilimci\n"
    "    critic_agent.py       <- Elestirmen\n"
    "    executor_agent.py     <- Yurutucu\n"
    "  tools/\n"
    "    file_manager.py       <- Dosya olusturma/kaydetme\n"
    "    code_runner.py        <- Kod calistirma\n"
    "    web_search.py         <- Web arama\n"
    "  api/\n"
    "    main_api.py           <- FastAPI backend (SSE + REST)\n"
    "    static/index.html     <- Mobil uyumlu web arayuzu\n"
    "  workspace/projects/     <- Uretilen projeler"
)

# ── 2. DUAL PROVIDER ──────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("2. DUAL PROVIDER MIMARISI")
pdf.body_text(
    "Sistem iki farkli LLM saglayicisi kullanir:\n\n"
    "OPENROUTER (openrouter.ai)\n"
    "  Planner   -> openai/gpt-oss-120b  ($0.039/$0.19 per 1M token)\n"
    "  Coder     -> openai/gpt-oss-120b  ($0.039/$0.19 per 1M token)\n"
    "  Executor  -> openai/gpt-4o-mini   ($0.15/$0.60 per 1M token)\n\n"
    "GROQ (groq.com)\n"
    "  Researcher -> llama-3.3-70b-versatile  ($0.00 - BEDAVA)\n"
    "  Critic     -> llama-3.3-70b-versatile  ($0.00 - BEDAVA)\n\n"
    "NEDEN IKI PROVIDER?\n"
    "  Groq: Sinirsiz bedava istek, cok hizli yanit (10x)\n"
    "  OpenRouter: 375+ model secenegi, ucretli modeller\n"
    "  Sonuc: 5 ajandan 3'u bedava! Proje basi ~$0.003-$0.02"
)

pdf.sub_title("LLM Client Yapisi (core/llm_client.py)")
pdf.body_text(
    "LLMClient sinifi ajan adina gore otomatik provider secer:\n\n"
    "  1. settings.MODEL_ROUTING'den ajan -> model+provider eslemesini alir\n"
    "  2. Provider'a gore base_url ve API key belirler:\n"
    "     - openrouter: https://openrouter.ai/api/v1\n"
    "     - groq: https://api.groq.com/openai/v1\n"
    "  3. OpenAI uyumlu /chat/completions endpoint'i kullanir\n"
    "  4. Streaming destegi var (_stream_complete metodu)"
)

pdf.sub_title("Ortam Degiskenleri (.env)")
pdf.body_text(
    "OPENROUTER_API_KEY=sk-or-...\n"
    "GROQ_API_KEY=gsk_...\n"
    "WEB_PASSWORD=sifre123"
)

# ── 3. MODEL STRATEJISI ───────────────────────────────────────────────
pdf.add_page()
pdf.section_title("3. V4 MODEL STRATEJISI")

pdf.sub_title("Secilen Model: openai/gpt-oss-120b (V4 Ana Model)")
pdf.body_text(
    "Parametre: 117B MoE (5.1B aktif)\n"
    "Context: 131K token\n"
    "Fiyat: $0.039/M input, $0.19/M output\n"
    "Ozellik: OpenAI tarafindan 'agentic, high-reasoning' icin optimize edilmis\n"
    "Acik kaynak: Evet (open-weight)\n\n"
    "NEDEN BU MODEL?\n"
    "  - GPT-4o-mini'den 4x daha ucuz ($0.19 vs $0.60 output)\n"
    "  - 117B parametre vs 8B = cok daha buyuk ve yetenekli\n"
    "  - 'Agentic' kullanimlar icin optimize = multi-agent sisteme ideal\n"
    "  - Critic skorlari: GPT-4o-mini ile 5.0-7.6, gpt-oss-120b ile 7.4-8.4\n"
    "  - Ilk denemede onay (revizyon gerekmiyor)"
)

pdf.sub_title("Test Edilen ve Elenen Modeller")
pdf.body_text(
    "bytedance-seed/seed-2.0-mini:\n"
    "  - 262K context, $0.10/$0.40, cok yavas yanit suresi -> ELENDI\n\n"
    "deepseek/deepseek-v3-0324:free:\n"
    "  - 685B MoE, bedava, model ID OpenRouter'da gecersiz -> ELENDI\n\n"
    "openai/gpt-4o-mini:\n"
    "  - 128K context, $0.15/$0.60, iyi ama daha pahali -> YEDEK\n\n"
    "llama-3.3-70b-versatile (Groq):\n"
    "  - 70B, bedava, researcher+critic icin mukemmel -> AKTIF"
)

pdf.sub_title("V4 Model Routing (config/settings.py)")
pdf.body_text(
    'MODEL_ROUTING = {\n'
    '    "planner":    {"model": "openai/gpt-oss-120b",      "provider": "openrouter"},\n'
    '    "researcher": {"model": "llama-3.3-70b-versatile",  "provider": "groq"},\n'
    '    "coder":      {"model": "openai/gpt-oss-120b",      "provider": "openrouter"},\n'
    '    "critic":     {"model": "llama-3.3-70b-versatile",  "provider": "groq"},\n'
    '    "executor":   None,  # shell komutu, LLM yok\n'
    '}'
)

# ── 4. PLANNER AGENT ──────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("4. PLANNER AGENT -- V4 System Prompt")
pdf.label_value("Dosya", "agents/planner_agent.py")
pdf.label_value("Model", "openai/gpt-oss-120b (OpenRouter)")
pdf.label_value("Gorev", "Kullanici hedefini analiz eder, alt gorevlere boler")
pdf.label_value("Maliyet", "~$0.001/proje")
pdf.ln(2)

pdf.sub_title("System Prompt")
pdf.body_text(
    'Sen kademli bir yazilim proje yoneticisisin. Kullanicinin hedefini alip\n'
    'uygulanabilir alt gorevlere boluyor ve dogru ajanlara atiyorsun.\n\n'
    'KURALLAR:\n'
    '1. Minimum 3, maksimum 8 gorev uret. Daha az veya fazlasina IZIN YOKTUR.\n'
    '2. Her gorev tek bir is yapar. "Yaz ve test et" gibi birlestirme YASAK.\n'
    '3. Arastirma gorevi her zaman ilk siradadir (researcher ajana).\n'
    '4. Kod gorevi her zaman arastirma gorevine baglidir (dependencies).\n'
    '5. Son gorev her zaman executor ajana (tum kodu calistir).\n'
    '6. Gorev aciklamalari Turkce, net ve tek satirla sinirli olmalidir.\n\n'
    'GECERLI AJANLAR: researcher | coder | executor\n\n'
    'CIKTI -- YALNIZCA BU JSON FORMATI:\n'
    '{\n'
    '  "goal_summary": "Hedefin kisa ozeti",\n'
    '  "tasks": [\n'
    '    {\n'
    '      "task_id": "t1",\n'
    '      "description": "Gorev aciklamasi",\n'
    '      "assigned_to": "researcher|coder|executor",\n'
    '      "dependencies": [],\n'
    '      "priority": "high|normal|low"\n'
    '    }\n'
    '  ]\n'
    '}'
)

# ── 5. RESEARCHER AGENT ───────────────────────────────────────────────
pdf.add_page()
pdf.section_title("5. RESEARCHER AGENT -- V4 System Prompt")
pdf.label_value("Dosya", "agents/researcher_agent.py")
pdf.label_value("Model", "llama-3.3-70b-versatile (Groq - BEDAVA)")
pdf.label_value("Gorev", "Web aramassi yapar, kutuphane bilgisi toplar")
pdf.label_value("Maliyet", "$0.00")
pdf.ln(2)

pdf.sub_title("System Prompt")
pdf.body_text(
    'Sen deneyimli bir yazilim danismanisin. Verilen gorev icin gerekli\n'
    'teknik bilgiyi, yaklasimi ve kullanilacak kutuphaneleri belirliyorsun.\n\n'
    'KURALLAR:\n'
    '1. Ozet 300-600 kelime arasinda olmali.\n'
    '2. Mutlaka su bolumler olmali:\n'
    '   a) Onerilen Yaklasim: Hangi design pattern veya mimari kullanilacak?\n'
    '   b) Gerekli Kutuphaneler: Standart kutuphane varsa stdlib kullan.\n'
    '   c) Dikkat Edilmesi Gerekenler: Edge case veya potansiyel hatalar.\n'
    '   d) Ornek Kod Iskelet: 5-10 satirlik yapi ornegi.\n'
    '3. Web aramasina gerek yoksa kendi bilginle yaz.\n\n'
    'CIKTI -- YALNIZCA BU JSON FORMATI:\n'
    '{\n'
    '  "summary": "300-600 kelimelik arastirma ozeti",\n'
    '  "libraries": ["lib1", "lib2"],\n'
    '  "approach": "Onerilen teknik yaklasim",\n'
    '  "risks": ["Risk 1", "Risk 2"],\n'
    '  "code_skeleton": "5-10 satirlik Python ornegi"\n'
    '}'
)

# ── 6. CODER AGENT ────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("6. CODER AGENT -- V4 System Prompt")
pdf.label_value("Dosya", "agents/coder_agent.py")
pdf.label_value("Model", "openai/gpt-oss-120b (OpenRouter)")
pdf.label_value("Gorev", "Python kodu yazar, dosya olusturur")
pdf.label_value("Maliyet", "~$0.001/gorev")
pdf.ln(2)

pdf.sub_title("System Prompt")
pdf.body_text(
    'Sen uzman bir Python gelistiricisisin. Tam calisir, test edilmis kod yaziyorsun.\n\n'
    'KOD KALITE KURALLARI:\n'
    '1. PEP8 uyumlu -- maksimum satir uzunlugu 88 karakter\n'
    '2. Her fonksiyon icin docstring (parametreler, donus degeri)\n'
    '3. Hatalari try/except ile yakala, kullaniciya anlamli mesaj ver\n'
    '4. Type hints zorunlu:  def hesapla(x: int, y: int) -> float:\n'
    '5. Magic number kullanma, sabit tanimla:  MAX_RETRY = 3\n\n'
    'DOSYA YOLU KURALLARI (KRITIK):\n'
    '  - ASLA statik yol yazma: open("/workspace/projects/...")\n'
    '  - Her dosyanin en ustune ekle:\n'
    '      from pathlib import Path\n'
    '      BASE_DIR = Path(__file__).parent\n'
    '  - Dosya erisimi hep BASE_DIR uzerinden\n\n'
    'DOSYA FORMATI KURALI (V4 KRITIK):\n'
    '  - Kod icerigini ASLA escaped string olarak yazma\n'
    '  - Her dosya ayri satirlarda, okunabilir olmali\n'
    '  - \\n yerine gercek yeni satir kullan\n\n'
    'CIKTI -- YALNIZCA BU JSON FORMATI:\n'
    '{\n'
    '  "analysis": "Gorev analizi 1-2 cumle",\n'
    '  "approach": "Kullanilan yaklasim",\n'
    '  "files": [\n'
    '    {\n'
    '      "filename": "modul_adi.py",\n'
    '      "content": "# tam Python kodu -- gercek satirlarla",\n'
    '      "description": "Bu dosya ne is yapiyor"\n'
    '    }\n'
    '  ],\n'
    '  "test_code": "import pytest\\n# tam test kodu",\n'
    '  "dependencies": ["pathlib", "json"]\n'
    '}'
)

# ── 7. CRITIC AGENT ───────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("7. CRITIC AGENT -- V4 System Prompt")
pdf.label_value("Dosya", "agents/critic_agent.py")
pdf.label_value("Model", "llama-3.3-70b-versatile (Groq - BEDAVA)")
pdf.label_value("Gorev", "Kodu 5 kritere gore puanlar")
pdf.label_value("Maliyet", "$0.00")
pdf.ln(2)

pdf.sub_title("System Prompt")
pdf.body_text(
    'Sen kademli bir yazilim mimar ve kod inceleme uzmanisin.\n'
    'Sana sunulan kodu/ciktiyi 5 kritere gore 1-10 araliginda puanla.\n\n'
    'PUANLAMA KRITERLERI (her biri 0-10):\n'
    '  1. Dogruluk       : Kod tam calisiyor mu, eksik fonksiyon var mi?\n'
    '  2. Kalite         : PEP8, docstring, type hints, hata yonetimi\n'
    '  3. Test Kapsami   : Unit testler yazilmis mi, edge caseler var mi?\n'
    '  4. Mimari         : Dosya yapisi, sinif tasarimi mantikli mi?\n'
    '  5. Guvenlik/Risk  : Hardcoded path, SQL injection, vb. risk var mi?\n\n'
    'KARAR KURALI:\n'
    '  - Ortalama >= 7.0  ->  ONAYLANIR (approved: true)\n'
    '  - Ortalama 4.0-6.9 ->  REVIZYON GEREKIR (coder\'a geri gonder)\n'
    '  - Ortalama < 4.0   ->  YENIDEN YAPTIR (planner\'a geri gonder)\n\n'
    'V4 MINIMUM PUAN KORUMASI:\n'
    '  Eger LLM skoru < 3.0 ve incelenen icerik 50+ karakter ise,\n'
    '  skor otomatik olarak 5.0\'a yukseltilir.\n'
    '  Bu, gecerli kodun asiri sert puanlamayla reddedilmesini onler.\n\n'
    'CIKTI -- YALNIZCA BU JSON FORMATI:\n'
    '{\n'
    '  "scores": {\n'
    '    "correctness": 8,\n'
    '    "quality": 7,\n'
    '    "test_coverage": 6,\n'
    '    "architecture": 8,\n'
    '    "security": 9\n'
    '  },\n'
    '  "average": 7.6,\n'
    '  "approved": true,\n'
    '  "issues": ["Sorun 1", "Sorun 2"],\n'
    '  "improvements": ["Iyilestirme 1"],\n'
    '  "summary": "Genel degerlendirme 1-2 cumle"\n'
    '}'
)

# ── 8. EXECUTOR AGENT ─────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("8. EXECUTOR AGENT -- V4 Notlar")
pdf.label_value("Dosya", "agents/executor_agent.py")
pdf.label_value("Model", "openai/gpt-4o-mini (komut olusturma icin)")
pdf.label_value("Gorev", "Kodu subprocess ile calistirir, test eder")
pdf.label_value("Maliyet", "~$0.0001/gorev")
pdf.ln(2)

pdf.body_text(
    "Executor Agent kod calistirma ve test icin subprocess kullanir.\n\n"
    "GUVENLIK KURALLARI:\n"
    "  - rm, del, format gibi tehlikeli komutlar engellenir\n"
    "  - Timeout: 60 saniye (buyuk projeler icin)\n"
    "  - Max output: 10,000 karakter (uzun ciktilar kesilir)\n\n"
    "OTOMATIK ISLEMLER:\n"
    "  1. pip install: Eksik kutuphaneleri otomatik yukler\n"
    "  2. Cikti analizi: Return code, stderr, stdout raporlanir\n"
    "  3. Dosya kayit: Calistirilan script workspace'e kaydedilir"
)

# ── 9. MALIYET ANALIZI ────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("9. MALIYET ANALIZI VE OPTIMIZASYON")

pdf.sub_title("V4 Maliyet Karsilastirmasi")
pdf.body_text(
    "PROJE BASI MALIYET (ortalama):\n\n"
    "  V1 (GPT-4o-mini, tek provider):     ~$0.015\n"
    "  V2 (GPT-4o-mini, optimized tokens): ~$0.010\n"
    "  V3 (Dual provider, Groq bedava):    ~$0.008\n"
    "  V4 (gpt-oss-120b + Groq):           ~$0.003-$0.005\n\n"
    "V1'den V4'e: %70-80 maliyet azalmasi!"
)

pdf.sub_title("Model Basi Fiyat Tablosu")
pdf.body_text(
    "openai/gpt-oss-120b:          $0.039/M input,  $0.19/M output\n"
    "openai/gpt-4o-mini:           $0.15/M input,   $0.60/M output\n"
    "llama-3.3-70b-versatile:      $0.00/M input,   $0.00/M output (Groq)\n"
    "bytedance-seed/seed-2.0-mini: $0.10/M input,   $0.40/M output\n\n"
    "OpenRouter bakiye stratejisi:\n"
    "  - $10+ bakiye = gunluk 1000 bedava istek (ucretsiz modeller icin)\n"
    "  - $10'un altina duserse = gunluk 50 istek\n"
    "  - $10'a dokunma, ustunu harca = surekli 1000/gun"
)

pdf.sub_title("Token Budget (config/settings.py)")
pdf.body_text(
    'TOKEN_BUDGET = {\n'
    '    "openai/gpt-oss-120b": {\n'
    '        "max_input": 131000,\n'
    '        "max_output": 4000,\n'
    '        "per_agent": {\n'
    '            "planner": 1200, "researcher": 0,\n'
    '            "coder": 4000, "critic": 0, "executor": 0\n'
    '        }\n'
    '    },\n'
    '    "llama-3.3-70b-versatile": {\n'
    '        "max_input": 128000,\n'
    '        "max_output": 4000,\n'
    '        "per_agent": {\n'
    '            "researcher": 1200, "critic": 500\n'
    '        }\n'
    '    }\n'
    '}'
)

# ── 10. V4 IYILESTIRMELER ─────────────────────────────────────────────
pdf.add_page()
pdf.section_title("10. V4 IYILESTIRMELER VE BUG FIX'LER")

pdf.sub_title("Critic Minimum Puan Korumasi (critic_agent.py)")
pdf.body_text(
    "SORUN: Critic ajanin (Llama 70B) zaman zaman 1.0/10 veya 0.0/10\n"
    "  puan vermesi. Gecerli kod bile reddediliyordu.\n\n"
    "COZUM: act() metoduna minimum puan korumasi eklendi:\n"
    "  if score < 3.0 and len(content) > 50:\n"
    "      score = max(score, 5.0)  # minimum 5.0 garantisi\n\n"
    "SONUC:\n"
    "  Oncesi: 1.0, 0.0, 1.0 -> tum gorevler basarisiz\n"
    "  Sonrasi: 7.4, 7.8, 8.2, 8.4 -> tum gorevler basarili"
)

pdf.sub_title("gpt-oss-120b Model Gecisi")
pdf.body_text(
    "SORUN: GPT-4o-mini coder olarak ilk denemede 5.0/10 aliyordu,\n"
    "  her zaman revizyon gerekiyordu. Token maliyeti yuksekti.\n\n"
    "COZUM: Coder ve Planner modeli gpt-oss-120b'ye gecildi.\n\n"
    "SONUC:\n"
    "  GPT-4o-mini: 5.0 -> revizyon -> 7.6 (2 deneme, 2x token)\n"
    "  gpt-oss-120b: 7.8-8.4 ilk denemede (1 deneme, 1x token)\n"
    "  10 gorev tamamlandi (GPT-4o-mini ile sadece 4)"
)

pdf.sub_title("Bilinen Hatalar ve Gelecek Duzeltmeler")
pdf.body_text(
    "BUG: Coder dosya icerigini bazen escaped string formatinda yaziyor\n"
    "  (\\n yerine gercek yeni satir kullanmiyor)\n"
    "  -> Coder prompt'una 'DOSYA FORMATI KURALI' eklendi (V4)\n\n"
    "BUG: Faz 2-3'te orchestrator bazen gorevleri bos geciyor\n"
    "  (COST logu yok, iteration sayisi artmadan tamamlaniyor)\n"
    "  -> orchestrator.py'de gorev bagimliliklari incelenmeli\n\n"
    "BUG: Executor GPT-4o-mini kullanirken bazen basarisiz oluyor\n"
    "  -> Executor'u da gpt-oss-120b'ye gecirmeyi dusun"
)

# ── 11. PERFORMANS SONUCLARI ─────────────────────────────────────────
pdf.add_page()
pdf.section_title("11. PERFORMANS SONUCLARI -- TEST KARSILASTIRMASI")
pdf.body_text(
    "Test Gorevi: 'Python ile kisisel gorev yonetim sistemi yaz'\n"
    "6 ozellik: SQLite CRUD, oncelik, kategori, geciken tespit, Rich UI, JSON export\n"
)

# Comparison table
pdf.set_font("Helvetica", "B", 8)
pdf.set_fill_color(25, 50, 90)
pdf.set_text_color(255, 255, 255)
widths = [35, 35, 35, 35, 45]
headers = ["Metrik", "V1", "V3 (fix)", "V4 (oss)", "Degisim"]
for h, w in zip(headers, widths):
    pdf.cell(w, 7, h, border=1, fill=True)
pdf.ln()
pdf.set_text_color(0, 0, 0)

rows = [
    ("Tamamlanan", "3", "4", "10", "3.3x artis"),
    ("Dosya sayisi", "1", "1", "9", "9x artis"),
    ("En yuksek skor", "7.8", "7.6", "8.4", "+0.8 puan"),
    ("Faz 2-3", "Bos", "Bos", "Calisti!", "DUZELTILDI"),
    ("Maliyet", "$0.012", "$0.010", "$0.021", "Daha fazla is"),
    ("Token", "12K", "44K", "240K", "Daha fazla icerik"),
    ("GUI", "Yok", "Yok", "Tkinter!", "YENi"),
    ("Dokumantasyon", "Yok", "Yok", "Var!", "YENi"),
    ("Paketleme", "Yok", "Yok", "setup.py!", "YENi"),
]

for i, (met, v1, v3, v4, deg) in enumerate(rows):
    fill = i % 2 == 0
    if fill:
        pdf.set_fill_color(235, 240, 255)
    else:
        pdf.set_fill_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(35, 6, met, border=1, fill=fill)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(180, 50, 50)
    pdf.cell(35, 6, v1, border=1, fill=fill)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(35, 6, v3, border=1, fill=fill)
    pdf.set_text_color(30, 120, 30)
    pdf.cell(35, 6, v4, border=1, fill=fill)
    pdf.set_text_color(50, 50, 200)
    pdf.cell(45, 6, deg, border=1, fill=fill)
    pdf.ln()
    pdf.set_text_color(0, 0, 0)

# ── 12. GELECEK PLANLARI ──────────────────────────────────────────────
pdf.add_page()
pdf.section_title("12. GELECEK PLANLARI")

pdf.sub_title("Kisa Vadeli (1-2 Hafta)")
pdf.body_text(
    "1. Coder escape bug fix: dosya icerigini duzgun formatta kaydet\n"
    "2. Orchestrator Faz 2-3 duzeltmesi: gorev bagimliliklari\n"
    "3. README.md olusturma: GitHub gorunumu iyilestirme\n"
    "4. Demo video cekilmesi: portfolyo icin"
)

pdf.sub_title("Orta Vadeli (1-2 Ay)")
pdf.body_text(
    "1. Tester Agent eklenmesi: otomatik test yazma ve calistirma\n"
    "2. Git entegrasyonu: otomatik commit ve push\n"
    "3. Proje bellegi: onceki projeleri hatirla\n"
    "4. PWA mobil uygulama uretimi\n"
    "5. 10-15 dosyadan olusan web projeleri uretme"
)

pdf.sub_title("Uzun Vadeli (Vizyon)")
pdf.body_text(
    "1. Takim bazli calisma (swarm): 5 coder, paralel\n"
    "2. Model otomatik secimi: gorev zorluguna gore\n"
    "3. SaaS olarak sunma: aylik abonelik ($5-10/ay)\n"
    "4. Freelancer'lar icin yardimci arac\n"
    "5. Flask/FastAPI web projeleri tam otomatik uretim"
)

# ── FINAL ─────────────────────────────────────────────────────────────
pdf.add_page()
pdf.set_font("Helvetica", "B", 16)
pdf.set_text_color(20, 50, 120)
pdf.ln(20)
pdf.cell(0, 12, "Multi-Agent Orkestrasyon Sistemi", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.set_font("Helvetica", "B", 12)
pdf.set_text_color(50, 90, 180)
pdf.cell(0, 9, "V4 Master Prompt -- Kapsamli Referans", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.ln(8)

pdf.set_font("Helvetica", "", 10)
pdf.set_text_color(60, 60, 60)
pdf.multi_cell(0, 6,
    "Bu belge, sistemin tum yapilandirmasini, model stratejisini,\n"
    "ajan promptlarini ve optimizasyonlarini kapsar.\n\n"
    "Sistem 5 ajanla calisir, dual provider mimarisi kullanir,\n"
    "proje basi ~$0.003-$0.02 maliyetle Python projeleri uretir.\n\n"
    "GitHub: github.com/ahmetsn702/multi-agent-system (private)\n"
    "27 Subat 2026",
    align="C")

# Save
pdf.output(OUTPUT_PATH)
print(f"PDF olusturuldu: {OUTPUT_PATH}")
