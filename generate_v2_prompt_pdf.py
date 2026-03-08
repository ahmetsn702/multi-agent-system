"""
generate_v2_prompt_pdf.py
Generates the V2 Optimization Prompt PDF for the Multi-Agent System.
"""
from fpdf import FPDF
import os

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "v2_optimization_prompt.pdf")


class PDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 10)
        self.set_fill_color(30, 30, 50)
        self.set_text_color(255, 255, 255)
        self.cell(0, 10, "Multi-Agent System  |  V2 Optimization Prompts", fill=True, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.ln(2)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, f"Sayfa {self.page_no()}", align="C")

    def section_title(self, title):
        self.set_font("Helvetica", "B", 13)
        self.set_fill_color(40, 60, 100)
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
        self.cell(35, 6, label + ":", new_x="RIGHT", new_y="LAST")
        self.set_font("Helvetica", "", 9)
        self.set_text_color(0, 0, 0)
        self.multi_cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")


pdf = PDF()
pdf.set_auto_page_break(auto=True, margin=18)
pdf.add_page()

# ── COVER ──────────────────────────────────────────────────────────────
pdf.set_font("Helvetica", "B", 22)
pdf.set_text_color(20, 60, 140)
pdf.ln(10)
pdf.cell(0, 12, "Multi-Agent Orkestrasyon Sistemi", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.set_font("Helvetica", "B", 15)
pdf.set_text_color(60, 100, 200)
pdf.cell(0, 9, "V2 Optimization Prompts", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.set_font("Helvetica", "", 10)
pdf.set_text_color(100, 100, 100)
pdf.cell(0, 7, "Surum: 2.0  |  Tarih: 25 Subat 2026  |  Model: OpenRouter / gpt-4o-mini", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.ln(6)

pdf.set_draw_color(40, 60, 100)
pdf.set_line_width(0.8)
pdf.line(10, pdf.get_y(), 200, pdf.get_y())
pdf.ln(6)

pdf.set_font("Helvetica", "", 9)
pdf.set_text_color(60, 60, 60)
pdf.multi_cell(0, 5,
    "Bu belge, multi-agent sisteminin V2 surumuyle daha tutarli, yuksek kaliteli ve "
    "maliyet etkin ciktilar uretmesi icin optimize edilmis sistem promptlarini icerir. "
    "Her ajan icin ayri prompt, kritik kurallar ve JSON sema tanimlari verilmistir.",
    align="C")
pdf.ln(8)

# ── 1. GENEL STRATEJI ──────────────────────────────────────────────────
pdf.section_title("1. GENEL V2 STRATEJISi")
pdf.body_text(
    "V1'deki temel sorunlar:\n"
    "  - LLM zaman zaman JSON yerine markdown veya duz metin donduruyor\n"
    "  - Coder agent dosya kaydetme yollarini karistiriyor\n"
    "  - Critic puanlama kriterleri net degil\n"
    "  - Planner cok az veya cok fazla gorev uretebiliyor\n\n"
    "V2 optimizasyon hedefleri:\n"
    "  + Her prompt sona mutlaka JSON sema ornegi eklenecek\n"
    "  + Dosya yolu kurallari tum aganlara inject edilecek\n"
    "  + Critic 5 kriterle 1-10 puanlayacak (eskiden kriterler belirsizdi)\n"
    "  + Planner minimum 3, maksimum 8 gorev uretecek (kural eklendi)\n"
    "  + Researcher ozet uzunlugu 300-600 kelime arasinda sinirlandi"
)

# ── 2. PLANNER ──────────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("2. PLANNER AGENT  —  V2 System Prompt")
pdf.sub_title("Rol ve Sorumluluk")
pdf.body_text("Kullanici hedefini analiz eder ve sistematik alt gorevlere boler. Her gorev atomik (tek is yapan) olmali.")

pdf.sub_title("V2 System Prompt (agents/planner_agent.py icine koy)")
pdf.body_text(
    'Sen kademli bir yazilim proje yoneticisisin. Kullanicinin hedefini alip\n'
    'uygulanabilir alt gorevlere boluyor ve dogru ajanlara atiyorsun.\n\n'
    'KURALLAR:\n'
    '1. Minimum 3, maksimum 8 gorev uret. Daha az veya fazlasina IZIN YOKTUR.\n'
    '2. Her gorev tek bir is yapar. "Yaz ve test et" gibi birlestirme YASAK.\n'
    '3. Arastirma gorevi her zaman ilk siradadir (researcher agana).\n'
    '4. Kod gorevi her zaman arastirma gorevine baglidir (dependencies).\n'
    '5. Son gorev her zaman executor agana (tum kodu calistir).\n'
    '6. Gorev aciklamalari Turkce, net ve tek satirla sinirli olmalidlr.\n\n'
    'GECERLI AJANLAR: researcher | coder | executor\n\n'
    'CIKTI — YALNIZCA BU JSON FORMATI:\n'
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

pdf.sub_title("Sik Yapilan Hatalar (V1'den ogrendiklerimiz)")
pdf.body_text(
    "YANLIS: assigned_to = 'planner' yazmak  ->  Planner kendine gorev atamaz\n"
    "YANLIS: dependencies listesini bos birakmak  ->  Bagimliliklari mutlaka yaz\n"
    "YANLIS: 10+ gorev uretmek  ->  Sistem yavaslayip maliyet artiyor\n"
    "DOGRU: Her gorev icin onceki gorevlerin ID'lerini dependencies'a ekle"
)

# ── 3. RESEARCHER ─────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("3. RESEARCHER AGENT  —  V2 System Prompt")
pdf.sub_title("V2 System Prompt (agents/researcher_agent.py icine koy)")
pdf.body_text(
    'Sen deneyimli bir yazilim danismanisin. Verilen gorev icin gerekli\n'
    'teknik bilgiyi, yaklasimi ve kullanilacak kutuphaneleri belirliyorsun.\n\n'
    'KURALLAR:\n'
    '1. Ozet 300-600 kelime arasinda olmali. Daha uzun veya kisa olursa tekrar yaz.\n'
    '2. Mutlaka su bolumler olmali:\n'
    '   a) Onerilen Yaklasim: Hangi design pattern veya mimari kullanilacak?\n'
    '   b) Gerekli Kutuphaneler: Standart kutuphane varsa stdlib kullan.\n'
    '   c) Dikkat Edilmesi Gerekenler: Edge case veya potansiyel hatalar.\n'
    '   d) Ornek Kod Iskelet: 5-10 satirlik yapi ornegi.\n'
    '3. Web aramasina gerek yoksa yarimci bilgiyle yaz (kendi bilginle yeter).\n\n'
    'CIKTI — YALNIZCA BU JSON FORMATI:\n'
    '{\n'
    '  "summary": "300-600 kelimelik arastirma ozeti",\n'
    '  "libraries": ["lib1", "lib2"],\n'
    '  "approach": "Onerilen teknik yaklasim",\n'
    '  "risks": ["Risk 1", "Risk 2"],\n'
    '  "code_skeleton": "5-10 satirlik Python ornegi"\n'
    '}'
)

# ── 4. CODER ───────────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("4. CODER AGENT  —  V2 System Prompt")
pdf.sub_title("V2 System Prompt (agents/coder_agent.py icine koy)")
pdf.body_text(
    'Sen uzman bir Python gelistiricisisin. Tam calisir, test edilmis kod yaziyorsun.\n\n'
    'KOD KALITE KURALLARI:\n'
    '1. PEP8 uyumlu — maksimum satir uzunlugu 88 karakter\n'
    '2. Her fonksiyon icin docstring (parametreler, donus degeri, ornek)\n'
    '3. Hatalari try/except ile yakala, kullaniciya anlamli mesaj ver\n'
    '4. Type hints zorunlu:  def hesapla(x: int, y: int) -> float:\n'
    '5. Magic number kullanma, sabit tanimla:  MAX_RETRY = 3\n\n'
    'DOSYA YOLU KURALLARI (KRITIK):\n'
    '  - ASLA statik yol yazma: open("/workspace/projects/...")\n'
    '  - Her dosyanin en ustune ekle:\n'
    '      from pathlib import Path\n'
    '      BASE_DIR = Path(__file__).parent\n'
    '  - Dosya erisimi hep BASE_DIR uzerinden\n'
    '  - Test importlari icin:\n'
    '      import sys\n'
    '      sys.path.insert(0, str(Path(__file__).parent.parent / "src"))\n\n'
    'CIKTI — YALNIZCA BU JSON FORMATI (baska hicbir sey yazma):\n'
    '{\n'
    '  "analysis": "Gorev analizi 1-2 cumle",\n'
    '  "approach": "Kullanilan yaklasim",\n'
    '  "files": [\n'
    '    {\n'
    '      "filename": "modul_adi.py",\n'
    '      "content": "# tam Python kodu buraya\\n...",\n'
    '      "description": "Bu dosya ne is yapiyor"\n'
    '    }\n'
    '  ],\n'
    '  "test_code": "import pytest\\n# tam test kodu",\n'
    '  "usage_example": "Nasil calistirilir",\n'
    '  "dependencies": ["pathlib", "json"]\n'
    '}'
)

pdf.sub_title("V1'de sikca yasanan sorunlar ve cozumleri")
pdf.body_text(
    "SORUN: Kod markdown fence icinde geliyor (```python ... ```)\n"
    "COZUM: JSON prompt sona 'Markdown kod blogu kullanma, sadece JSON' ekle\n\n"
    "SORUN: Cikti JSON yerine duz metin\n"
    "COZUM: LLM'e 'Bu talimata uymayan her cevap basarisiz sayilir' yaz\n\n"
    "SORUN: test_code icinde import hatalari\n"
    "COZUM: sys.path.insert satirini zorunlu hale getir (yukardaki kural 6)"
)

# ── 5. CRITIC ──────────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("5. CRITIC AGENT  —  V2 System Prompt")
pdf.sub_title("V2 System Prompt (agents/critic_agent.py icine koy)")
pdf.body_text(
    'Sen kademli bir yazilim mimar ve kod inceleme uzmanisinn.\n'
    'Sana sunulan kodu/ciktiyi 5 kritere gore 1-10 araliginda puanla.\n\n'
    'PUANLAMA KRITERLERi (her biri 0-10):\n'
    '  1. Dogruluk       : Kod tam istiyor mu, eksik fonksiyon var mi?\n'
    '  2. Kalite         : PEP8, docstring, type hints, hata yonetimi\n'
    '  3. Test Kapsami   : Unit testler yazilmis mi, edge caseler var mi?\n'
    '  4. Mimari         : Dosya yapisi, sinif tasarimi mantikli mi?\n'
    '  5. Guvenlik/Risk  : Hardcoded path, SQL injection, vb. risk var mi?\n\n'
    'KARAR KURALI:\n'
    '  - Toplam Ortalama >= 7.0  ->  ONAYLANIR (approved: true)\n'
    '  - Toplam Ortalama <  7.0  ->  REVIZYON GEREKIR (approved: false)\n\n'
    'CIKTI — YALNIZCA BU JSON FORMATI:\n'
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
    '  "improvements": ["Iyilestirme 1", "Iyilestirme 2"],\n'
    '  "summary": "Genel degerlendirme 1-2 cumle"\n'
    '}'
)

# ── 6. EXECUTOR ────────────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("6. EXECUTOR AGENT  —  V2 Notlar")
pdf.body_text(
    "Executor Agent LLM kullanmaz, sadece sistem komutu yukutur.\n"
    "V2'de yapilmasi onerilen degisiklikler:\n\n"
    "  1. Timeout artirimi: 30s -> 60s (buyuk projeler icin)\n"
    "  2. pytest otomatik calistirma: Coder'dan sonra pytest'i yuklet\n"
    "  3. Hata loglama: Basarisiz komutlari error_log.txt'e yaz\n"
    "  4. Cikti boyut siniri: 10,000 karakterden uzun output'u kisalt\n\n"
    "executor_agent.py'de degistirilecek ayarlar:\n"
    "  DEFAULT_TIMEOUT = 60        # 30'dan 60'a\n"
    "  MAX_OUTPUT_CHARS = 10_000   # uzun ciktilar kesilebilir\n"
    "  AUTO_RUN_TESTS = True       # her coder gorevinden sonra pytest"
)

# ── 7. MALIYET OPTIMIZASYONU ───────────────────────────────────────────
pdf.section_title("7. MALiYET OPTiMiZASYONU")
pdf.body_text(
    "Mevcut durum (V1): Her gorev icin ortalama 5,000-8,000 token\n"
    "Hedef (V2)       : Her gorev icin ortalama 3,000-4,000 token\n\n"
    "Tasarruf yontemleri:\n"
    "  1. Short-term memory penceresi: 20 -> 10 mesaj (yarim maliyet)\n"
    "  2. Researcher ozeti 600 kelimeyle sinirla (kural eklendi)\n"
    "  3. Kriter_incele: Yalnizca coder ve researcher gonderilsin,\n"
    "     planner ve executor critic'e gitmemeli (gereksiz)\n"
    "  4. max_tokens: Planner icin 800, Researcher icin 1200,\n"
    "     Coder icin 4000, Critic icin 500 (eskiden hepsi 4000'di)\n\n"
    "Tahmini V2 tasarrufu: %35-45 daha az token => %35-45 daha az maliyet"
)

pdf.sub_title("Onerilen per-ajan max_tokens degerleri (settings.py)")
pdf.body_text(
    "planner   :  max_tokens = 800    (plan JSON kisa olmali)\n"
    "researcher:  max_tokens = 1200   (ozet 300-600 kelime)\n"
    "coder     :  max_tokens = 4000   (tam kod icin yeterli)\n"
    "critic    :  max_tokens = 500    (sadece puan JSON)\n"
    "executor  :  LLM kullanmaz"
)

# ── 8. MODEL STRATEJISI ────────────────────────────────────────────────
pdf.add_page()
pdf.section_title("8. GELECEK MODEL STRATEJiSi")
pdf.body_text(
    "Su an: gpt-4o-mini (test asamasi) — dusuK maliyet, orta kalite\n\n"
    "Sistem oturup calistigindan emin olunduktan sonra onerilen gecis:\n\n"
    "  SECENEK A — Dengeli (Onerilen):\n"
    "    planner   : gpt-4o-mini   (plan mantiginda yeterli)\n"
    "    researcher: gpt-4o-mini   (ozet mantiginda yeterli)\n"
    "    coder     : gpt-4o        (kod kalitesi kritik!)\n"
    "    critic    : gpt-4o-mini   (puanlama mantiginda yeterli)\n"
    "    executor  : LLM yok\n"
    "    Tahmini ek maliyet: ~3-4x artis ama cok daha kaliteli kod\n\n"
    "  SECENEK B — Premium:\n"
    "    Tum ajanlar: claude-3.5-sonnet (en iyi kod kalitesi)\n"
    "    Maliyet: ~10x artis, sadece final surum icin dusun\n\n"
    "  SECENEK C — Ucretsiz/Ekonomik:\n"
    "    OpenRouter ucretsiz modeller + 10$ bakiye = gunluk 1000 istek\n"
    "    model: meta-llama/llama-3.3-70b-instruct:free\n"
    "    Uyari: Kod kalitesi gpt-4o-mini'nin altinda"
)

# ── 9. HIZLI UYGULAMA REHBERI ─────────────────────────────────────────
pdf.section_title("9. HIZLI UYGULAMA REHBERi (V1 -> V2)")
pdf.body_text(
    "Adim 1: config/settings.py\n"
    "  TOKEN_BUDGET guncellemesi:\n"
    '  TOKEN_BUDGET = {\n'
    '    "GPT4O_MINI": {\n'
    '      "max_input": 128000,\n'
    '      "max_output": {  # per-agent\n'
    '        "planner": 800, "researcher": 1200,\n'
    '        "coder": 4000,  "critic": 500\n'
    '      }\n'
    '    }\n'
    '  }\n\n'
    "Adim 2: core/memory.py\n"
    "  ShortTermMemory max_size: 20 -> 10\n\n"
    "Adim 3: agents/critic_agent.py\n"
    "  5 kriterli skorlama sistemini yukle (bolum 5'teki prompt)\n\n"
    "Adim 4: agents/planner_agent.py\n"
    "  V2 promptu inject et, 'min 3 max 8 gorev' kuralini ekle\n\n"
    "Adim 5: agents/coder_agent.py\n"
    "  V2 promptu inject et, dosya yolu kurallarini (KRITIK bolum) ekle\n\n"
    "Adim 6: Test\n"
    "  python main.py \"Python ile basit bir Todo CLI yaz\"\n"
    "  Beklenen: 3-5 gorev, her gorev src/ icine kayit, Critic 7+ puan"
)

pdf.add_page()
pdf.set_font("Helvetica", "B", 11)
pdf.set_text_color(20, 60, 140)
pdf.cell(0, 9, "OZET — V1 vs V2 Karsilastirmasi", new_x="LMARGIN", new_y="NEXT")
pdf.set_text_color(0, 0, 0)
pdf.ln(2)

# Table headers
pdf.set_font("Helvetica", "B", 9)
pdf.set_fill_color(40, 60, 100)
pdf.set_text_color(255, 255, 255)
pdf.cell(50, 7, "Ozellik", border=1, fill=True)
pdf.cell(65, 7, "V1 (Mevcut)", border=1, fill=True)
pdf.cell(65, 7, "V2 (Hedef)", border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
pdf.set_text_color(0, 0, 0)

rows = [
    ("Planner kural", "Sinir yok", "Min 3, Max 8 gorev"),
    ("Coder dosya yolu", "Workspace koke yaziyor", "projects/{slug}/src/"),
    ("Critic puanlama", "Belirsiz kriterler", "5 kriterli, 1-10 skala"),
    ("Short-term bellek", "Son 20 mesaj", "Son 10 mesaj"),
    ("Per-ajan token", "Hepsi 4000", "Planner:800 Coder:4000"),
    ("Researcher ozet", "Sinir yok", "300-600 kelime"),
    ("Tahmini maliyet", "~$0.01/proje", "~$0.006/proje"),
    ("Model (test)", "gpt-4o-mini", "gpt-4o-mini"),
    ("Model (uretim)", "-", "coder -> gpt-4o"),
]

for i, (feat, v1, v2) in enumerate(rows):
    fill = i % 2 == 0
    pdf.set_fill_color(235, 240, 255) if fill else pdf.set_fill_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(50, 6, feat, border=1, fill=fill)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(180, 50, 50)
    pdf.cell(65, 6, v1, border=1, fill=fill)
    pdf.set_text_color(30, 120, 30)
    pdf.cell(65, 6, v2, border=1, fill=fill, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)

pdf.ln(10)
pdf.set_font("Helvetica", "I", 8)
pdf.set_text_color(100, 100, 100)
pdf.cell(0, 6, "Multi-Agent Orkestrasyon Sistemi  —  V2 Optimization Prompts  —  25 Subat 2026", align="C")

# Save
pdf.output(OUTPUT_PATH)
print(f"PDF olusturuldu: {OUTPUT_PATH}")
