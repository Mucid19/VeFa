# VeFa - Akademik Tez & Makale Asistanı 🎓

**VeFa**, YÖK standartlarında tam otomatik tez ve makale hazırlama, inceleme ve çeviri platformudur. Yapay zeka destekli modern web mimarisi (React + FastAPI) sayesinde literatür taramasından bölüm yazımına, belge denetiminden biçimlendirmeye kadar tüm akademik süreçleri tek bir merkezden yönetmenizi sağlar.

## 🚀 Özellikler (Modüller)

VeFa, birbirine entegre 3 ana modülden oluşmaktadır:

### 🔎 Mod 1: Akademik Kaynak Bulucu ve İndirici
- Verilen konu ve başlıklara uygun, güvenilir akademik kaynakları (Makale, Tez, Bildiri) otomatik olarak tarar.
- **Semantic Scholar**, **OpenAlex** ve **Genel Web** üzerinden arama yapar.
- Bulunan PDF dosyalarını otomatik olarak indirip tezinizin/makalenizin kaynak havuzuna ekler.

### ✍️ Mod 2: Yapay Zeka ile Akademik Tez/Makale Üretimi
- Mod 1'de indirilen kaynakları okuyarak yapılandırılmış bir tez veya makale oluşturur.
- **RAG (Retrieval-Augmented Generation)** teknolojisi kullanır; bilgileri sadece akademik dosyalardan çekerek halüsinasyonu engeller.
- Çıktıyı doğrudan **YÖK Standartlarında** (Kapak, İçindekiler, Roma rakamlı sayfalama vb.) Word (`.docx`) belgesine dönüştürür. 

### 🛠️ Mod 3: Denetle & Çevir (Akademik Editör)
- Daha önceden yazdığınız bir Word belgesini yükleyerek gelişmiş denetimden geçirebilir veya yapılandırılmış akademik çeviri (Örn: Arapça -> Türkçe) yapabilirsiniz.
- Sadece metni çevirmekle kalmaz, çıktıyı tekrar YÖK standartlarında kusursuz bir Word şablonuna oturtarak size teslim eder.

## ⚙️ Modern Mimari ve Sistem Tepsisi (System Tray) Entegrasyonu

VeFa, eski terminal tabanlı çalışan sistemlerden farklı olarak **tamamen arka planda, sessiz çalışan modern bir masaüstü uygulaması** hissiyatı sunar.

- **Ön Yüz:** React ve Vite kullanılarak geliştirilmiş, Dark Mode ve Glassmorphism destekli süper hızlı modern arayüz.
- **Arka Uç:** Python ve FastAPI tabanlı, yüksek performanslı asenkron yapay zeka motoru.
- **Sistem Tepsisi:** Rahatsız edici CMD (siyah ekran) pencereleri olmadan çalışır. Görev çubuğunun sağ alt köşesindeki VeFa logosundan tek tıkla arayüze erişilebilir ve yönetilebilir.

## 🤖 Desteklenen Yapay Zeka Modelleri
- **Yerel ve Ücretsiz (Ollama):** İnternetsiz tam gizlilik için *DeepSeek*, *Llama3*, *Mistral*, *Qwen* gibi yerel modelleri destekler.
- **Bulut API'leri:** Google Gemini, OpenAI, Anthropic, Groq.

## 📥 Kurulum & Kullanım

1. Gerekli Python kütüphanelerini kurun:
   ```bash
   pip install -r requirements.txt
   ```
2. Ön yüz (React) kütüphanelerini kurun:
   ```bash
   cd frontend
   npm install
   ```
3. **Uygulamayı Başlatın:**
   Ana klasördeki **`VeFa_Baslat.vbs`** dosyasına çift tıklayın. Hiçbir pencere açılmayacak, sistem arka planda sessizce başlayacak ve birkaç saniye içinde tarayıcınızda arayüz açılacaktır.
   Sistemi kapatmak için sağ alt köşedeki (saat yanındaki) VeFa ikonuna sağ tıklayıp **"Çıkış Yap"** demeniz yeterlidir.

## 🔒 Güvenlik & Gizlilik
- Ollama kullandığınızda, hiçbir PDF belgeniz veya tez taslağınız internete yüklenmez. Tüm işlemler %100 yerel bilgisayarınızın donanımında gerçekleşir.
- Gelişmiş veri güvenliği ve akademik etik kurallarına uygun tasarlanmıştır.

---
*Geliştiriciler için not: Arka plan süreçleri `backend/VeFa_Tray.py` dosyası üzerinden soket (socket) kilitleri kullanılarak yönetilir ve mükerrer başlatmalar engellenir.*
