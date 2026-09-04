"""
core/scoring_config.py — Viral Skorlama Sistemi Konfigürasyonu

Bu dosya llm_engine.py'daki skora ait tüm ayarlanabilir parametreleri tek yerde tutar.
Ağırlıklar ve eşikler sezgisel / uzman tahminine dayalıdır — henüz istatistiksel olarak
doğrulanmamıştır. Referans-set kalibrasyon sonuçlarına göre güncellenmesi önerilir.

# Ağırlıkları Değiştirme Rehberi
# --------------------------------
# Aşağıdaki ağırlıklar toplamı 100'e eşit olmalıdır.
# Daha dramatik, ani anlar istiyorsan HOOK_STRENGTH_WEIGHT ve EMOTION_WEIGHT'i artır.
# Daha "anlamlı" klip istiyorsan STORY_COMPLETENESS_WEIGHT'i artır.
# Yeni sinyal altyapısı (pitch, frame-diff) olgunlaştıkça SIGNAL_VALIDATION_WEIGHT artır.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# PROMPT AĞIRLIKLARI (toplamı = 100)
# NOT: Bu değerler henüz deneysel / sezgiseldir. Referans set kalibrasyon
# sonuçlarıyla karşılaştırılarak ayarlanması önerilir.
# ---------------------------------------------------------------------------
HOOK_STRENGTH_WEIGHT: int = 35        # İlk 3 saniyede izleyiciyi durdurma gücü
EMOTION_WEIGHT: int = 30              # Duygu/kategori şiddeti (FAIL/FUNNY, CLUTCH vs.)
STORY_COMPLETENESS_WEIGHT: int = 20   # Hikaye bütünlüğü (bağlam, giriş-gelişme-sonuç)
SIGNAL_VALIDATION_WEIGHT: int = 15    # Sinyal doğrulama (ses, pitch, frame-diff uyumu)

# ---------------------------------------------------------------------------
# KATEGORİ TAKSONOMİSİ
# ---------------------------------------------------------------------------
# MUNDANE/NONE: LLM zorla kategori atamasını önlemek için fallback kategori.
# Bu kategoriye düşen adaylar otomatik düşük bant olarak işaretlenir.
CATEGORIES = [
    "CLUTCH",       # Üstün oynanış / geri dönüş anları
    "FAIL/FUNNY",   # Eğlenceli başarısızlık, ironi, kahkaha
    "RAGE/REACTION", # Panik, sinirlenme, coşkulu reaksiyon
    "JUMPSCARE",    # Ani korku / şok anı
    "EPIC_MOMENT",  # Destansı başarı, teamwork, zafer
    "STORY",        # Anlatı bütünlüğü yüksek klip
    "MUNDANE",      # Sıradan/hiçbiri — viral potansiyeli düşük, fallback
]

# MUNDANE kategorisine düşen kliplerin skoru bu üst sınırla kırpılır
MUNDANE_SCORE_CAP: int = 30

# ---------------------------------------------------------------------------
# BANT SİSTEMİ (0-100 → 4 bant)
# ---------------------------------------------------------------------------
SCORE_BANDS = [
    {"label": "Yüksek",       "min": 75, "max": 100},
    {"label": "Orta-Yüksek",  "min": 55, "max": 74},
    {"label": "Orta",         "min": 35, "max": 54},
    {"label": "Düşük",        "min": 0,  "max": 34},
]

# Bant etiketleme aktif mi?  (madde 1 varyans testinden önce kapalı)
BAND_LABELS_ENABLED: bool = True

# ---------------------------------------------------------------------------
# ENSEMBLE / MEDYAN SKORLAMA
# ---------------------------------------------------------------------------
# Aynı adayı kaç kez skorlatacak?  1 = mevcut tekil davranış.
# Yüksek değer daha kararlı sonuç verir ama maliyet/gecikme artar.
ENSEMBLE_RUNS: int = 1

# ---------------------------------------------------------------------------
# TUTARLILIK TESTİ
# ---------------------------------------------------------------------------
# score_consistency_test() içinde kaç kez tekrar çalıştırılacak?
CONSISTENCY_TEST_RUNS: int = 3
