# 🎮 Gaming AI Clipper

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/Frontend-React_18_%2B_Vite-61DAFB.svg)](https://vitejs.dev/)
[![DeepSeek V3](https://img.shields.io/badge/Copywriting-DeepSeek_V3-blueviolet.svg)](https://openrouter.ai/)
[![Gemini 3.5 Flash](https://img.shields.io/badge/Judgment-Gemini_3.5_Flash-4285F4.svg)](https://ai.google.dev/)
[![Coverage](https://img.shields.io/badge/Coverage-97%25-brightgreen.svg)]()

> **Oyun videoları ve canlı yayın kayıtlarından (VODs) YouTube Shorts, TikTok ve Instagram Reels için otomatik olarak en viral anları tespit eden, kesen, altyazılandıran ve başlıklandıran otonom yapay zeka stüdyosu.**

---

## 🌟 Öne Çıkan Özellikler

- **🎯 5 Katmanlı Akıllı Tespit Mimarisi:**
  1. **Ses Sinyal İşleme (DSP):** RMS enerji patlamaları, sessizlikten çığlığa ani geçişler (*silence-to-scream*) ve dinamik aralık analizi.
  2. **İzleyici Tekrar Isı Haritası (Heatmap):** YouTube'un en çok izlenen ve tekrar sarılan anları ile sinyal füzyonu.
  3. **Google Gemini 3.5 Flash Yargılama:** Aday klipler arasındaki boş gürültüleri eleyip (`DROP`), gerçek eğlence ve aksiyon anlarını (`KEEP`) seçen jüri sistemi.
  4. **DeepSeek-V3 Kreatif Başlık & Metin Motoru:** Türk internet mizahına, oyun jargonuna ve algoritmaya uygun yüksek tıklanma oranlı (CTR) başlıklar, kısa kancalar ve 14 niş SEO etiketi.
  5. **Milisaniyelik Whisper Kelime Senkronu:** `faster-whisper` ile tam zamanlı neon sarı vurgulu tek satır Karaoke altyazılar (ASS formatı).

- **✂️ Profesyonel Video Edit Motoru (FFmpeg):**
  - Çoklu Format Desteği: `1:1 Kare`, `9:16 Shorts (Siyah)`, `9:16 Shorts (Blur Arkaplan)`, `16:9 Orijinal`.
  - İlk 3.5 saniyede animasyonlu kanca başlık kartı (*Hook Card*).
  - Renk canlandırma ve kontrast filtreleri (*Vibrancy boost*).
  - Shorts ve TikTok standardına uygun ses normalizasyonu (`-14 LUFS`).

- **🖥️ Modern React + Vite & FastAPI Mimarisi:**
  - 🎬 **Dashboard & Analiz:** Canlı SSE (Server-Sent Events) pipeline takibi, anlık sinyal adımları ve klip üretimi.
  - 📁 **Klip Kütüphanesi:** SQLite veritabanındaki tüm klipleri filtreleme, detay görüntüleme, indirme ve doğrudan yayınlama.
  - 📅 **Slot Planlayıcı:** 14 günlük takvim slotları (11:30, 15:30, 19:00, 22:30), havuz yönetimi ve akıllı shuffle.
  - 🤖 **AutoPilot:** Otomatik kanal tarama, çift katmanlı anchor video tespit sistemi ve otonom stok yönetimi.
  - 📤 **Platform Yayınlama & OAuth2:** Tek tıkla YouTube Shorts, Instagram Reels ve TikTok desteği.
  - ⚙️ **Ayarlar:** Dinamik API anahtarları, YouTube OAuth2 bağlantısı, disk ve önbellek yönetimi.

---

## 🏗️ Mimari & Çalışma Mantığı

```
                     [YouTube Video / Canlı Yayın]
                                   │
                                   ▼
 ┌───────────────────────────────────────────────────────────────────┐
 │ KATMAN 1 & 2: Sinyal İşleme & Isı Haritası Füzyonu               │
 │ • Audio DSP (RMS Enerji Zirveleri & Ani Çığlık Algılama)          │
 │ • YouTube Most Replayed Isı Haritası & Transkript Analizi         │
 └─────────────────────────────────┬─────────────────────────────────┘
                                   │ (Aday Havuzu)
                                   ▼
 ┌───────────────────────────────────────────────────────────────────┐
 │ KATMAN 3 & 4: Yapay Zeka Yargılama (Google Gemini 3.5 Flash)     │
 │ • Sahte alarmları ve boş gürültüleri eler                        │
 │ • Aksiyonun başladığı/bittiği saniyeleri tespit eder             │
 └─────────────────────────────────┬─────────────────────────────────┘
                                   │ (Seçilen Klipler)
                                   ▼
 ┌───────────────────────────────────────────────────────────────────┐
 │ KATMAN 5: Video Kurgu, Whisper Altyazı & DeepSeek-V3             │
 │ • faster-whisper ile milisaniyelik kelime zamanlaması             │
 │ • FFmpeg: 9:16 crop, renk canlandırma, -14 LUFS ses              │
 │ • DeepSeek-V3: Viral başlık, kanca ve SEO etiketleri              │
 └─────────────────────────────────┬─────────────────────────────────┘
                                   │
                                   ▼
               [YouTube Shorts / TikTok / Reels Çıktısı]
```

---

## 🚀 Hızlı Başlangıç

### 1. Gereksinimler
- Python 3.10 veya üzeri
- `ffmpeg` sistemi üzerinde kurulu olmalıdır:
  ```bash
  # Ubuntu / Debian
  sudo apt install ffmpeg

  # Arch Linux
  sudo pacman -S ffmpeg

  # macOS
  brew install ffmpeg
  ```

### 2. Kurulum
```bash
# Depoyu klonlayın
git clone https://github.com/tuncaycelikkanat/Clipper.git
cd Clipper

# Sanal ortam oluşturup aktif edin
python -m venv .venv
source .venv/bin/activate  # Windows için: .venv\Scripts\activate

# Bağımlılıkları yükleyin
pip install -r requirements.txt
```

### 3. Ortam Değişkenleri (.env)
Kök dizinde `.env` dosyasını oluşturun:
```env
# Google Gemini API Anahtarı (Klip seçimi ve kalite değerlendirme)
GEMINI_API_KEY=your_gemini_api_key_here

# OpenRouter API Anahtarı (DeepSeek-V3 ile başlık, kanca ve etiket üretimi)
OPENROUTER_API_KEY=your_openrouter_api_key_here

# Doğrudan DeepSeek API Anahtarı (İsteğe bağlı alternatif)
DEEPSEEK_API_KEY=your_deepseek_api_key_here
```

### 4. Başlatma
 
Tek bir komutla hem FastAPI backend'i (`http://localhost:8000`) hem de Vite frontend'i (`http://localhost:5173`) başlatabilirsiniz:

```bash
# Backend + Frontend geliştirici modu
./run.sh

# Sadece FastAPI Backend (Docs: http://localhost:8000/docs)
./run.sh backend

# Sadece Vite Frontend
./run.sh frontend
```

#### Komut Satırından Toplu Çalıştırma (CLI)
```bash
# Tek bir videoyu analiz edip 3 klip üretme
python -m clipper run --url "https://www.youtube.com/watch?v=..." --clips 3 --format square_1x1_black

# Altyazısız ve başlıksız hızlı kesim
python -m clipper run --url "https://www.youtube.com/watch?v=..." --no-subtitles --no-hook
```

---

## 🧪 Testler

Tüm birim ve entegrasyon testleri `pytest` ile çalıştırılabilir:
```bash
PYTHONPATH=. pytest tests/ --cov=core
```
*(Proje %97 kod kapsama oranına ve 190+ otomatik teste sahiptir).*

---

## 📄 Lisans

Bu proje [MIT Lisansı](LICENSE) altında lisanslanmıştır. © 2026 Tuncay Çelikkanat
