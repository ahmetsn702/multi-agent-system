# MAOS V5 (Multi-Agent Orchestration System) Proje Raporu

## 1. Projenin Amacı ve Kapsamı
**MAOS (Multi-Agent Orchestration System)**, kullanıcıdan alınan doğal dil formatındaki bir yazılım projesi fikrini anlayan, planlayan, kodlayan, donanımsal ve mantıksal testlerini yapan, hataları kendi kendine düzelterek en sonunda çalışan bir uygulama (CLI, Web, API veya Mobil APK) olarak teslim eden **yapay zeka destekli otonom yazılım geliştirme sistemidir.**

Bu sistemin temel amacı, bir yazılım ekibini (müşteri temsilcisi, mimar, yazılımcı, test uzmanı vb.) yapay zeka ajanları ile simüle ederek yazılım geliştirme sürecindeki insan müdahalesini en aza indirmek ve sıfırdan otonom bir ürün ortaya koymaktır.

---

## 2. Sistem Mimarisi ve Çekirdek Yapı
Sistem iki ana omurga üzerinde şekillenmiştir:

1. **Orkestratör (Orchestrator):** Tüm sistemin beynidir. Kullanıcı komutunu alır, projeyi yönetir, ajanları sırasıyla göreve çağırır ve aralarındaki bilgi akışını koordine eder. Sistem takılırsa döngüyü yeniden kurar.
2. **Mesaj Veriyolu (Message Bus):** Ajanların (Agent) kendi aralarında asenkron ve güvenli bir iletişim kurmasını sağlayan, olay-güdümlü (event-driven) yayın/abonelik (pub/sub) sistemidir. Bir ajan işini bitirdiğinde veriyoluna mesaj bırakır, sıradaki ajan bu mesaja göre tepki verir.

---

## 3. Yapay Zeka Ajanları ve Rolleri
Projede her biri kendi uzmanlık alanına sahip yapay zeka ajanları (Agents) bulunmaktadır:

* 🧠 **Planner Agent (Planlayıcı Ajan):** Kullanıcının isteğini analiz eder, mimari tasarımı yapar ve projenin gerçekleştirilmesi için adım adım "Görevler (Tasks)" listesi oluşturur.
* 💻 **Coder Agent (Yazılımcı Ajan):** Planlayıcıdan gelen blueprint'e (plan) sadık kalarak projenin kaynak kodlarını, dosyalarını ve modüllerini yazar. Son sürümde (V5) yaygın söz dizimi engellerini kendi algılayıp onarabiliyor (Auto-fix mekanizması).
* ⚙️ **Executor Agent (Çalıştırıcı Ajan):** Yazılan kodları izole bir Python terminalinde veya shell ortamında çalıştırır. (Örn: Paket yükleme, modül çalıştırma). Kodu dener, konsol çıktısını yakalar.
* 🕵️ **Linter Agent (Kalite Ajanı):** Kodu statik analiz araçlarıyla (Pylint vb.) tarayarak PEP-8 uyumluluğunu, temiz kod prensiplerini ve optimizasyonlarını denetler, puanlar.
* 🧪 **Tester & UITester Agent (Test Uzmanları):** Yazılan algoritmalar için Unit Testler (Pytest) çalıştırır. Eğer proje Web projesi ise `UITester` ajanı, Selenium/Pyppeteer kullanarak tarayıcıyı ayağa kaldırır, UI'ın ekran görüntüsünü alır ve görsel kalitesini ölçer.
* 🧐 **Critic Agent (Eleştirmen Ajan):** Kodu tasarım, mantık ve güvenlik açısından yüksek seviyede eleştirir. Kod gözden geçirmesini (Code Review) yapar.
* 💾 **Memory Agent (Hafıza Ajanı):** ChromaDB (Sematik Vektör Veritabanı) tabanlıdır. Önceki projelerdeki çözümleri, dosyaları ve yazılan fonksiyonları akılında tutar. Yeni bir projede benzer durumla karşılaşırsa "geçmiş hafızadan" o kodu hatırlar ve sisteme bağlar.
* 📱 **Builder Agent (Derleyici Ajan) (YENİ!):** Proje tamamlandıktan sonra eğer hedef bir platform uygulaması ise kodu derleyip son haline getirir. Örneğin; "flet" tabanlı mobil tasarımları alıp doğrudan **.apk** formatında build alır ve kullanıcıya "Al telefonuna kur" der.

---

## 4. Otonom Çalışma Akışı (Workflow)
Bir proje süreci şu adımlardan geçer:
1. **Talep:** Kullanıcı "Bana pomodoro tekniği için bir mobil uygulama yaz" der.
2. **Hafıza & Şablon:** Sistem geçmiş başarılarını (Memory) tarar ve eğer "mobil/apk" anahtar kelimesini gördüyse projeyi `Flet` altyapısı üstünde kurgulamaya karar verir.
3. **Planlama:** PlannerAgent, backend ve frontend için taslaklar hazırlar.
4. **Kodlama & Test (ReAct Döngüsü):** 
   - Coder, login ekranını yazar.
   - Executor çalıştırır. Pylint denetler. Testler yapılır.
   - Eğer terminalde *HATA (Exception)* çıkarsa, Linter hatayı okuyup Coder'a "Şu parametre yanlış, tekrar yaz" diyerek kodu geri gönderir. (Agentic Feedback Loop)
   - Kod hatasız çalışana veya testleri geçene kadar ajanlar kendi aralarında paslaşır.
5. **Derleme:** Web ise UI testleri alınır, mobil ise BuilderAgent ayağa kalkar ve projeden Android (APK) çıktısı üretir.
6. **Teslimat:** Sistem, hazırladığı dizini kullanıcıya hatasız ve hazır sunar.

---

## 5. MAOS V5 ile Gelen Kritik Çözümler ve Yenilikler
Proje sadece bir ChatGPT sarmalayıcısı (wrapper) değildir; karmaşık mühendislik problemlerine otonom çözümler geliştirilmiştir:
* **Rich Console & Subprocess Ayrışması:** Alt ajanların çalıştırdığı terminal uygulamalarının (özellikle Flet derleyicisinin renk kodlarının) ana sistemin arayüzünü bozması, Ortam Değişkenleri (ENV -> `TERM=dumb, NO_COLOR=1`) izole edilerek önlendi.
* **Semantic Vector Memory (Vektörel Hafıza):** ChromaDB teknolojisi sisteme entegre edildi. Ajan, boş dosyalarla değil; bağlamsal veri tabanından aldığı *("Buna benzer daha önce X kodunu yazmıştık")* context ile provalı çalışır. `Empty Tags` metadata çökmeleri önlendi.
* **Koşullu Bypass (Smart Skipping):** Örneğin, Coder bir CLI uygulaması yazdıysa "UITester", bu projenin bir web sitesi olmadığını [orchestrator.py](file:///c:/Users/ahmed/OneDrive/Masa%C3%BCst%C3%BC/Multi-Agent/multi_agent_system/core/orchestrator.py) içindeki analizden anlayıp (`is_flet_mobile` vb.) o görevi kasten atlar (skip). Kaynak ve token (API bütçesi) tasarrufu sağlar.
* **Auto-Fixing LLM Hataları:** LLM'lerin kronik olarak ürettiği spesifik söz dizimi (syntax) hataları (Örn: Boş bloklu `if :` veya yanlış büyük-küçük harfli `ft.icons.`) string manipülasyonları ve Regex ile arkaplanda otomatik tespit edilerek sisteme onarılmış olarak verilir.

## 6. Sonuç
MAOS V5, günümüz yazılım mimarilerini tekdüze prompt mühendisliğinden çıkararak; "Analiz, Üretim, Doğrulama ve Derleme" safhalarını mikro-servis benzeri yapay zeka işçileriyle (Agent) eşzamanlı yapan, kendine yetebilen, hata ayıklayabilen (self-debugging) olgun bir otonom yazılım fabrikasyon mimarisidir.
