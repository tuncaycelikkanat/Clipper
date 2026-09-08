# Clipper — Düzeltme & İyileştirme Yol Haritası

Mevcut puan: **6.6 / 10** → Hedef: **9.2 / 10**

Her görev; etkilenen dosya, tahmini süre ve hangi puanı ne kadar artırdığını içerir.

---

## Faz 0 — Güvenlik Yangını (Gün 1) 
> Güvenlik: 3.5 → 8.5

Bu faz başka hiçbir şeyden önce yapılmalı. Tek gün, sıfır tartışma.

### G0-1: OAuth kimlik bilgilerini git'ten temizle ve revoke et
**Dosyalar:** Proje kökü (`credentials.json`, `token.json`, `client_secret_*.json`)

```bash
# 1. Google Cloud Console'dan mevcut client'ı revoke et
# 2. Yeni OAuth client oluştur, yeni credentials.json indir
# 3. Git geçmişinden temizle
brew install bfg  # veya apt install bfg
bfg --delete-files credentials.json
bfg --delete-files token.json
bfg --delete-files "client_secret_*.json"
git reflog expire --expire=now --all && git gc --prune=now --aggressive
git push --force
# 4. .gitignore'a ekle
echo "credentials.json\ntoken.json\nclient_secret_*.json\n.env" >> .gitignore
```

### G0-2: Wildcard postMessage düzelt
**Dosya:** [`backend/api/routes/auth.py:162`](file:///home/tuncay/Projects/clipper/backend/api/routes/auth.py#L162)

```python
# ÖNCE
window.opener.postMessage({ type: 'YOUTUBE_AUTH_SUCCESS' }, '*')

# SONRA
window.opener.postMessage({ type: 'YOUTUBE_AUTH_SUCCESS' }, 'http://localhost:5173')
```

### G0-3: Güvensiz PKCE fallback kaldır
**Dosya:** [`backend/api/routes/auth.py:87-88`](file:///home/tuncay/Projects/clipper/backend/api/routes/auth.py#L87-L88)

```python
# ÖNCE
if state not in pkce_store:
    verifier = list(pkce_store.values())[-1]  # Tehlikeli fallback

# SONRA
if state not in pkce_store:
    raise HTTPException(status_code=400, detail="Invalid state parameter")
verifier = pkce_store.pop(state)
```

### G0-4: Settings.tsx postMessage origin kontrolü
**Dosya:** [`frontend/src/pages/Settings.tsx:43-52`](file:///home/tuncay/Projects/clipper/frontend/src/pages/Settings.tsx#L43-L52)

```typescript
// ÖNCE
window.addEventListener('message', handleMessage)

// SONRA
window.addEventListener('message', (e) => {
  if (e.origin !== 'http://localhost:8000') return;
  handleMessage(e);
})
```

### G0-5: Partial LIKE sorgusunu tam eşleşmeye çevir
**Dosya:** [`backend/api/routes/clips.py:221`](file:///home/tuncay/Projects/clipper/backend/api/routes/clips.py#L221)

```python
# ÖNCE
cursor = db.execute("SELECT * FROM clips WHERE id LIKE ?", (f"{video_id}%",))

# SONRA
cursor = db.execute("SELECT * FROM clips WHERE video_id = ?", (video_id,))
```

---

## Faz 1 — Kritik Hata Düzeltmeleri (Gün 2-4)
> Mimari: 6.5 → 8.0 | Kod Kalitesi: 6.0 → 7.5

### G1-1: Şema tutarsızlığını çöz (Runtime crash)
**Dosya:** [`backend/api/routes/channels.py:48`](file:///home/tuncay/Projects/clipper/backend/api/routes/channels.py#L48)

`backend/api/routes/channels.py` `tracked_channels` tablosunu sorgular ama `backend/db/schema.py`'da bu tablo yok; `channels` var. Bu runtime'da patlıyor.

**Çözüm:** Tüm backend route'larını `core/database.py` DatabaseManager'ını kullanacak şekilde güncelle. `backend/db/` klasörünü sadece eski uyumluluk katmanı olarak bırak, yeni kod yazmak için kullanma.

```python
# backend/deps.py — ÖNCE
from backend.db.database import DatabaseManager
def get_db():
    return DatabaseManager()

# backend/deps.py — SONRA
from core.database import DatabaseManager
_db_instance: DatabaseManager | None = None

def get_db() -> DatabaseManager:
    global _db_instance
    if _db_instance is None:
        _db_instance = DatabaseManager()
    return _db_instance
```

Tüm route dosyalarında import düzelt: `from backend.db.database import` → `from core.database import`

### G1-2: N+1 batch delete → tek sorgu
**Dosya:** [`backend/api/routes/clips.py:105-120`](file:///home/tuncay/Projects/clipper/backend/api/routes/clips.py#L105-L120)

```python
# ÖNCE — Her klip için 3 sorgu
for clip_id in clip_ids:
    clip = db.execute("SELECT * FROM clips WHERE id=?", (clip_id,))
    db.execute("DELETE FROM clips WHERE id=?", (clip_id,))
    db.execute("DELETE FROM renders WHERE clip_id=?", (clip_id,))

# SONRA — 2 sorgu toplam
placeholders = ",".join("?" * len(clip_ids))
clips = db.execute(f"SELECT * FROM clips WHERE id IN ({placeholders})", clip_ids)
db.execute(f"DELETE FROM renders WHERE clip_id IN ({placeholders})", clip_ids)
db.execute(f"DELETE FROM clips WHERE id IN ({placeholders})", clip_ids)
```

### G1-3: Ölü kodu temizle
**Dosya:** [`core/cutter.py:312`](file:///home/tuncay/Projects/clipper/core/cutter.py#L312)

```python
# ÖNCE
end_time - start_time  # atanmıyor, sonuç kayboluyor

# SONRA
duration = end_time - start_time
logger.debug(f"Clip duration: {duration:.2f}s")
```

### G1-4: Sessiz exception yutmayı düzelt
**Dosya:** [`core/extractor.py:101`](file:///home/tuncay/Projects/clipper/core/extractor.py#L101)

```python
# ÖNCE
except Exception:
    pass

# SONRA
except Exception as e:
    logger.warning(f"Comment fetch failed for {video_id}: {e}")
    return []
```

Aynı pattern `core/audio_dsp.py:101-108`'de de var — orada da `logger.error(f"Chunk extract failed: {e}")` ekle.

---

## Faz 2 — Performans (Gün 5-10)
> Performans: 5.5 → 9.0

### G2-1: NumPy pitch variance vektörize et
**Dosya:** [`core/audio_dsp.py:273-277`](file:///home/tuncay/Projects/clipper/core/audio_dsp.py#L273-L277)

```python
# ÖNCE — Saf Python döngüsü (binlerce iterasyon)
for i in range(win_hops, n_hops):
    pitch_var[i] = float(np.var(zcr[i - win_hops : i]))

# SONRA — Tamamen vektörize (10-50x hız artışı)
from numpy.lib.stride_tricks import sliding_window_view
windows = sliding_window_view(zcr, window_shape=win_hops)
pitch_var[win_hops:] = np.var(windows, axis=1)
```

### G2-2: NumPy silence burst vektörize et
**Dosya:** [`core/audio_dsp.py:378-382`](file:///home/tuncay/Projects/clipper/core/audio_dsp.py#L378-L382)

```python
# ÖNCE
for i in range(2, len(rms)):
    pre_min = np.min(rms[max(0, i - 4) : i])

# SONRA
from numpy.lib.stride_tricks import sliding_window_view
padded = np.pad(rms, (4, 0), mode='edge')
pre_min = np.min(sliding_window_view(padded, 4), axis=1)[:len(rms)]
```

### G2-3: FFmpeg preset düzelt
**Dosya:** [`core/cutter.py:489`](file:///home/tuncay/Projects/clipper/core/cutter.py#L489)

```python
# ÖNCE
"-preset", "slow"

# SONRA — 2-4x encoding hızlanması, görsel fark yok
"-preset", "fast"
```

### G2-4: Facecam tespitini video başına cache'le
**Dosya:** [`core/smart_layout.py:37`](file:///home/tuncay/Projects/clipper/core/smart_layout.py#L37)

```python
# SmartLayoutEngine sınıfına ekle
_facecam_cache: dict[str, dict] = {}

def detect_facecam(self, video_path: str, sample_time_sec: float = 3.0) -> dict:
    if video_path in self._facecam_cache:
        logger.debug(f"Facecam cache hit: {video_path}")
        return self._facecam_cache[video_path]
    
    result = self._detect_facecam_uncached(video_path, sample_time_sec)
    self._facecam_cache[video_path] = result
    return result
```

Mevcut metodun gövdesini `_detect_facecam_uncached` olarak yeniden adlandır.

### G2-5: _STREAM_CACHE bellek sızıntısını düzelt
**Dosya:** [`core/cutter.py:127-134`](file:///home/tuncay/Projects/clipper/core/cutter.py#L127-L134)

```python
# ÖNCE — Sınırsız büyüyen dict
_STREAM_CACHE: dict[str, str] = {}

# SONRA — LRU cache ile sınırlı
from functools import lru_cache

@lru_cache(maxsize=32)
def _get_stream_url(video_id: str) -> str:
    # mevcut yt-dlp çağrısı
    ...
```

### G2-6: LLM model listesini temizle
**Dosya:** [`core/llm_engine.py:283-288`](file:///home/tuncay/Projects/clipper/core/llm_engine.py#L283-L288)

`MODELS_TO_TRY` listesinde geçersiz model adlarını kaldır. Sadece çalıştığı doğrulanan modelleri bırak. Her başarısız deneme gereksiz network round-trip ve gecikme yaratıyor.

---

## Faz 3 — Kod Kalitesi & Type Safety (Gün 11-15)
> Kod Kalitesi: 6.0 → 8.5 | Güvenlik: 8.5 → 9.0

### G3-1: FFmpeg komut tekrarını birleştir
**Dosya:** [`core/cutter.py:384-578`](file:///home/tuncay/Projects/clipper/core/cutter.py#L384-L578)

Şu an 4 kez tekrarlanan ~30 satırlık FFmpeg argüman listesini tek fabrika fonksiyonuna topla:

```python
def _build_ffmpeg_cmd(
    input_path: str,
    output_path: str,
    has_cam: bool,
    cam_box: dict | None,
    format: str,
    subtitle_path: str | None,
    hook_text: str | None,
    lufs_target: float = -14.0,
) -> list[str]:
    """Tüm format ve facecam kombinasyonları için tek FFmpeg komut üreticisi."""
    cmd = ["ffmpeg", "-y", "-i", input_path]
    
    if has_cam and cam_box:
        # facecam filtre zinciri
        ...
    else:
        # blur/black filtre zinciri
        ...
    
    if subtitle_path:
        cmd += ["-vf", f"subtitles={subtitle_path}"]
    
    cmd += ["-preset", "fast", "-crf", "23", output_path]
    return cmd
```

### G3-2: job_store race condition düzelt
**Dosya:** [`backend/workers/job_store.py:69-70`](file:///home/tuncay/Projects/clipper/backend/workers/job_store.py#L69-L70)

```python
import asyncio
from threading import Lock

class JobStore:
    def __init__(self):
        self._jobs: dict[str, JobState] = {}
        self._lock = Lock()  # Thread-safe erişim için

    def get_job(self, job_id: str) -> JobState | None:
        with self._lock:
            return self._jobs.get(job_id)

    def set_job(self, job_id: str, state: JobState) -> None:
        with self._lock:
            self._jobs[job_id] = state
```

### G3-3: scoring_config global mutation düzelt
**Dosya:** [`backend/api/routes/settings.py:136-152`](file:///home/tuncay/Projects/clipper/backend/api/routes/settings.py#L136-L152)

Scoring konfigürasyonunu global module değişkeni yerine DB'de sakla:

```python
# core/database.py'ye ekle
def get_scoring_config(self) -> dict:
    row = self.execute_one("SELECT config_json FROM app_config WHERE key='scoring'")
    return json.loads(row["config_json"]) if row else DEFAULT_SCORING

def set_scoring_config(self, config: dict) -> None:
    self.execute(
        "INSERT OR REPLACE INTO app_config (key, config_json) VALUES ('scoring', ?)",
        (json.dumps(config),)
    )
```

### G3-4: Analyze.tsx tip güvenliği
**Dosya:** [`frontend/src/pages/Analyze.tsx:39`](file:///home/tuncay/Projects/clipper/frontend/src/pages/Analyze.tsx#L39)

```typescript
// ÖNCE
const [url, setUrl] = useState((search as any)?.url || '');

// SONRA — TanStack Router tip güvenli search params
import { Route } from './Analyze.route'
const { url: initialUrl } = Route.useSearch()
const [url, setUrl] = useState(initialUrl ?? '')
```

### G3-5: Analyze.tsx SPA navigasyonu düzelt
**Dosya:** [`frontend/src/pages/Analyze.tsx:616`](file:///home/tuncay/Projects/clipper/frontend/src/pages/Analyze.tsx#L616)

```typescript
// ÖNCE — Tam sayfa yenileme
onClick={() => (window.location.href = '/clips')}

// SONRA — SPA navigasyonu
import { useNavigate } from '@tanstack/react-router'
const navigate = useNavigate()
onClick={() => navigate({ to: '/clips' })}
```

### G3-6: SSE + polling çift mekanizmasını kaldır
**Dosya:** [`frontend/src/pages/Analyze.tsx:130-158`](file:///home/tuncay/Projects/clipper/frontend/src/pages/Analyze.tsx#L130-L158)

```typescript
// ÖNCE — SSE + setInterval aynı anda çalışıyor
useEffect(() => {
  const interval = setInterval(async () => { ... }, 1500);  // Gereksiz!
  return () => clearInterval(interval);
}, [jobId]);

// SONRA — Sadece SSE yeterli, polling tamamen kaldır
// useSSE hook zaten tüm güncellemeleri push ediyor
```

### G3-7: litterbox.catbox.moe bağımlılığını kaldır
**Dosya:** [`core/instagram_uploader.py:80-86`](file:///home/tuncay/Projects/clipper/core/instagram_uploader.py#L80-L86)

Anonim geçici hosting yerine kendi FastAPI sunucunda servis et:

```python
# Yeni endpoint: backend/api/routes/media.py
@router.get("/api/media/thumbnail/{clip_id}")
async def serve_thumbnail(clip_id: str):
    path = db.get_thumbnail_path(clip_id)
    return FileResponse(path)

# instagram_uploader.py — thumbnail URL'i lokal sunucu URL'iyle değiştir
thumbnail_url = f"http://YOUR_PUBLIC_URL/api/media/thumbnail/{clip_id}"
```

> [!IMPORTANT]
> Instagram'ın erişebilmesi için bu URL'in public olması gerekir. Local development için ngrok kullanılabilir.

---

## Faz 4 — Mimari Sağlamlaştırma (Gün 16-25)
> Mimari: 8.0 → 9.5 | Ölçeklenebilirlik: 4.0 → 7.0

### G4-1: Job state'i DB'ye taşı
**Dosyalar:** [`backend/workers/job_store.py`](file:///home/tuncay/Projects/clipper/backend/workers/job_store.py), [`backend/db/schema.py`](file:///home/tuncay/Projects/clipper/backend/db/schema.py)

Şemada `pipeline_jobs` tablosu var ama kullanılmıyor. Etkin hale getir:

```python
# core/database.py'ye ekle
def create_job(self, job_id: str, video_url: str) -> None:
    self.execute(
        "INSERT INTO pipeline_jobs (id, video_url, status, created_at) VALUES (?, ?, 'pending', ?)",
        (job_id, video_url, datetime.utcnow().isoformat())
    )

def update_job_status(self, job_id: str, status: str, progress: dict) -> None:
    self.execute(
        "UPDATE pipeline_jobs SET status=?, progress_json=?, updated_at=? WHERE id=?",
        (status, json.dumps(progress), datetime.utcnow().isoformat(), job_id)
    )
```

`JobStore` singleton'ı bu metotları çağıracak şekilde güncelle. Server restart'ta tüm iş geçmişi korunur.

### G4-2: Connection pooling ekle
**Dosya:** [`backend/deps.py`](file:///home/tuncay/Projects/clipper/backend/deps.py)

```python
# Singleton + WAL mode ile hafif connection pooling
from core.database import DatabaseManager
import threading

_local = threading.local()

def get_db() -> DatabaseManager:
    if not hasattr(_local, 'db') or _local.db is None:
        _local.db = DatabaseManager()
        _local.db.execute("PRAGMA journal_mode=WAL")
        _local.db.execute("PRAGMA busy_timeout=5000")
    return _local.db
```

WAL mode ile okuma-yazma eşzamanlılığı ciddi oranda artar.

### G4-3: autopilot _worker_info thread safety
**Dosya:** [`core/autopilot.py:29`](file:///home/tuncay/Projects/clipper/core/autopilot.py#L29)

```python
import threading

class AutoPilot:
    _worker_info: dict[str, Any] = {}
    _lock = threading.Lock()

    @classmethod
    def get_status(cls) -> dict:
        with cls._lock:
            return dict(cls._worker_info)

    @classmethod
    def _set_status(cls, **kwargs) -> None:
        with cls._lock:
            cls._worker_info.update(kwargs)
```

### G4-4: QueryClient varsayılanlarını yapılandır
**Dosya:** [`frontend/src/App.tsx`](file:///home/tuncay/Projects/clipper/frontend/src/App.tsx)

```typescript
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,          // 30sn önbellekte tut
      retry: 2,                   // Başarısızda 2 kez dene
      refetchOnWindowFocus: false, // Tab değişiminde gereksiz yenileme yok
    },
  },
})
```

### G4-5: AutoPilot batch job tracking düzelt
**Dosya:** [`frontend/src/pages/AutoPilot.tsx:98`](file:///home/tuncay/Projects/clipper/frontend/src/pages/AutoPilot.tsx#L98)

```typescript
// ÖNCE — Sadece ilk job ID saklanıyor
localStorage.setItem('clipper_active_job_id', res.jobs[0].job_id);

// SONRA — Tüm job ID'leri sakla
const jobIds = res.jobs.map((j: Job) => j.job_id);
localStorage.setItem('clipper_active_job_ids', JSON.stringify(jobIds));
```

---

## Faz 5 — Yeni Özellikler (Gün 26-45)
> Özellik Zenginliği: 9.0 → 10.0 | Geliştirici DX: 8.0 → 9.5

### G5-1: Webhook API
**Yeni dosya:** `backend/api/routes/webhooks.py`

```python
import hmac, hashlib

@router.post("/api/webhooks/process-video")
async def webhook_process(request: Request, x_signature: str = Header(...)):
    body = await request.body()
    secret = os.environ["WEBHOOK_SECRET"]
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(x_signature, expected):
        raise HTTPException(status_code=401, detail="Invalid signature")
    data = await request.json()
    # pipeline'ı tetikle
    job_id = await run_pipeline_async(data["url"], data.get("clips", 3))
    return {"job_id": job_id}
```

### G5-2: Pipeline iptal butonu
**Frontend:** `pages/Analyze.tsx` + **Backend:** `backend/api/routes/pipeline.py`

```python
# Backend
@router.post("/api/pipeline/{job_id}/cancel")
async def cancel_job(job_id: str):
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(404)
    job.cancelled = True
    return {"status": "cancelling"}
```

```typescript
// Frontend — Analyze.tsx'e ekle
<button onClick={() => api.pipeline.cancel(jobId)}>
  İşlemi Durdur
</button>
```

### G5-3: YouTube Analytics entegrasyonu
**Yeni dosya:** `core/analytics_tracker.py`

```python
class AnalyticsTracker:
    def fetch_video_stats(self, video_id: str) -> dict:
        """YouTube Analytics API'den izlenme, CTR, retention çek."""
        ...
    
    def update_clip_performance(self, clip_id: str) -> None:
        stats = self.fetch_video_stats(clip_id)
        db.execute(
            "UPDATE clips SET views=?, ctr=?, avg_view_duration=? WHERE youtube_video_id=?",
            (stats["views"], stats["ctr"], stats["avg_duration"], clip_id)
        )
```

APScheduler'a günde bir kez çalışacak job olarak ekle.

### G5-4: A/B Thumbnail Testi
**Yeni dosya:** `core/ab_tester.py`

Aynı klip için 3 farklı thumbnail üret (farklı frame + metin rengi). YouTube API'ye yükle. 48 saat sonra analytics ile en iyi CTR'a sahip olanı kalıcı yap.

### G5-5: Highlight Reel (Best Of)
**Yeni dosya:** `core/reel_composer.py`

Haftalık en yüksek `viral_score`'a sahip 5-7 klibi FFmpeg `concat` ile birleştir. `xfade` geçiş efektleri ekle. APScheduler'a her Pazar 10:00'da çalışacak job olarak ekle.

---

## Faz 6 — Ölçeklenebilirlik (Gün 46-60)
> Ölçeklenebilirlik: 4.0 → 8.5

### G6-1: SQLite WAL + Busy Timeout (Hızlı kazanım)
Tüm bağlantılarda zaten Faz 4'te eklendi. Bu kısmı orada yaptıysan geç.

### G6-2: SQLite → PostgreSQL migrasyonu
**Dosya:** `core/database.py`

```python
# requirements.txt'e ekle
asyncpg==0.29.0
sqlalchemy[asyncio]==2.0.0

# core/database.py — DatabaseManager'ı SQLAlchemy async engine üzerine taşı
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

engine = create_async_engine(
    os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///clipper.db"),
    pool_size=10,
    max_overflow=20,
)
```

`DATABASE_URL=postgresql+asyncpg://user:pass@localhost/clipper` ile Postgres'a geç.

### G6-3: Celery + Redis iş kuyruğu
**Yeni dosyalar:** `celery_app.py`, `workers/tasks.py`

```python
# celery_app.py
from celery import Celery
app = Celery('clipper', broker='redis://localhost:6379/0')

# workers/tasks.py
@app.task(bind=True, max_retries=3)
def process_video_task(self, video_url: str, options: dict):
    try:
        pipeline = ClipperPipeline(**options)
        return pipeline.execute(video_url)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)
```

### G6-4: S3 uyumlu nesne depolama
**Dosya:** `core/cutter.py:36`

```python
# ÖNCE — Hardcoded local path
output_dir = "outputs/clips"

# SONRA — Konfigüre edilebilir
import os
OUTPUT_BACKEND = os.environ.get("OUTPUT_BACKEND", "local")  # "local" | "s3"
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "outputs/clips")
S3_BUCKET = os.environ.get("S3_BUCKET", "")
```

`core/storage.py` ile `LocalStorage` ve `S3Storage` sınıfları oluştur. `cutter.py` soyut `Storage` arayüzüne yazar.

---

## Faz 7 — Test & Dokümantasyon (Paralel, sürekli)
> Test: 7.5 → 9.5 | Dokümantasyon: 7.0 → 9.0

### G7-1: Şema tutarsızlığı testi
**Yeni dosya:** `tests/test_schema_consistency.py`

```python
def test_backend_routes_use_core_db():
    """backend/ route'larının core/database.py'yi kullandığını doğrula."""
    from backend.deps import get_db
    from core.database import DatabaseManager
    db = get_db()
    assert isinstance(db, DatabaseManager)

def test_tracked_channels_table_exists(temp_db):
    """tracked_channels tablosunun DatabaseManager şemasında var olduğunu doğrula."""
    result = temp_db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r["name"] for r in result]
    assert "tracked_channels" in tables
```

### G7-2: Race condition testi
**Yeni dosya:** `tests/test_job_store_concurrency.py`

```python
import threading

def test_job_store_concurrent_access():
    store = JobStore()
    errors = []
    
    def writer():
        for i in range(100):
            try:
                store.set_job(f"job-{i}", JobState(...))
            except Exception as e:
                errors.append(e)
    
    threads = [threading.Thread(target=writer) for _ in range(10)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(errors) == 0
```

### G7-3: CI/CD pipeline
**Yeni dosya:** `.github/workflows/ci.yml`

```yaml
name: CI
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: ruff check .
      - run: mypy core/ backend/ --ignore-missing-imports
      - run: PYTHONPATH=. pytest tests/ --cov=core --cov-report=xml
      - uses: codecov/codecov-action@v4
```

### G7-4: API dokümantasyonu otomatikleştir
FastAPI zaten `/docs` ile Swagger UI sunuyor. Her endpoint'e `summary`, `description` ve `response_model` ekle:

```python
# ÖNCE
@router.get("/clips")
async def list_clips(db=Depends(get_db)):
    ...

# SONRA
@router.get("/clips", summary="Tüm klipleri listele", response_model=list[ClipResponse])
async def list_clips(
    db: DatabaseManager = Depends(get_db),
    limit: int = Query(50, description="Sayfa başı maksimum klip sayısı"),
    offset: int = Query(0, description="Başlangıç offseti"),
):
    ...
```

---

## Hedef Puan Tablosu

| Kategori | Şimdi | Faz 0 | Faz 1 | Faz 2 | Faz 3 | Faz 4 | Faz 5 | Faz 6+7 |
|---|---|---|---|---|---|---|---|---|
| Güvenlik | 3.5 | **8.5** | 8.5 | 8.5 | 9.0 | 9.0 | 9.0 | 9.5 |
| Performans | 5.5 | 5.5 | 5.5 | **9.0** | 9.0 | 9.0 | 9.0 | 9.0 |
| Mimari | 6.5 | 6.5 | **8.0** | 8.0 | 8.5 | **9.5** | 9.5 | 9.5 |
| Kod Kalitesi | 6.0 | 6.0 | 7.0 | 7.0 | **8.5** | 8.5 | 8.5 | 9.0 |
| Test | 7.5 | 7.5 | 7.5 | 7.5 | 7.5 | 7.5 | 7.5 | **9.5** |
| Frontend | 6.5 | 7.0 | 7.0 | 7.0 | **8.5** | 9.0 | 9.0 | 9.0 |
| Özellik | 9.0 | 9.0 | 9.0 | 9.0 | 9.0 | 9.0 | **10.0** | 10.0 |
| Ölçeklenebilirlik | 4.0 | 4.0 | 4.0 | 4.0 | 4.0 | 5.0 | 5.0 | **8.5** |
| Dokümantasyon | 7.0 | 7.0 | 7.0 | 7.0 | 7.0 | 7.0 | 7.0 | **9.0** |
| Geliştirici DX | 8.0 | 8.0 | 8.0 | 8.0 | 8.0 | 8.5 | **9.5** | 9.5 |
| Bağımlılık | 6.0 | 6.0 | 6.0 | 6.0 | **8.0** | 8.0 | 8.0 | 8.5 |
| Fikir | 9.5 | 9.5 | 9.5 | 9.5 | 9.5 | 9.5 | 9.5 | 9.5 |
| **Ortalama** | **6.6** | **7.0** | **7.3** | **7.8** | **8.2** | **8.5** | **8.8** | **9.2** |

---

## Öncelik Sırası (TL;DR)

```
GÜN 1    → Faz 0: Güvenlik (5 görev, ~4 saat)
GÜN 2-4  → Faz 1: Kritik hatalar (5 görev, ~1 gün)
GÜN 5-10 → Faz 2: Performans (6 görev, ~3 gün)
GÜN 11-15→ Faz 3: Kod kalitesi (7 görev, ~3 gün)
GÜN 16-25→ Faz 4: Mimari (5 görev, ~5 gün)
GÜN 26-45→ Faz 5: Yeni özellikler (~15 gün)
GÜN 46-60→ Faz 6+7: Ölçeklendirme + Test (~15 gün)
```
