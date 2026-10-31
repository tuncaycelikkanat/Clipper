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
HOOK_STRENGTH_WEIGHT: int = 35  # İlk 3 saniyede izleyiciyi durdurma gücü
EMOTION_WEIGHT: int = 30  # Duygu/kategori şiddeti (FAIL/FUNNY, CLUTCH vs.)
STORY_COMPLETENESS_WEIGHT: int = 20  # Hikaye bütünlüğü (bağlam, giriş-gelişme-sonuç)
SIGNAL_VALIDATION_WEIGHT: int = 15  # Sinyal doğrulama (ses, pitch, frame-diff uyumu)

# ---------------------------------------------------------------------------
# İZLEYİCİ YORUMU (COMMENT MINING)
# ---------------------------------------------------------------------------
# Yorumlar artık suni +15 puan basmak yerine füzyon sinyali ve LLM bağlamı
# olarak kullanılır. Skor 98'e sabitlenmez.
COMMENT_FEATURE_ENABLED: bool = True

# ---------------------------------------------------------------------------
# KALİTE EŞİĞİ VE SIFIR KLİP POLİTİKASI (STRICT GATEKEEPER)
# ---------------------------------------------------------------------------
# Kalite barajı (0-100). Bu puanın altındaki anlar elenir.
VIRAL_SCORE_THRESHOLD: int = 70
# Zorunlu kota iptali: Eğer videoda kaliteli an yoksa zorla klip üretme (0 klip dön)
ALLOW_ZERO_CLIPS: bool = True
# Test / Audit modu: Kapıdan geçemeyen (elenen) klipleri de [ELENDİ] olarak kaydet ve render et
SAVE_REJECTED_CLIPS: bool = False

# ---------------------------------------------------------------------------
# KATEGORİ TAKSONOMİSİ
# ---------------------------------------------------------------------------
# MUNDANE/NONE: LLM zorla kategori atamasını önlemek için fallback kategori.
# Bu kategoriye düşen adaylar otomatik düşük bant olarak işaretlenir.
CATEGORIES = [
    "CLUTCH",  # Üstün oynanış / geri dönüş anları
    "FAIL/FUNNY",  # Eğlenceli başarısızlık, ironi, kahkaha
    "RAGE/REACTION",  # Panik, sinirlenme, coşkulu reaksiyon
    "JUMPSCARE",  # Ani korku / şok anı
    "EPIC_MOMENT",  # Destansı başarı, teamwork, zafer
    "STORY",  # Anlatı bütünlüğü yüksek klip
    "MUNDANE",  # Sıradan/hiçbiri — viral potansiyeli düşük, fallback
]

# MUNDANE kategorisine düşen kliplerin skoru bu üst sınırla kırpılır
MUNDANE_SCORE_CAP: int = 30

# ---------------------------------------------------------------------------
# BANT SİSTEMİ (0-100 → 4 bant)
# ---------------------------------------------------------------------------
SCORE_BANDS = [
    {"label": "Yüksek", "min": 75, "max": 100},
    {"label": "Orta-Yüksek", "min": 55, "max": 74},
    {"label": "Orta", "min": 35, "max": 54},
    {"label": "Düşük", "min": 0, "max": 34},
]

# Bant etiketleme aktif mi?  (madde 1 varyans testinden önce kapalı)
BAND_LABELS_ENABLED: bool = True

# ---------------------------------------------------------------------------
# ENSEMBLE / MEDYAN SKORLAMA
# ---------------------------------------------------------------------------
# Aynı adayı kaç kez skorlatacak?
# 3 = medyan skor ile LLM kararsızlığını minimize eder (~10-15sn ek süre).
# 1 = tek çalışma (hızlı ama tutarsız).
ENSEMBLE_RUNS: int = 3


# ---------------------------------------------------------------------------
# HİBRİT SKOR AĞIRLIKLARI
# ---------------------------------------------------------------------------
# final_score = fusion_score * FUSION_WEIGHT + llm_score * LLM_WEIGHT
# Fusion sinyali (ses, yorum, pitch) ve LLM yargısı birbirini dengeler.
FUSION_WEIGHT: float = 0.30
LLM_WEIGHT: float = 0.70

# ---------------------------------------------------------------------------
# HEATMAP FÜZYON
# ---------------------------------------------------------------------------
# Gerçek YouTube heatmap verisi varsa füzyon sinyaline katılsın mı?
HEATMAP_FUSION_ENABLED: bool = True
# Heatmap sinyal ağırlığı (gerçek veri varsa)
HEATMAP_FUSION_WEIGHT: float = 0.25

# ---------------------------------------------------------------------------
# TUTARLILIK TESTİ
# ---------------------------------------------------------------------------
# score_consistency_test() içinde kaç kez tekrar çalıştırılacak?
CONSISTENCY_TEST_RUNS: int = 3

