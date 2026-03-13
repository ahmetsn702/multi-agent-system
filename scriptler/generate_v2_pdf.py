"""generate_v2_pdf.py - V2 Optimization Prompt PDF (ASCII only, no Unicode)"""
from fpdf import FPDF
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "v2_optimization_prompt.pdf")


class PDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 10)
        self.set_fill_color(30, 30, 50)
        self.set_text_color(255, 255, 255)
        self.cell(0, 10, "Multi-Agent System  |  V2 Optimization Prompts", fill=True, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0); self.ln(2)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, f"Sayfa {self.page_no()}", align="C")

    def stitle(self, t):
        self.set_font("Helvetica", "B", 13)
        self.set_fill_color(40, 60, 100); self.set_text_color(255, 255, 255)
        self.cell(0, 9, t, fill=True, align="L", new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0); self.ln(2)

    def sub(self, t):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(20, 60, 140)
        self.cell(0, 7, t, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)

    def body(self, t):
        self.set_font("Helvetica", "", 9)
        self.set_fill_color(245, 247, 252)
        self.multi_cell(0, 5, t, fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)


pdf = PDF()
pdf.set_auto_page_break(auto=True, margin=18)
pdf.add_page()

# --- COVER ---
pdf.set_font("Helvetica", "B", 22); pdf.set_text_color(20, 60, 140); pdf.ln(10)
pdf.cell(0, 12, "Multi-Agent Orkestrasyon Sistemi", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.set_font("Helvetica", "B", 15); pdf.set_text_color(60, 100, 200)
pdf.cell(0, 9, "V2 Optimization Prompts", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.set_font("Helvetica", "", 10); pdf.set_text_color(100, 100, 100)
pdf.cell(0, 7, "Surum: 2.0  |  Tarih: 25 Subat 2026  |  Model: OpenRouter / gpt-4o-mini", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.ln(6); pdf.set_draw_color(40, 60, 100); pdf.set_line_width(0.8)
pdf.line(10, pdf.get_y(), 200, pdf.get_y()); pdf.ln(6)
pdf.set_font("Helvetica", "", 9); pdf.set_text_color(60, 60, 60)
pdf.multi_cell(0, 5, "Bu belge, multi-agent sisteminin V2 surumuyle daha tutarli ve maliyet etkin ciktilar uretmesi icin optimize edilmis sistem promptlarini icerir.", align="C")
pdf.ln(8)

# --- 1. GENEL ---
pdf.stitle("1. GENEL V2 STRATEJISI")
pdf.body(
    "V1 sorunlari:\n"
    "  - LLM zaman zaman JSON yerine markdown donduruyor\n"
    "  - Coder dosya kaydetme yollarini karistiriyor\n"
    "  - Critic puanlama kriterleri belirsiz\n"
    "  - Planner cok az veya fazla gorev uretebiliyor\n\n"
    "V2 hedefleri:\n"
    "  + Her prompt sona JSON sema ornegi ekler\n"
    "  + Dosya yolu kurallari tum ajanlara eklendi\n"
    "  + Critic 5 kriterle 1-10 skalasiyla puanliyor\n"
    "  + Planner minimum 3, maksimum 8 gorev uretiyor\n"
    "  + Researcher ozet uzunlugu 300-600 kelime ile sinirli"
)

# --- 2. PLANNER ---
pdf.add_page()
pdf.stitle("2. PLANNER AGENT  -  V2 System Prompt")
pdf.sub("Rol ve Sorumluluk")
pdf.body("Kullanici hedefini analiz eder, atomik alt gorevlere boler ve dogru ajanlara atar.")
pdf.sub("V2 System Prompt  (agents/planner_agent.py icine koy)")
pdf.body(
    "Sen kademli bir yazilim proje yoneticisisin.\n"
    "Kullanicinin hedefini uygulanabilir alt gorevlere boluyorsun.\n\n"
    "KURALLAR:\n"
    "1. Minimum 3, maksimum 8 gorev uret. Kural delinirse basarisiz sayilir.\n"
    "2. Her gorev tek bir is yapar. 'Yaz ve test et' birlesimi YASAK.\n"
    "3. Arastirma gorevi her zaman ilk siradadir (researcher agana).\n"
    "4. Kod gorevi arastirma gorevine baglidir - dependencies listele.\n"
    "5. Son gorev her zaman executor agana gitmelidir.\n"
    "6. Gorev aciklamalari Turkce, net ve tek satir olmalidir.\n\n"
    "GECERLI AJANLAR: researcher | coder | executor\n\n"
    'CIKTI - YALNIZCA BU JSON:\n'
    '{\n'
    '  "goal_summary": "hedefin kisa ozeti",\n'
    '  "tasks": [\n'
    '    {"task_id": "t1", "description": "gorev",\n'
    '     "assigned_to": "researcher", "dependencies": [], "priority": "high"}\n'
    '  ]\n'
    '}'
)
pdf.sub("Sik Yapilan Hatalar  (V1 deneyimi)")
pdf.body(
    "YANLIS: assigned_to='planner'  -> Planner kendine gorev atamaz\n"
    "YANLIS: dependencies listesini bos birakmak\n"
    "YANLIS: 10+ gorev uretmek -> Sistem yavaslayip maliyet artar\n"
    "DOGRU: Her gorev icin onceki gorev ID lerini dependencies a ekle"
)

# --- 3. RESEARCHER ---
pdf.add_page()
pdf.stitle("3. RESEARCHER AGENT  -  V2 System Prompt")
pdf.body(
    "Sen deneyimli bir yazilim danismanisin.\n"
    "Verilen gorev icin teknik bilgiyi ve kutuphaneleri belirliyorsun.\n\n"
    "KURALLAR:\n"
    "1. Ozet mutlaka 300-600 kelime arasinda olmali.\n"
    "2. Mutlaka su 4 bolum olmali:\n"
    "   a) Onerilen Yaklasim: hangi design pattern kullanilacak\n"
    "   b) Gerekli Kutuphane: stdlib varsa onu sec\n"
    "   c) Dikkat Edilecekler: edge case ve potansiyel hatalar\n"
    "   d) Ornek Iskelet: 5-10 satirlik Python yapisi\n"
    "3. Kendi bilginle yaz, web aramasina gerek yoksa yapma.\n\n"
    'CIKTI - YALNIZCA BU JSON:\n'
    '{\n'
    '  "summary": "300-600 kelimelik ozet",\n'
    '  "libraries": ["lib1", "lib2"],\n'
    '  "approach": "onerilen teknik yaklasim",\n'
    '  "risks": ["Risk 1", "Risk 2"],\n'
    '  "code_skeleton": "# 5-10 satir ornek"\n'
    '}'
)

# --- 4. CODER ---
pdf.add_page()
pdf.stitle("4. CODER AGENT  -  V2 System Prompt")
pdf.body(
    "Sen uzman bir Python gelistiricisisin.\n"
    "Tam calisir, test edilmis, PEP8 uyumlu kod yaziyorsun.\n\n"
    "KOD KALITE KURALLARI:\n"
    "1. PEP8 uyumlu - maks satir uzunlugu 88 karakter\n"
    "2. Her fonksiyon icin docstring (parametreler, donus degeri, ornek)\n"
    "3. Hatalari try/except ile yakala, anlamli mesaj ver\n"
    "4. Type hints zorunlu: def hesapla(x: int, y: int) -> float:\n"
    "5. Magic number kullanma: MAX_RETRY = 3 gibi sabit tanimla\n\n"
    "DOSYA YOLU KURALLARI (KRITIK - her zaman uygula):\n"
    "  - ASLA statik yol yazma: open('/workspace/projects/...')\n"
    "  - Her dosyanin en ustune ekle:\n"
    "      from pathlib import Path\n"
    "      BASE_DIR = Path(__file__).parent\n"
    "  - Test importlari icin:\n"
    "      import sys\n"
    "      sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))\n\n"
    'CIKTI - YALNIZCA BU JSON (baska hicbir sey yazma):\n'
    '{\n'
    '  "analysis": "gorev analizi 1-2 cumle",\n'
    '  "approach": "kullanilan yaklasim",\n'
    '  "files": [\n'
    '    {"filename": "modul.py", "content": "# kod", "description": "ne yapar"}\n'
    '  ],\n'
    '  "test_code": "import pytest\\n# testler",\n'
    '  "usage_example": "nasil calistirilir",\n'
    '  "dependencies": ["pathlib", "json"]\n'
    '}'
)
pdf.sub("V1 Sikca Yasanan Sorunlar ve Cozumleri")
pdf.body(
    "SORUN: Kod markdown fence icinde geliyor (```python...```)\n"
    "COZUM: Prompta 'Markdown kullanma, sadece JSON don' ekle\n\n"
    "SORUN: Cikti JSON yerine duz metin\n"
    "COZUM: 'Bu talimata uymayan her cevap basarisiz sayilir' ekle\n\n"
    "SORUN: test_code icinde import hatalari\n"
    "COZUM: sys.path.insert satirini zorunlu hale getir"
)

# --- 5. CRITIC ---
pdf.add_page()
pdf.stitle("5. CRITIC AGENT  -  V2 System Prompt")
pdf.body(
    "Sen kademli bir yazilim mimar ve kod inceleme uzmanisinn.\n"
    "Sana sunulan kodu/ciktiyi 5 kritere gore 1-10 araliginda puanla.\n\n"
    "PUANLAMA KRITERLERI (her biri 1-10):\n"
    "  1. Dogruluk     : Kod tam istiyor mu, eksik fonksiyon var mi?\n"
    "  2. Kalite       : PEP8, docstring, type hints, hata yonetimi\n"
    "  3. Test Kapsami : Unit testler var mi, edge caseler kapsaniyor mu?\n"
    "  4. Mimari       : Dosya yapisi ve sinif tasarimi mantikli mi?\n"
    "  5. Guvenlik     : Hardcoded path, SQL injection vb. risk var mi?\n\n"
    "KARAR KURALI:\n"
    "  Ortalama >= 7.0  ->  ONAYLANIR  (approved: true)\n"
    "  Ortalama <  7.0  ->  REVIZYON   (approved: false)\n\n"
    'CIKTI - YALNIZCA BU JSON:\n'
    '{\n'
    '  "scores": {"correctness": 8, "quality": 7,\n'
    '             "test_coverage": 6, "architecture": 8, "security": 9},\n'
    '  "average": 7.6,\n'
    '  "approved": true,\n'
    '  "issues": ["Sorun 1"],\n'
    '  "improvements": ["Iyilestirme 1"],\n'
    '  "summary": "genel degerlendirme"\n'
    '}'
)

# --- 6. EXECUTOR ---
pdf.add_page()
pdf.stitle("6. EXECUTOR AGENT  -  V2 Notlar")
pdf.body(
    "Executor LLM kullanmaz, sadece sistem komutu yukuter.\n"
    "V2 icin onerilen degisiklikler:\n\n"
    "  1. Timeout artirimi: 30s -> 60s (buyuk projeler icin)\n"
    "  2. pytest otomatik calistirma: Coder bittikten sonra testleri yuklet\n"
    "  3. Hata loglama: Basarisiz komutlari error_log.txt e kaydet\n"
    "  4. Max output: 10.000 karakterden uzun ciktiyi kisalt\n\n"
    "executor_agent.py guncellemeleri:\n"
    "  DEFAULT_TIMEOUT = 60\n"
    "  MAX_OUTPUT_CHARS = 10_000\n"
    "  AUTO_RUN_TESTS = True"
)

pdf.stitle("7. MALIYET OPTIMIZASYONU")
pdf.body(
    "V1: Her gorev ortalama 5.000-8.000 token\n"
    "V2: Her gorev ortalama 3.000-4.000 token (hedef)\n\n"
    "Tasarruf yontemleri:\n"
    "  1. Short-term memory: 20 -> 10 mesaj (neredeyse yarim maliyet)\n"
    "  2. Researcher ozeti max 600 kelime ile sinirla\n"
    "  3. Critic e yalnizca coder ve researcher gonderilsin\n"
    "  4. Per-ajan max_tokens:\n"
    "       planner    = 800    (plan JSON kisa olmali)\n"
    "       researcher = 1200   (ozet sinirli)\n"
    "       coder      = 4000   (tam kod gerekli)\n"
    "       critic     = 500    (sadece puan JSON)\n\n"
    "Tahmini V2 tasarrufu: %35-45 daha az token ve maliyet"
)

# --- 8. MODEL ---
pdf.add_page()
pdf.stitle("8. GELECEK MODEL STRATEJISI")
pdf.body(
    "Su an: gpt-4o-mini (test asamasi) - dusuk maliyet, orta kalite\n\n"
    "Sistem olgunlasinca onerilen gecis plani:\n\n"
    "SECENEK A - Dengeli (Onerilen):\n"
    "  planner   : gpt-4o-mini  (plan mantiginda yeterli)\n"
    "  researcher: gpt-4o-mini  (ozet mantiginda yeterli)\n"
    "  coder     : gpt-4o       (kod kalitesi kritik!)\n"
    "  critic    : gpt-4o-mini  (puanlama icin yeterli)\n"
    "  executor  : LLM yok\n"
    "  Ek maliyet: ~3-4x artis, cok daha kaliteli kod\n\n"
    "SECENEK B - Premium:\n"
    "  Tum ajanlar: claude-3.5-sonnet (en iyi kod kalitesi)\n"
    "  Maliyet: ~10x artis - sadece final surum icin dusunulebilir\n\n"
    "SECENEK C - Ucretsiz:\n"
    "  model: meta-llama/llama-3.3-70b-instruct:free (OpenRouter)\n"
    "  10 dolar bakiye = gunluk 1000 istek limiti\n"
    "  Uyari: Kod kalitesi gpt-4o-mini nin altinda kalabilir"
)

pdf.stitle("9. HIZLI UYGULAMA REHBERI (V1 -> V2)")
pdf.body(
    "Adim 1: config/settings.py\n"
    "  TOKEN_BUDGET per-ajan guncelle:\n"
    "  planner:800, researcher:1200, coder:4000, critic:500\n\n"
    "Adim 2: core/memory.py\n"
    "  ShortTermMemory max_size: 20 -> 10\n\n"
    "Adim 3: agents/critic_agent.py\n"
    "  5 kriterli skorlama sistemini yukle (Bolum 5 deki prompt)\n\n"
    "Adim 4: agents/planner_agent.py\n"
    "  V2 promptu inject et, 'min 3 max 8 gorev' kuralini ekle\n\n"
    "Adim 5: agents/coder_agent.py\n"
    "  V2 promptu inject et, dosya yolu kurallarini (KRITIK) ekle\n\n"
    "Adim 6: Test et\n"
    "  python main.py \"Python ile basit bir Todo CLI yaz\"\n"
    "  Beklenen: 3-5 gorev, src/ e kayit, Critic 7+ puan"
)

# --- SUMMARY TABLE ---
pdf.add_page()
pdf.set_font("Helvetica", "B", 11); pdf.set_text_color(20, 60, 140)
pdf.cell(0, 9, "OZET - V1 vs V2 Karsilastirmasi", new_x="LMARGIN", new_y="NEXT")
pdf.set_text_color(0, 0, 0); pdf.ln(2)

pdf.set_font("Helvetica", "B", 9)
pdf.set_fill_color(40, 60, 100); pdf.set_text_color(255, 255, 255)
pdf.cell(50, 7, "Ozellik", border=1, fill=True)
pdf.cell(65, 7, "V1 (Mevcut)", border=1, fill=True)
pdf.cell(65, 7, "V2 (Hedef)", border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
pdf.set_text_color(0, 0, 0)

rows = [
    ("Planner kural",     "Sinir yok",              "Min 3, Max 8 gorev"),
    ("Coder dosya yolu",  "Workspace koke yazar",    "projects/{slug}/src/"),
    ("Critic puanlama",   "Belirsiz kriterler",      "5 kriterli, 1-10 skala"),
    ("Short-term bellek", "Son 20 mesaj",            "Son 10 mesaj"),
    ("Per-ajan token",    "Hepsi 4000",              "Planner:800 Coder:4000"),
    ("Researcher ozet",   "Sinir yok",               "300-600 kelime"),
    ("Tahmini maliyet",   "~$0.01/proje",            "~$0.006/proje"),
    ("Model (test)",      "gpt-4o-mini",             "gpt-4o-mini"),
    ("Model (uretim)",    "-",                       "coder -> gpt-4o"),
]

for i, (f, v1, v2) in enumerate(rows):
    fill = i % 2 == 0
    pdf.set_fill_color(235, 240, 255) if fill else pdf.set_fill_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(50, 6, f, border=1, fill=fill)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(180, 50, 50)
    pdf.cell(65, 6, v1, border=1, fill=fill)
    pdf.set_text_color(30, 120, 30)
    pdf.cell(65, 6, v2, border=1, fill=fill, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)

pdf.ln(10)
pdf.set_font("Helvetica", "I", 8); pdf.set_text_color(100, 100, 100)
pdf.cell(0, 6, "Multi-Agent Orkestrasyon Sistemi  -  V2 Optimization Prompts  -  25 Subat 2026", align="C")

pdf.output(OUT)
print(f"PDF olusturuldu: {OUT}")
