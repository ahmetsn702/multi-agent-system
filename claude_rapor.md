# Multi-Agent Orchestration System - Proje Analiz ve Durum Raporu

Merhaba Claude,

Şu anda Python tabanlı, 5 otonom ajanın (Multi-Agent) birbiriyle asenkron şekilde iletişim kurarak görevleri tamamladığı bir sistem geliştiriyoruz. Sistem, başlangıçta planlanan "Optimization Plan" aşamasını başarıyla tamamladı. Bu rapor, sistemin mimarisine, mevcut durumuna ve çözmemiz/danışmamız gereken güncel sonuca dair teknik detayları içermektedir. Genel mimariyi inceleyip bize geliştirmeler konusunda tavsiyeler vermeni rica ediyoruz.

## 1. Sistem Mimarisi ve Bileşenleri

Sistemimiz `httpx` ve `asyncio` tabanlı olup LLM olarak (hız ve maliyet optimizasyonu nedeniyle) **Groq API (Llama-3.3-70B)** kullanmaktadır. LLM çağrıları `core/llm_client.py` üzerinden yapılmakta ve token/maliyet hesaplamaları dinamik olarak izlenmektedir. Ajanlar birbirleriyle bir **Message Bus (Priority Queue)** üzerinden haberleşmektedir.

### Otonom Ajanlar (Agents)
1. **Planner Agent:** Kullanıcının ana hedefini (`Task`) alır ve bağımlılıklı alt görevlere (`subtasks`) böler.
2. **Researcher Agent:** İnternette araştırma yapar (DuckDuckGo), bilgileri sentezler ve kaynakçalı rapor döner.
3. **Coder Agent:** Görev tanımına göre Python kodu yazar, testlerini hazırlar ve kod içindeki hataları auto-fix etmeye çalışır.
4. **Critic Agent:** Gelen çıktıları/kodları 4 kritere göre değerlendirir (Okunabilirlik, hata yönetimi, performans, eksiksizlik). 1-10 arası puan verir. Puan durumuna göre işi Executor'a veya Coder'a (Revizyon) gönderir.
5. **Executor Agent:** Yazılan kodları izole bir Subprocess Sandbox içinde çalıştırır veya bash komutları donanımında `workspace` dizinine yazar.

### Altyapı (Core)
* **Orchestrator (`core/orchestrator.py`):** Sistemi ReAct döngüsü (Reason-Act-Observe) mantığıyla yönetir. Ajanların hata durumlarında 3'lük bir *retry* limiti vardır. İşler paralel olarak (`asyncio.gather`) yürütülebilir.
* **Memory (`core/memory.py`):** 
  - *Short-Term Memory:* Sliding window algoritması ile ajan başına sadece son 20 mesajı tutar.
  - *Long-Term Memory:* Proje bazlı klasörlere oturum verilerini kaydeder (`workspace/projects/{slug}/session.json`). Yeni oturumda planner'a geçmiş referans sağlamak için son 3 oturumu okur.

### Araçlar (Tools)
* `web_search.py`: MD5 hash ve 24-saat TTL(Time To Live) algoritması ile önbellekleme yapar. Bu sayede API istek sınırlarını (rate limits) azaltır.
* `code_runner.py` & `file_manager.py`: İşlemlerin sadece güvenli `workspace/` klasöründe yapılmasına (Jail/Sandbox kuralı) zorlar. Path dışına çıkılmasını `PermissionError` ile keser.

---

## 2. Optimizasyonlar (Success)
Projeye son eklediğimiz kritik özellikleri başarıyla çalıştırdık:
* Bütün ajan prompt'ları token israfını kesmek için ciddi şekilde küçültüldü (örneğin Critic Agent sadece 25 kelime + JSON).
* Rich kütüphanesiyle yazılan Terminal ekranında anlık token hesapları ve Session Cost loglanması yapıldı.
* Critic routing (Gelişmiş Ajan yönlendirmesi) aktif edildi.

---

## 3. Güncel Vaka ve Çözülemeyen Hata (Mevcut Durum)
Geçtiğimiz test senaryosunda ("Bir klasördeki txt dosyalarını bulup kelime sayan ve sıralayıp dosyaya kaydeden, testleri yazılmış Python scripti oluştur") sistem şunları başarabildi:

1. `txt_bul.py` oluşturuldu.
2. Regex ile kelime sayan `kelime_sayisi.py` oluşturuldu.
3. Bunları entegre eden `ana_fonksiyon.py` yazıldı.
4. Fakat **test yazma, dosyaları hedefe sıralı kaydetme (id4, id5, id6 nolu görevler)** aşamasında `Coder` ve `Executor` ajanları kodları yazmasına rağmen test çalıştırma veya dosyaya kaydetme döngülerinde **3 deneme sınırını aşıp başarısız oldu (failed after 3 attempts)**. 

### Soru ve Beklenti:
Coder Agent sisteminde alt dosyaların testini sandbox (subprocess) içinde çalıştırırken büyük ihtimalle "path/modül bulunamadı" veya `os.listdir()` işlemlerinde izole edilmiş `workspace/projects/{slug}` yol kısıtlamalarına çarpıyoruz. Ayrıca dosya yolları dinamik üretildiği için ajanlar kodlarda statik path denediklerinde testler patlıyor olabilir.

Claude, bu karmaşık Multi-Agent yapısında;
1. Executor ve Coder'ın dosya yetkileri veya test pathleri oluştururken aldıkları başarısızlıkları (Retry cycle failure) aşmaları için nasıl bir strateji önerebilirsin?
2. Sistemin genel Multi-Agent (Priority Queue, ReAct orchestrator vs.) mimari yapısını nasıl buluyorsun, darboğaz olabilecek noktalar sence nelerdir?
