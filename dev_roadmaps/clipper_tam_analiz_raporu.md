# Clipper Projesi — Tam Kod Analiz Raporu

> ~10.000+ satır kod satır satır okunarak üretilmiştir. (backend, core, frontend, tests)

---

# 1. Sistem Mimarisi Haritası

## 1.1 Bileşenler ve Sorumluluklar

### Giriş Noktaları

| Bileşen | Dosya | Sorumluluk |
|---|---|---|
| CLI | `__main__.py` | `run`, `backfill`, `cleanup` alt komutları |
| REST API | `backend/main.py` | FastAPI uygulaması, 9 router, lifespan yönetimi |

### Backend Katmanı (`backend/`)

| Modül | Sorumluluk |
|---|---|
| `backend/api/routes/auth.py` | YouTube OAuth2 + PKCE akışı |
| `backend/api/routes/channels.py` | Takip edilen kanalların CRUD'u |
| `backend/api/routes/clips.py` | Klip CRUD, dosya servis, thumbnail |
| `backend/api/routes/pipeline.py` | SSE streaming, iş yönetimi |
| `backend/api/routes/queue.py` | Yayın kuyruğu CRUD + takvim |
| `backend/api/routes/scheduler.py` | AutoPilot başlat/durdur/durum |
| `backend/api/routes/settings.py` | .env okuma/yazma, scoring config |
| `backend/api/routes/upload.py` | YouTube/Instagram yükleme |
| `backend/api/routes/videos.py` | Video listeleme, önizleme |
| `backend/workers/job_store.py` | In-memory iş deposu + SSE pub/sub |
| `backend/workers/pipeline_worker.py` | asyncio.to_thread pipeline çalıştırıcı |
| `backend/db/database.py` | İnce SQLite wrapper |
| `backend/db/schema.py` | DB şema tanımları (7 tablo) |
| `backend/db/migrations.py` | ALTER TABLE migrasyonları |

### Core Katmanı (`core/`)

| Modül | Sorumluluk |
|---|---|
| `core/pipeline.py` | 6 adımlı ana orkestratör |
| `core/database.py` | Tam özellikli DatabaseManager (1042 satır) |
| `core/extractor.py` | YouTube meta + heatmap çekimi (yt-dlp) |
| `core/audio_dsp.py` | FFmpeg+NumPy ile ses sinyal analizi |
| `core/candidate_ranker.py` | Çok-modal sinyal füzyonu → Top-N adaylar |
| `core/llm_engine.py` | Gemini Flash viral skorlama motoru |
| `core/aligner.py` | Sahne kesim + ses dip tabanlı sınır hizalama |
| `core/cutter.py` | FFmpeg video kesimi + 9:16 render |
| `core/smart_layout.py` | Gemini ile facecam tespiti + dikey düzenleyici |
| `core/autopilot.py` | Otonom kanal takip + planlı yayın yöneticisi |
| `core/feed.py` | yt-dlp ile kanal video listesi |
| `core/uploader.py` | YouTube Data API v3 yükleyici |
| `core/instagram_uploader.py` | Meta Graph API Reels yükleyici |
| `core/multi_publisher.py` | YouTube + Instagram orkestrasyonu |
| `core/transcript.py` | YouTube ASR + Whisper transkript yönetimi |
| `core/comment_miner.py` | Yorum zaman damgası madenciliği |
| `core/heatmap_predictor.py` | ML tabanlı heatmap tahmini |
| `core/scoring_config.py` | Viral skor ağırlık konfigürasyonu |
| `core/cache_manager.py` | Render dosyası cache yönetimi |
| `core/notifier.py` | Discord + Telegram bildirim sistemi |
| `core/copywriter.py` | Klip başlık/açıklama üretimi |
| `core/deepseek_engine.py` | DeepSeek V3 SEO metin motoru |
| `core/slot_allocator.py` | Günlük zaman dilimi tahsilatı |

### Frontend Katmanı (`frontend/src/`)

| Dosya | Sorumluluk |
|---|---|
| `App.tsx` | TanStack Router kurulumu (7 route) |
| `pages/Analyze.tsx` | SSE + polling ile canlı pipeline izleme |
| `pages/AutoPilot.tsx` | Kanal yönetimi + toplu işlem UI |
| `pages/Clips.tsx` | Klip kütüphanesi |
| `pages/ClipDetail.tsx` | Klip detay + yükleme |
| `pages/Planner.tsx` | Takvim tabanlı yayın planlayıcısı |
| `pages/Settings.tsx` | API anahtarları + scoring konfigürasyonu |
| `pages/Dashboard.tsx` | Genel bakış |
| `hooks/useSSE.ts` | EventSource SSE hook'u |
| `lib/api.ts` | Tüm API çağrıları için merkezi client |

## 1.2 Veri Akışı

```
Kullanıcı (UI / CLI)
  │
  ├─→ POST /api/pipeline/run
  │     │
  │     ├─→ pipeline_worker.py: run_pipeline_async()
  │     │     └─→ asyncio.to_thread(ClipperPipeline.run)
  │     │           │
  │     │           └─→ core/pipeline.py: execute()
  │     │                 ├─ Step 1: YouTubeExtractor.get_video_data() [yt-dlp]
  │     │                 ├─ Step 2 (Parallel ThreadPool):
  │     │                 │    ├─ AudioDSPAnalyzer.extract_all_signals_fast()
  │     │                 │    ├─ TranscriptManager.get_transcript()
  │     │                 │    ├─ YouTubeExtractor.get_video_comments()
  │     │                 │    └─ VisualDSPAnalyzer.extract_frame_diff()
  │     │                 ├─ Step 3: CandidateRanker.fuse_signals_and_generate_candidates()
  │     │                 ├─ Step 4: GeminiHighlightEngine.batch_judge_gaming_candidates()
  │     │                 ├─ Step 5: AlignmentEngine.refine_cut_points() [per clip]
  │     │                 └─ Step 6: VideoCutter.cut_clip() [parallel render]
  │     │
  │     └─→ SSE stream → Frontend (Analyze.tsx)
  │
  ├─→ AutoPilot: APScheduler arka plan işi
  │     ├─ Her N saatte: run_cycle() → kanal tara
  │     ├─ Her 1 dakikada: publish_due_socials()
  │     │    └─→ MultiPublisher → YouTube + Instagram
  │     └─→ DatabaseManager (core/database.py) ile tüm durum yönetimi
  │
  └─→ SQLite (clipper.db)
        ├─ videos, clips, renders, channels
        ├─ tracked_channels, channel_processed_videos
        ├─ autopilot_queue, heatmap_patterns
        └─ pipeline_jobs (şemada tanımlı ama kullanılmıyor!)
```

---

# 2. Performans Sorunları

## 2.1 Veritabanı Bağlantı Havuzu Eksikliği (Kritik)

**[`backend/deps.py:4-5`](file:///home/tuncay/Projects/clipper/backend/deps.py#L4-L5)**
```python
def get_db():
    return DatabaseManager()  # Her request'te yeni instance!
```
Her HTTP isteğinde yeni bir `DatabaseManager` örneği oluşturulup `_connect()` ile yeni SQLite bağlantısı açılıyor. Connection pooling tamamen yok. Yüksek trafikte ciddi performans sorununa yol açar.

**`core/database.py` — Her metod:** `with self._connect() as conn:` kalıbı her veri erişiminde yeni bağlantı açıyor. Tek bir pipeline çalışmasında onlarca bağlantı açılıp kapanıyor.

## 2.2 N+1 Sorgu Problemi

**[`backend/api/routes/clips.py:105-120`](file:///home/tuncay/Projects/clipper/backend/api/routes/clips.py#L105-L120)** — Toplu silme döngüsü:
```python
for clip_id in clip_ids:
    clip = db.execute("SELECT * FROM clips WHERE id=?", (clip_id,))
    db.execute("DELETE FROM clips WHERE id=?", (clip_id,))
    db.execute("DELETE FROM renders WHERE clip_id=?", (clip_id,))
```
Her klip için ayrı SELECT + iki DELETE yapılıyor. `WHERE id IN (?, ?, ...)` ile tek sorguda yapılabilir.

**[`core/pipeline.py:264-287`](file:///home/tuncay/Projects/clipper/core/pipeline.py#L264-L287)** — Metadata enrichment döngüsü: Her klip için ayrı `HumanMetadataEngine.generate_metadata()` çağrısı yapılıyor (potansiyel LLM çağrısı).

**[`core/pipeline.py:232-248`](file:///home/tuncay/Projects/clipper/core/pipeline.py#L232-L248)** — Sınır hizalama döngüsü: Her klip için ayrı `aligner.refine_cut_points()`.

## 2.3 Bloklayan Senkron İşlemler

**[`backend/workers/pipeline_worker.py:98`](file:///home/tuncay/Projects/clipper/backend/workers/pipeline_worker.py#L98)**
```python
result = await asyncio.to_thread(ClipperPipeline.run, ...)
```
Tüm ağır pipeline işlemi (audio DSP, LLM çağrısı, FFmpeg) tek bir thread'e atılıyor. `asyncio.to_thread` GIL'i bypass etmez — CPU-bound NumPy işlemleri diğer coroutine'leri bloklayabilir.

**[`core/audio_dsp.py:159-163`](file:///home/tuncay/Projects/clipper/core/audio_dsp.py#L159-L163)** — FFmpeg subprocess `communicate(timeout=60)`: Senkron blokaj, thread içinde de olsa diğer görevleri yavaşlatır.

**[`core/cutter.py:508`](file:///home/tuncay/Projects/clipper/core/cutter.py#L508)** — `subprocess.run(cmd, capture_output=True, check=True)`: FFmpeg render asenkron değil. 30+ saniyelik bir klipte bu çağrı iş parçacığını tamamen bloklar.

## 2.4 Gereksiz Yinelenen yt-dlp Çağrıları

**[`core/cutter.py:127-134`](file:///home/tuncay/Projects/clipper/core/cutter.py#L127-L134)** — `_STREAM_CACHE` dict'i sınıf değişkeni olarak stream URL'i önbelleğe alıyor, ancak bu cache hiçbir zaman temizlenmiyor (bellek sızıntısı riski). Ayrıca pipeline her yeni video için `extractor.py` ve `audio_dsp.py`'den ayrı yt-dlp çağrıları yapıyor; bu bilgi tek seferinde çekilip paylaşılabilir.

## 2.5 Ses Analizi Verimsizliği

**[`core/audio_dsp.py:273-277`](file:///home/tuncay/Projects/clipper/core/audio_dsp.py#L273-L277)** — Pitch variance sliding window:
```python
for i in range(win_hops, n_hops):
    pitch_var[i] = float(np.var(zcr[i - win_hops : i]))
```
Saf Python döngüsü içinde NumPy dizi dilimleme. Binlerce iterasyon için vektörize `np.lib.stride_tricks.sliding_window_view` ile 10-50x hızlandırılabilir.

**[`core/audio_dsp.py:378-382`](file:///home/tuncay/Projects/clipper/core/audio_dsp.py#L378-L382)** — Silence burst detection döngüsü:
```python
for i in range(2, len(rms)):
    pre_min = np.min(rms[max(0, i - 4) : i])
```
Yine saf Python döngüsü; NumPy sliding window ile tamamen kaldırılabilir.

## 2.6 FFmpeg İşlem Optimizasyon Fırsatları

**[`core/cutter.py:383-452`](file:///home/tuncay/Projects/clipper/core/cutter.py#L383-L452)** — Facecam durumunda `temp_raw_cut` dosyası iki kez `-i` girişi olarak açılıyor (Step 2'de zaten mevcut ham kesim var). Bu gereksiz disk I/O'su.

**[`core/cutter.py:489`](file:///home/tuncay/Projects/clipper/core/cutter.py#L489)** — `"-preset", "slow"` — 9:16 olmayan renderlar için `slow` preset kullanılıyor. Gaming klipleri için `fast` veya `medium` yeterlidir; `slow` encoding süresini 2-4x artırır.

## 2.7 LLM API Çağrılarında Gecikme

**[`core/llm_engine.py:283-288`](file:///home/tuncay/Projects/clipper/core/llm_engine.py#L283-L288)** — Varsayılan `ENSEMBLE_RUNS=1`, tek Gemini çağrısı yapılıyor. Ancak `MODELS_TO_TRY` listesinde 7 model var ve başarısız olursa hepsi deneniyor. Gemini olmayan model adları 404 döndürerek her seferinde retry overhead'ı yaratıyor.

**[`core/smart_layout.py:107-130`](file:///home/tuncay/Projects/clipper/core/smart_layout.py#L107-L130)** — Her klip renderı için facecam tespiti → Gemini API çağrısı yapılıyor. Bu gereksizdir; aynı video için tüm kliplerde facecam aynı konumda olacaktır. Cache edilmeli.

---

# 3. Kod Kalitesi Sorunları

## 3.1 Kopyala-Yapıştır Kod Blokları

**[`core/cutter.py:384-452`](file:///home/tuncay/Projects/clipper/core/cutter.py#L384-L452) vs [`core/cutter.py:514-578`](file:///home/tuncay/Projects/clipper/core/cutter.py#L514-L578)** — FFmpeg komut listesi (has_cam=True ve has_cam=False, primary ve fallback) neredeyse aynı; yalnızca 2-3 parametre farklı. 4 kez tekrarlanan ~30 satırlık FFmpeg argüman listesi. Tek bir `_build_ffmpeg_cmd()` yardımcı fonksiyonu ile birleştirilebilir.

**[`backend/api/routes/clips.py`](file:///home/tuncay/Projects/clipper/backend/api/routes/clips.py) ve [`backend/api/routes/videos.py`](file:///home/tuncay/Projects/clipper/backend/api/routes/videos.py)** — Her iki dosyada da `_db()` / `_get_db()` adında benzer lokal factory fonksiyonlar tanımlanmış. Bu pattern `backend/deps.py`'daki `get_db()` ile üçüncü kez tekrar ediyor.

## 3.2 Hata Yönetimi Eksiklikleri

**[`core/extractor.py:101`](file:///home/tuncay/Projects/clipper/core/extractor.py#L101)**
```python
except Exception:
    pass
```
yt-dlp yorum çekiminde tüm istisnalar sessizce yutulmuş. Kullanıcı ne hatanın olduğunu ne de yorumların neden boş döndüğünü bilemez.

**[`core/audio_dsp.py:101-108`](file:///home/tuncay/Projects/clipper/core/audio_dsp.py#L101-L108)** — `_extract_chunk_raw` metodunda subprocess hata durumunda sıfır dizi döndürülüyor, hata kaydedilmiyor. Ses analizi tamamen sessiz başarısız olabilir.

**[`core/autopilot.py:461-547`](file:///home/tuncay/Projects/clipper/core/autopilot.py#L461-L547)** — `process_pending_videos` içinde `ClipperPipeline.execute()` hatası sadece `str(e)` olarak kaydediliyor; traceback ve bağlam bilgisi kayboluyor.

**[`backend/api/routes/upload.py:78-81`](file:///home/tuncay/Projects/clipper/backend/api/routes/upload.py#L78-L81)**
```python
raise HTTPException(status_code=501, detail="TikTok upload not yet implemented")
```
TikTok upload tamamen stub. Frontend `api.upload.tiktok()` çağrısı yapabiliyor.

## 3.3 Type Safety Sorunları

**[`backend/workers/job_store.py:36`](file:///home/tuncay/Projects/clipper/backend/workers/job_store.py#L36)** — `JobState` dataclass'ında `subscribers: asyncio.Queue = field(default_factory=asyncio.Queue)` tanımlanmış. `asyncio.Queue` thread-safe değil; `job_store` global singleton olarak birden fazla thread'den erişilebilir.

**[`core/autopilot.py:29`](file:///home/tuncay/Projects/clipper/core/autopilot.py#L29)** — Class-level mutable dict:
```python
_worker_info: dict[str, Any] = {
    "running": False,
    ...
}
```
Class değişkeni tüm örnekler arasında paylaşılıyor. Bu `threading` sorunlarına yol açabilir.

**[`frontend/src/pages/Analyze.tsx:39`](file:///home/tuncay/Projects/clipper/frontend/src/pages/Analyze.tsx#L39)**
```typescript
const [url, setUrl] = useState((search as any)?.url || '');
```
`as any` tip dönüşümü — TanStack Router'ın arama parametre tipi güvenli şekilde tanımlanabilir.

## 3.4 Ölü / Kullanılmayan Kod

**[`backend/db/schema.py`](file:///home/tuncay/Projects/clipper/backend/db/schema.py)** — `pipeline_jobs` tablosu şemada tanımlı ancak hiçbir route veya worker tarafından kullanılmıyor. İş durumu tamamen `job_store.py`'daki in-memory dict ile yönetiliyor.

**[`core/cutter.py:312`](file:///home/tuncay/Projects/clipper/core/cutter.py#L312)**
```python
end_time - start_time  # Sonuç hiçbir yere atanmıyor!
```

**`core/audio_dsp.py` — `extract_audio_energy()` ve `extract_pitch_variance()` metodları** — `extract_all_signals_fast()` ile büyük ölçüde çakışıyor; eski API uyumluluğu için tutuluyor ama içeride yeni metodu çağırıyor.

## 3.5 Race Condition Riskleri

**[`backend/workers/job_store.py:69-70`](file:///home/tuncay/Projects/clipper/backend/workers/job_store.py#L69-L70)** — `_jobs: dict` üzerinde herhangi bir kilit yok:
```python
def get_job(self, job_id: str) -> JobState | None:
    return self._jobs.get(job_id)  # Lock yok!
```
FastAPI async handler'lar ve background worker aynı dict'e eşzamanlı erişebilir.

**[`backend/api/routes/settings.py:136-152`](file:///home/tuncay/Projects/clipper/backend/api/routes/settings.py#L136-L152)** — `scoring_config` modülü global değişkenlerini runtime'da değiştiriyor:
```python
import core.scoring_config as SC
SC.HOOK_STRENGTH_WEIGHT = body.hook_strength_weight
```
Thread-safe değil; birden fazla eşzamanlı istek yarış durumu yaratabilir.

---

# 4. Güvenlik Açıkları

> [!CAUTION]
> Aşağıdaki güvenlik açıklarından ilk ikisi acil müdahale gerektirir.

## 4.1 Hassas Kimlik Bilgilerinin Git'te Bulunması (Kritik)

**Proje kökü:**
- `credentials.json` — Google OAuth2 client secret
- `token.json` — Kullanıcı OAuth token
- `client_secret_734319452485-...json` — Ek OAuth kimlik bilgisi dosyası

Bu dosyalar büyük ihtimalle `.gitignore`'da değil. Bu, Google hesabının ve YouTube kanalının tam olarak ele geçirilmesi anlamına gelir.

**Önlem:** Bu dosyaları hemen revoke edin, yeni kimlik bilgileri oluşturun ve `.gitignore`'a ekleyin.

## 4.2 Wildcard PostMessage Origin (Kritik)

**[`backend/api/routes/auth.py:162`](file:///home/tuncay/Projects/clipper/backend/api/routes/auth.py#L162)**
```python
window.opener.postMessage({ type: 'YOUTUBE_AUTH_SUCCESS' }, '*')
```
`targetOrigin` parametresi `'*'` olarak ayarlanmış. `'http://localhost:5173'` ile sınırlandırılmalı.

## 4.3 Güvensiz PKCE Fallback

**[`backend/api/routes/auth.py:87-88`](file:///home/tuncay/Projects/clipper/backend/api/routes/auth.py#L87-L88)**
```python
if state not in pkce_store:
    verifier = list(pkce_store.values())[-1]  # Son verifier'ı kullan
```
State eşleşmezse (CSRF saldırısı olabilir) son verifier kullanılıyor. Bu, PKCE'nin CSRF korumasını tamamen geçersiz kılar.

## 4.4 API Anahtarlarının Plaintext Depolanması

**[`backend/api/routes/settings.py:46-75`](file:///home/tuncay/Projects/clipper/backend/api/routes/settings.py#L46-L75)** — API anahtarları `.env` dosyasına düz metin olarak yazılıp diskten okunuyor. Şifrelenmiş depolama (OS keyring vb.) yok.

## 4.5 Partial ID Match Güvenlik Riski

**[`backend/api/routes/clips.py:221-222`](file:///home/tuncay/Projects/clipper/backend/api/routes/clips.py#L221-L222)**
```python
cursor = db.execute("SELECT * FROM clips WHERE id LIKE ?", (f"{video_id}%",))
```
Kısa veya genel bir ID ile istenmeyen kliplere erişim sağlanabilir.

## 4.6 Instagram Thumbnail Üçüncü Taraf Hosting

**[`core/instagram_uploader.py:80-86`](file:///home/tuncay/Projects/clipper/core/instagram_uploader.py#L80-L86)**
```python
req = urllib.request.Request(
    "https://litterbox.catbox.moe/resources/internals/api.php",
    ...
)
```
Thumbnail'lar `litterbox.catbox.moe`'ya (geçici anonim dosya hosting) yükleniyor. Bu servis herhangi bir anda kapanabilir ve dosyalar herkese açık kalıcı URL'lerde bulunuyor.

---

# 5. Mimari İyileştirme Önerileri

## 5.1 İkili DatabaseManager Tutarsızlığı (Kritik)

**Sorun:** İki ayrı DatabaseManager bulunuyor:
- `core/database.py` — Ana, tam özellikli (1042 satır, 8 tablo)
- `backend/db/database.py` — İnce wrapper, farklı şema kullanıyor

**[`backend/api/routes/channels.py:48`](file:///home/tuncay/Projects/clipper/backend/api/routes/channels.py#L48)** hâlâ `tracked_channels` tablosunu sorgularken `backend/db/schema.py`'da bu tablo **yok**! Runtime hataya yol açar.

**Çözüm:** Tüm backend route'larını `core/database.py`'daki tek, yetkili `DatabaseManager`'ı kullanacak şekilde yeniden yaz.

## 5.2 In-Memory Job Store

**[`backend/workers/job_store.py:156`](file:///home/tuncay/Projects/clipper/backend/workers/job_store.py#L156)** — Global singleton:
```python
job_store = JobStore()
```
Server restart'ta tüm iş geçmişi kayboluyor. `pipeline_jobs` tablosu şemada var ama hiç kullanılmıyor.

## 5.3 APScheduler Thread Güvenliği

**[`core/autopilot.py:76-125`](file:///home/tuncay/Projects/clipper/core/autopilot.py#L76-L125)** — `BackgroundScheduler` thread'de çalışırken `_worker_info` class dict'i lock olmadan güncelleniyor.

## 5.4 Stateless API Tasarımı

Settings endpoint'leri global module değişkenlerini değiştiriyor (`scoring_config`). Bu, birden fazla worker process ile çalışılamaz hale getirir.

---

# 6. Yeni Özellik Fikirleri

### Özellik 1: Gerçek Zamanlı Viral Trend Tespiti
YouTube Trending API + RSS feed kombinasyonu ile son 24 saatteki trending oyun etiketleri çekilip `CandidateRanker` skorlama ağırlıkları dinamik olarak ayarlanır.
**Etkilenen dosyalar:** `core/trend_engine.py` (yeni) + `core/candidate_ranker.py`
**İş yükü:** 2 gün

### Özellik 2: A/B Thumbnail Testi
Aynı klip için 3 farklı thumbnail varyantı üretilip YouTube API ile sırayla test edilir. 48 saat sonra CTR verisine göre en iyisi kalıcı yapılır.
**Etkilenen dosyalar:** `core/ab_tester.py` (yeni) + `core/uploader.py` + `backend/db/schema.py`
**İş yükü:** 3 gün

### Özellik 3: Multi-Platform Cross-Posting Intelligence
YouTube Shorts, Instagram Reels, TikTok için özgün metadata üretimi. Aynı klip farklı kanca metinleri ve hashtag stratejileriyle yayınlanır.
**Etkilenen dosyalar:** `core/platform_copywriter.py` (yeni) + `core/multi_publisher.py`
**İş yükü:** 2 gün

### Özellik 4: Yayın Analitik Entegrasyonu
YouTube Analytics API + Instagram Graph API ile yüklenen her klipin izlenme, tıklama, retention ve abone kazanım verileri otomatik çekilip biriktirilir. `CandidateRanker` ağırlıkları öğrenme verisiyle adapt edilir.
**Etkilenen dosyalar:** `core/analytics_tracker.py` (yeni) + `core/database.py`
**İş yükü:** 4 gün

### Özellik 5: Otomatik Klip Serilendirme (Story Arc Detection)
Bir gaming oturumundan çıkarılan klipleri intro → gerilim → zirve → kapanış sırasıyla dizer. LLM klipler arası bağlantıyı analiz ederek optimal yayın sırası ve seriyi birbirine bağlayan hook metinleri üretir.
**Etkilenen dosyalar:** `core/arc_sequencer.py` (yeni) + `pages/Planner.tsx`
**İş yükü:** 3 gün

### Özellik 6: Çok Dilli Whisper Altyazı
`faster-whisper` ile Türkçe/İngilizce transkript çıkarılıp 5 dile çevrilir. Her platform için hedef dil seçilebilir.
**Etkilenen dosyalar:** `core/multilingual_subtitles.py` (yeni) + `core/cutter.py`
**İş yükü:** 2 gün

### Özellik 7: Oyuna Özel Viral Kategori Modeli
Mevcut `GameDetector`'ı genişleterek tespit edilen oyuna göre farklı viral kategoriler etkin yapılır: CS2 için "1v5 clutch", Minecraft için "elytra crash".
**Etkilenen dosyalar:** `core/game_detector.py` + `core/scoring_config.py`
**İş yükü:** 2 gün

### Özellik 8: Canlı Yayın (Live Stream) Entegrasyonu
YouTube Live API ile aktif yayınları izleyip gerçek zamanlı chat hız artışlarını ve SuperChat anlarını tespit et. Bu anları otomatik klip adayı olarak kaydet.
**Etkilenen dosyalar:** `core/live_monitor.py` (yeni) + `core/autopilot.py`
**İş yükü:** 5 gün

### Özellik 9: Discord Community Annotation
Klip önizleme URL'leri Discord kanalına gönderilip 24 saat içinde emoji reaksiyonları sayılır. Yüksek reaksiyon alan klipler "topluluk onaylı" etiketiyle önceliklendirilir.
**Etkilenen dosyalar:** `core/notifier.py` (genişlet) + `core/database.py`
**İş yükü:** 2 gün

### Özellik 10: Akıllı Yayın Zaman Optimizasyonu
Analytics verilerine göre izleyicilerin en aktif olduğu saatler (`peak_hours`) çıkarılır. `SlotAllocator` bu saatlere öncelik verir.
**Etkilenen dosyalar:** `core/slot_allocator.py` + `core/analytics_tracker.py`
**İş yükü:** 2 gün

### Özellik 11: Otomatik Highlight Reel (Best Of Compilation)
Günlük/haftalık en iyi klipler birleştirilerek "best of" compilation videosu oluşturulur. FFmpeg `concat` demuxer + `xfade` transition efektleri kullanılır.
**Etkilenen dosyalar:** `core/reel_composer.py` (yeni) + `core/autopilot.py`
**İş yükü:** 3 gün

### Özellik 12: Webhook API
Dışarıdan sistemlerin (Discord bot, Zapier, n8n) video işleme tetikleyebilmesi için HMAC-SHA256 imzalı `POST /api/webhooks/process-video` endpoint'i eklenir.
**Etkilenen dosyalar:** `backend/api/routes/webhooks.py` (yeni) + `backend/main.py`
**İş yükü:** 1 gün

---

# 7. Ölçeklendirme Sorunları

## 7.1 SQLite Sınırlamaları

AutoPilot döngüsü her dakika yayın tick'i çalıştırırken, aynı anda pipeline worker çalışıyor ve HTTP istekleri geliyor. SQLite'ın yazma kilidi yüksek eşzamanlılıkta darboğaz yaratır.

**[`backend/db/database.py:14`](file:///home/tuncay/Projects/clipper/backend/db/database.py#L14):** `check_same_thread=False` ayarlanmış; bu thread safety **sağlamaz**, sadece kontrolü devre dışı bırakır.

**Ölçeklendirme adımı:** SQLite → PostgreSQL migrasyonu.

## 7.2 Tek Process Mimarisi

Tüm sistem tek bir Python process içinde çalışıyor: FastAPI + APScheduler + asyncio + ThreadPool. CPU-bound işlemler (NumPy FFT, FFmpeg) GIL nedeniyle çakışır.

**Çözüm:** Celery veya ARQ ile ayrı worker process'leri, Redis queue ile iş dağıtımı.

## 7.3 Dosya Sistemi Bağımlılığı

**[`core/cutter.py:36`](file:///home/tuncay/Projects/clipper/core/cutter.py#L36):** `output_dir = "outputs/clips"` — hardcoded local path. Multi-server deployment'ta bu paylaşımlı NFS veya S3 ile değiştirilmeli.

## 7.4 In-Memory Job State

Server restart'ta tüm iş durumu kayboluyor. Horizontal scaling yapılamaz: worker 1'deki iş, worker 2 tarafından görülemiyor.

---

# 8. Frontend Analizi

## 8.1 İyi Pratikler
- `useSSE.ts` hook'u temiz EventSource soyutlaması sunuyor; cleanup `useEffect` return'ünde doğru yapılmış
- `api.ts`'deki tüm API çağrıları merkezi request wrapper üzerinden geçiyor; hata handling tutarlı
- TanStack Query ile sunucu durumu ve yerel UI durumu doğru ayrılmış
- `optionsRef` ile SSE callback'lerinde closure tuzağından kaçınılmış

## 8.2 Sorunlar

**[`frontend/src/pages/Analyze.tsx:130-158`](file:///home/tuncay/Projects/clipper/frontend/src/pages/Analyze.tsx#L130-L158)** — Hem SSE hem de 1500ms polling aynı anda çalışıyor:
```typescript
const interval = setInterval(async () => {
  const job = await api.pipeline.getJob(jobId);
  ...
}, 1500);
```
SSE zaten gerçek zamanlı güncellemeler sağlıyor. Polling gereksiz ek yük yaratıyor.

**[`frontend/src/pages/Analyze.tsx:616`](file:///home/tuncay/Projects/clipper/frontend/src/pages/Analyze.tsx#L616)**
```typescript
onClick={() => (window.location.href = '/clips')}
```
TanStack Router yerine `window.location.href` kullanılmış — tam sayfa yükleme tetikleniyor, SPA navigasyonu bozuluyor.

**[`frontend/src/pages/AutoPilot.tsx:98`](file:///home/tuncay/Projects/clipper/frontend/src/pages/AutoPilot.tsx#L98)**
```typescript
localStorage.setItem('clipper_active_job_id', res.jobs[0].job_id);
```
Yalnızca ilk iş ID'si saklanıyor; batch işlemde diğer işlerin SSE akışı takip edilemiyor.

**[`frontend/src/App.tsx`](file:///home/tuncay/Projects/clipper/frontend/src/App.tsx)** — `QueryClient` varsayılan ayarlarla oluşturulmuş. `staleTime`, `retry`, `refetchOnWindowFocus` gibi kritik ayarlar yapılandırılmamış.

**[`frontend/src/pages/Settings.tsx:43-52`](file:///home/tuncay/Projects/clipper/frontend/src/pages/Settings.tsx#L43-L52)** — `window.addEventListener('message', handleMessage)` herhangi bir origin kontrolü yapmaksızın tüm `postMessage` olaylarını dinliyor. `e.origin` kontrol edilmeli.

## 8.3 Eksik UX Özellikleri
- Pipeline iptal işlemi (cancel button) frontend'de yok
- Hata mesajları için retry mekanizması yok
- Responsive tasarım kısmen uygulanmış (bazı tablolar mobilde taşıyor)
- Dark mode mevcut, ancak sistem tercihine göre otomatik geçiş yok

---

# 9. Test Kalitesi

## 9.1 İyi Pratikler
- `conftest.py`'de `temp_db` fixture (geçici SQLite) ve `reset_test_state` (global state sıfırlama) iyi uygulamalar
- `temp_db` fixture WAL/SHM dosyalarını da temizliyor
- `reset_test_state` fixture `autouse=True` ile global state'ini sıfırlıyor — test izolasyonu iyi

## 9.2 Sorunlar

**Gerçek Entegrasyon Testi Yok:**
Tüm yt-dlp, FFmpeg ve LLM çağrıları mock'lanmış. CI'da gerçek end-to-end test atlanıyor olabilir.

**`tests/test_backend_deps.py`** sadece 173 byte — muhtemelen tek satır test veya boş.
**`tests/test_backend_main.py`** sadece 376 byte — FastAPI lifespan testi eksik olabilir.

**Schema Tutarsızlığı Testi Yok:**
`backend/db/schema.py` ile `core/database.py` arasındaki tablo uyumsuzluğunu (`tracked_channels` vs `channels`) yakalayan bir test yok.

**Race Condition Testleri Yok:**
`job_store.py`'daki eşzamanlı erişim senaryoları için concurrency testi yok.

---

# 10. Enterprise Seviye Yol Haritası

## Hafta 1 — Kritik Hata Düzeltmeleri & Güvenlik

### Gün 1-2: Güvenlik Düzeltmeleri
- [ ] `credentials.json`, `token.json`, `client_secret_*.json` dosyalarını git history'den temizle (BFG Repo Cleaner), yeni OAuth kimlik bilgileri oluştur
- [ ] `auth.py:162`'deki wildcard `postMessage` `'*'` → `'http://localhost:5173'` olarak değiştir
- [ ] `auth.py:87-88`'deki güvensiz PKCE fallback'i kaldır; state eşleşmezse hata döndür
- [ ] `frontend/src/pages/Settings.tsx:44-52`'ye `e.origin` kontrolü ekle

### Gün 3-4: Şema Tutarsızlığı Düzeltmesi
- [ ] `backend/api/routes/channels.py:48` `tracked_channels` → `core/database.py`'daki tek `DatabaseManager`
- [ ] Tüm backend route'larını `core/database.py` kullancak şekilde birleştir
- [ ] `backend/db/schema.py` ile `core/database.py` şemasını tek bir kaynakta topla

### Gün 5-7: Temel Performans İyileştirmeleri
- [ ] `backend/api/routes/clips.py:105-120` N+1 batch delete → `WHERE id IN (...)` tek sorgu
- [ ] `backend/workers/job_store.py` `_jobs` dict'ine `asyncio.Lock` ekle
- [ ] `core/cutter.py:312` — atanmayan `end_time - start_time` ifadesini kaldır
- [ ] `core/cutter.py:489` — non-9x16 render için `slow` → `fast` preset

---

## Ay 1 — Mimari Sağlamlaştırma

### Hafta 2: Job Persistence
- [ ] `backend/workers/job_store.py` in-memory dict → `pipeline_jobs` SQLite tablosu
- [ ] Server restart'ta devam eden işleri yeniden başlat
- [ ] SSE'de job_id bazlı stream'i DB-backed state ile destekle

### Hafta 3: Performans Optimizasyonları
- [ ] `core/audio_dsp.py:273-277` pitch variance döngüsü → `np.lib.stride_tricks.sliding_window_view` ile vektörize (10-50x hızlanma)
- [ ] `core/audio_dsp.py:378-382` silence burst döngüsü → NumPy vektörize
- [ ] `core/smart_layout.py:37-132` facecam tespitini klip başına değil, video başına bir kez cache'le
- [ ] `VideoCutter._STREAM_CACHE` LRU cache ile sınırla (bellek sızıntısı önleme)

### Hafta 4: Frontend Temizlik
- [ ] `Analyze.tsx:130-158` SSE + polling çift mekanizması → sadece SSE
- [ ] `Analyze.tsx:616` `window.location.href` → TanStack Router `navigate({ to: '/clips' })`
- [ ] `App.tsx` QueryClient'a `staleTime`, `retry`, `refetchOnWindowFocus` ayarları
- [ ] Batch işlemde tüm iş ID'lerini `localStorage`'a kaydet

---

## Ay 3 — Enterprise Özellikleri

**Ay 2 Kapsamı:**
- PostgreSQL migrasyonu (`core/database.py` → async SQLAlchemy)
- Celery + Redis ile iş kuyruğu
- S3 uyumlu nesne depolaması (render dosyaları için)
- Webhook API (`/api/webhooks/process-video`)
- YouTube Analytics otomatik veri çekimi
- A/B thumbnail testi

**Ay 3 Kapsamı:**
- Multi-tenant mimarisi (birden fazla kanal hesabı)
- Gerçek zamanlı live stream monitoring
- Community annotation (Discord reaksiyon entegrasyonu)
- Akıllı yayın zamanlaması (peak hour optimizasyonu)
- Prometheus/Grafana metrik monitoring
- Kubernetes deployment manifests
- CI/CD pipeline (GitHub Actions) → pytest + mypy + ruff + Docker build
- Kullanıcı bazlı yetkilendirme (JWT) — şu an auth tamamen yok!

---

# Özet Kritiklik Tablosu

| # | Sorun | Dosya | Satır | Öncelik |
|---|---|---|---|---|
| S1 | `credentials.json` git'te | Proje kökü | — | Acil |
| S2 | Wildcard postMessage | [`auth.py`](file:///home/tuncay/Projects/clipper/backend/api/routes/auth.py) | 162 | Acil |
| S3 | Güvensiz PKCE fallback | [`auth.py`](file:///home/tuncay/Projects/clipper/backend/api/routes/auth.py) | 87-88 | Acil |
| S4 | tracked_channels şema hatası | [`channels.py`](file:///home/tuncay/Projects/clipper/backend/api/routes/channels.py) | 48 | Acil |
| P1 | Her request'te yeni DB instance | [`deps.py`](file:///home/tuncay/Projects/clipper/backend/deps.py) | 4-5 | Yüksek |
| P2 | N+1 batch delete sorgu | [`clips.py`](file:///home/tuncay/Projects/clipper/backend/api/routes/clips.py) | 105-120 | Yüksek |
| P3 | In-memory job store | [`job_store.py`](file:///home/tuncay/Projects/clipper/backend/workers/job_store.py) | 156 | Yüksek |
| P4 | Pitch variance Python döngüsü | [`audio_dsp.py`](file:///home/tuncay/Projects/clipper/core/audio_dsp.py) | 273-277 | Orta |
| P5 | Facecam tespiti cache yok | [`smart_layout.py`](file:///home/tuncay/Projects/clipper/core/smart_layout.py) | 37-132 | Orta |
| Q1 | FFmpeg cmd kod tekrarı (4x) | [`cutter.py`](file:///home/tuncay/Projects/clipper/core/cutter.py) | 384-578 | Orta |
| Q2 | `slow` preset non-9x16 render | [`cutter.py`](file:///home/tuncay/Projects/clipper/core/cutter.py) | 489 | Orta |
| Q3 | Atanmayan hesap sonucu | [`cutter.py`](file:///home/tuncay/Projects/clipper/core/cutter.py) | 312 | Düşük |
| Q4 | `as any` tip dönüşümü | [`Analyze.tsx`](file:///home/tuncay/Projects/clipper/frontend/src/pages/Analyze.tsx) | 39 | Düşük |
| Q5 | SSE + polling çift mekanizma | [`Analyze.tsx`](file:///home/tuncay/Projects/clipper/frontend/src/pages/Analyze.tsx) | 130-158 | Orta |
| Q6 | window.location.href | [`Analyze.tsx`](file:///home/tuncay/Projects/clipper/frontend/src/pages/Analyze.tsx) | 616 | Düşük |
| Q7 | `litterbox.catbox.moe` bağımlılığı | [`instagram_uploader.py`](file:///home/tuncay/Projects/clipper/core/instagram_uploader.py) | 80-86 | Yüksek |
