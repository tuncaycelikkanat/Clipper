import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Badge } from '@/components/ui/Badge';
import { api } from '@/lib/api';
import { Youtube, Key, HardDrive, Trash2, CheckCircle2, XCircle, RefreshCw, Sliders, Sparkles } from 'lucide-react';

export default function Settings() {
  const queryClient = useQueryClient();
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [keyValue, setKeyValue] = useState('');
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  // 1. Settings / API keys
  const { data: settings, isLoading: settingsLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: () => api.settings.get(),
  });

  // 1.5. Scoring Configuration
  const { data: scoringConfig } = useQuery({
    queryKey: ['scoring-config'],
    queryFn: () => api.settings.getScoring(),
  });

  const updateScoringMutation = useMutation({
    mutationFn: (body: Partial<import('@/types').ScoringConfig>) => api.settings.updateScoring(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scoring-config'] });
      setStatusMsg('Viral skorlama ayarları güncellendi.');
      setTimeout(() => setStatusMsg(null), 4000);
    },
  });

  // 2. YouTube Auth Status
  const { data: ytStatus, refetch: refetchYt } = useQuery({
    queryKey: ['youtube-auth-status'],
    queryFn: () => api.auth.youtubeStatus(),
  });

  useEffect(() => {
    const handleMessage = (e: MessageEvent) => {
      if (e.data?.type === 'YOUTUBE_AUTH_SUCCESS') {
        refetchYt();
        setStatusMsg('YouTube hesabı başarıyla bağlandı!');
        setTimeout(() => setStatusMsg(null), 4000);
      }
    };
    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [refetchYt]);

  // 3. Disk Usage
  const { data: diskInfo, refetch: refetchDisk } = useQuery({
    queryKey: ['disk-usage'],
    queryFn: () => api.settings.disk(),
  });

  // Mutations
  const updateEnvMutation = useMutation({
    mutationFn: ({ key, value }: { key: string; value: string }) => api.settings.updateEnv(key, value),
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      setEditingKey(null);
      setKeyValue('');
      setStatusMsg(`${vars.key} başarıyla güncellendi.`);
      setTimeout(() => setStatusMsg(null), 4000);
    },
  });

  const clearCacheMutation = useMutation({
    mutationFn: () => api.settings.clearCache(),
    onSuccess: () => {
      refetchDisk();
      setStatusMsg('Geçici önbellek dosyaları temizlendi.');
      setTimeout(() => setStatusMsg(null), 4000);
    },
  });

  const clearDbMutation = useMutation({
    mutationFn: (keepChannels: boolean) => api.settings.clearDatabase(keepChannels),
    onSuccess: () => {
      queryClient.invalidateQueries();
      setStatusMsg('Veritabanı sıfırlandı (Takip edilen kanallar korundu).');
      setTimeout(() => setStatusMsg(null), 4000);
    },
  });

  const handleSaveKey = (key: string) => {
    if (keyValue.trim()) {
      updateEnvMutation.mutate({ key, value: keyValue.trim() });
    }
  };

  const keyLabels: Record<string, { label: string; desc: string }> = {
    GEMINI_API_KEY: {
      label: 'Google Gemini API Anahtarı',
      desc: 'Video segment analizi, facecam algılama ve klip değerlendirme motoru.',
    },
    OPENROUTER_API_KEY: {
      label: 'OpenRouter / DeepSeek API Anahtarı',
      desc: 'Viral başlık, açıklama ve niş YouTube/TikTok etiket üretimi.',
    },
    INSTAGRAM_ACCESS_TOKEN: {
      label: 'Instagram Graph API Access Token',
      desc: 'Instagram Reels otomatik yayınlama için hesap erişim anahtarı.',
    },
    INSTAGRAM_ACCOUNT_ID: {
      label: 'Instagram Professional Account ID',
      desc: 'Instagram Business / Creator hesap kimliği.',
    },
    TIKTOK_SESSION_ID: {
      label: 'TikTok Session ID',
      desc: 'TikTok doğrudan video yükleme oturumu.',
    },
  };

  return (
    <div className="space-y-8 max-w-4xl pb-12">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Ayarlar</h1>
          <p className="text-zinc-400 text-sm mt-1">API anahtarları, platform bağlantıları ve disk yönetimi.</p>
        </div>
      </div>

      {statusMsg && (
        <div className="bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 px-4 py-3 rounded-lg flex items-center gap-2 text-sm">
          <CheckCircle2 className="w-4 h-4" />
          <span>{statusMsg}</span>
        </div>
      )}

      {/* ── 1. YouTube OAuth2 Bağlantısı ────────────────────────────── */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-red-600/10 flex items-center justify-center text-red-500">
              <Youtube className="w-5 h-5" />
            </div>
            <div>
              <CardTitle className="text-base">YouTube Shorts Bağlantısı</CardTitle>
              <p className="text-xs text-zinc-400 mt-0.5">Otomatik Shorts yüklemeleri için Google OAuth2 hesabı</p>
            </div>
          </div>
          <Badge variant={ytStatus?.authenticated ? 'success' : 'destructive'}>
            {ytStatus?.authenticated ? 'Bağlı (Yetkilendirildi)' : 'Bağlı Değil'}
          </Badge>
        </CardHeader>
        <CardContent className="pt-2">
          <div className="flex items-center justify-between bg-zinc-950/60 p-4 rounded-lg border border-zinc-800/80">
            <div className="text-sm">
              <p className="font-medium text-zinc-200">
                {ytStatus?.authenticated ? 'Hesap Aktif' : 'Yetkilendirme Gerekli'}
              </p>
              <p className="text-xs text-zinc-500 mt-0.5">
                {ytStatus?.authenticated
                  ? 'Klipler doğrudan YouTube kanalınıza yüklenebilir.'
                  : 'Otomatik yükleme için credentials.json ve token.json gereklidir.'}
              </p>
            </div>
            <Button
              variant={ytStatus?.authenticated ? 'outline' : 'default'}
              className={!ytStatus?.authenticated ? 'bg-red-600 hover:bg-red-700 text-white' : ''}
              onClick={async () => {
                // Tarayıcı açılır pencere engelleyicisini (Popup Blocker) aşmak için pencereyi senkron olarak hemen açıyoruz
                const popup = window.open('about:blank', '_blank', 'width=600,height=750,location=no,status=no');
                if (popup) {
                  try {
                    popup.document.write(
                      '<!DOCTYPE html><html><head><title>Yönlendiriliyor...</title></head><body style="background:#09090b;color:#a1a1aa;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;"><p>Google giriş ekranına yönlendiriliyorsunuz...</p></body></html>'
                    );
                  } catch {
                    // cross-origin ignore
                  }
                }

                try {
                  const res = await api.auth.youtubeUrl();
                  if (res.url) {
                    if (popup && !popup.closed) {
                      popup.location.href = res.url;
                      popup.focus();
                    } else {
                      window.location.href = res.url;
                    }

                    // Periyodik kontrol başlat
                    const pollTimer = setInterval(async () => {
                      const updated = await refetchYt();
                      if (updated.data?.authenticated) {
                        clearInterval(pollTimer);
                        setStatusMsg('YouTube hesabı başarıyla bağlandı!');
                        setTimeout(() => setStatusMsg(null), 4000);
                      }
                    }, 2000);
                    setTimeout(() => clearInterval(pollTimer), 120000);
                  } else {
                    if (popup && !popup.closed) popup.close();
                    alert('Yetkilendirme adresi alınamadı.');
                  }
                } catch (err: any) {
                  if (popup && !popup.closed) popup.close();
                  alert(`OAuth yetkilendirme akışı başlatılamadı: ${err?.message || err}`);
                }
              }}
            >
              {ytStatus?.authenticated ? 'Yeniden Yetkilendir' : 'YouTube Hesabını Bağla'}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* ── 2. AI & Platform API Anahtarları ────────────────────────── */}
      <Card>
        <CardHeader className="flex flex-row items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-violet-600/10 flex items-center justify-center text-violet-500">
            <Key className="w-5 h-5" />
          </div>
          <div>
            <CardTitle className="text-base">API Anahtarları (.env)</CardTitle>
            <p className="text-xs text-zinc-400 mt-0.5">Yapay zeka modelleri ve sosyal medya entegrasyonları</p>
          </div>
        </CardHeader>
        <CardContent className="space-y-4 pt-2">
          {settingsLoading ? (
            <div className="text-sm text-zinc-500">Yükleniyor...</div>
          ) : (
            settings &&
            Object.entries(settings).map(([key, info]: [string, any]) => {
              const meta = keyLabels[key] || { label: key, desc: '' };
              const isEditing = editingKey === key;

              return (
                <div key={key} className="p-4 rounded-lg bg-zinc-950/60 border border-zinc-800/80 space-y-2">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-zinc-200">{meta.label}</span>
                        <Badge variant={info.set ? 'success' : 'destructive'} className="text-[10px] py-0 px-1.5">
                          {info.set ? 'Tanımlı' : 'Eksik'}
                        </Badge>
                      </div>
                      <p className="text-xs text-zinc-500 mt-0.5">{meta.desc}</p>
                    </div>

                    {!isEditing && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          setEditingKey(key);
                          setKeyValue('');
                        }}
                      >
                        {info.set ? 'Değiştir' : 'Tanımla'}
                      </Button>
                    )}
                  </div>

                  {!isEditing ? (
                    <div className="text-xs font-mono text-zinc-400 bg-zinc-900/80 px-3 py-1.5 rounded border border-zinc-800">
                      {info.masked || 'Tanımlanmamış'}
                    </div>
                  ) : (
                    <div className="flex gap-2 mt-2">
                      <Input
                        type="password"
                        placeholder={`Yeni ${key} değerini yapıştırın...`}
                        value={keyValue}
                        onChange={(e) => setKeyValue(e.target.value)}
                        className="font-mono text-xs h-9"
                      />
                      <Button size="sm" onClick={() => handleSaveKey(key)} disabled={!keyValue.trim()}>
                        Kaydet
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          setEditingKey(null);
                          setKeyValue('');
                        }}
                      >
                        İptal
                      </Button>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </CardContent>
      </Card>

      {/* ── 2.5. Viral Skorlama & Kalibrasyon Motoru Ayarları ──────── */}
      <Card>
        <CardHeader className="flex flex-row items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-amber-500/10 flex items-center justify-center text-amber-400">
            <Sparkles className="w-5 h-5" />
          </div>
          <div>
            <CardTitle className="text-base">Viral Skorlama & Algılama Motoru</CardTitle>
            <p className="text-xs text-zinc-400 mt-0.5">Gemini Flash ağırlıkları, bant etiketleme ve ensemble modları</p>
          </div>
        </CardHeader>
        <CardContent className="space-y-4 pt-2">
          {scoringConfig ? (
            <div className="space-y-4">
              {/* Ağırlık Dağılımı */}
              <div className="p-4 rounded-lg bg-zinc-950/60 border border-zinc-800/80 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-zinc-200">Sinyal ve Prompt Ağırlıkları</span>
                  <span className="text-xs font-mono text-zinc-400">Toplam: %100</span>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                  <div className="p-2.5 rounded bg-zinc-900 border border-zinc-800">
                    <span className="text-zinc-400 block text-[11px]">Hook Gücü</span>
                    <span className="font-bold text-amber-400 text-sm">%{scoringConfig.hook_strength_weight}</span>
                  </div>
                  <div className="p-2.5 rounded bg-zinc-900 border border-zinc-800">
                    <span className="text-zinc-400 block text-[11px]">Duygu/Şiddet</span>
                    <span className="font-bold text-pink-400 text-sm">%{scoringConfig.emotion_weight}</span>
                  </div>
                  <div className="p-2.5 rounded bg-zinc-900 border border-zinc-800">
                    <span className="text-zinc-400 block text-[11px]">Hikaye Bütünlüğü</span>
                    <span className="font-bold text-blue-400 text-sm">%{scoringConfig.story_completeness_weight}</span>
                  </div>
                  <div className="p-2.5 rounded bg-zinc-900 border border-zinc-800">
                    <span className="text-zinc-400 block text-[11px]">Sinyal Doğrulama</span>
                    <span className="font-bold text-emerald-400 text-sm">%{scoringConfig.signal_validation_weight}</span>
                  </div>
                </div>
                <p className="text-[11px] text-zinc-500 italic">
                  * Ağırlıklar Pitch/F0 varyansı (kahkaha) ve Frame-diff (sahne kesimi) sinyalleriyle optimize edilmiştir.
                </p>
              </div>

              {/* Seçenekler ve Kontroller */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Bant Etiketleme */}
                <div className="p-4 rounded-lg bg-zinc-950/60 border border-zinc-800/80 flex items-center justify-between">
                  <div>
                    <span className="text-sm font-medium text-zinc-200 block">Skor Bant Etiketleme</span>
                    <span className="text-xs text-zinc-400">0-100 skoru 4 seviyeli banda çevir</span>
                  </div>
                  <Button
                    size="sm"
                    variant={scoringConfig.band_labels_enabled ? 'default' : 'outline'}
                    className={scoringConfig.band_labels_enabled ? 'bg-violet-600 hover:bg-violet-700' : ''}
                    onClick={() => updateScoringMutation.mutate({ band_labels_enabled: !scoringConfig.band_labels_enabled })}
                  >
                    {scoringConfig.band_labels_enabled ? 'Aktif' : 'Kapalı'}
                  </Button>
                </div>

                {/* Ensemble Medyan Modu */}
                <div className="p-4 rounded-lg bg-zinc-950/60 border border-zinc-800/80 flex items-center justify-between">
                  <div>
                    <span className="text-sm font-medium text-zinc-200 block">Ensemble Skorlama</span>
                    <span className="text-xs text-zinc-400">
                      {scoringConfig.ensemble_runs > 1 ? `${scoringConfig.ensemble_runs}x Medyan Modu` : 'Tekil Çalışma (Hızlı)'}
                    </span>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => updateScoringMutation.mutate({ ensemble_runs: scoringConfig.ensemble_runs === 1 ? 3 : 1 })}
                  >
                    {scoringConfig.ensemble_runs > 1 ? '3x Medyan (Aktif)' : '1x Tekil'}
                  </Button>
                </div>
              </div>
            </div>
          ) : (
            <div className="text-xs text-zinc-500">Skorlama konfigürasyonu yükleniyor...</div>
          )}
        </CardContent>
      </Card>

      {/* ── 3. Depolama & Disk Yönetimi ─────────────────────────────── */}
      <Card>
        <CardHeader className="flex flex-row items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-blue-600/10 flex items-center justify-center text-blue-500">
            <HardDrive className="w-5 h-5" />
          </div>
          <div>
            <CardTitle className="text-base">Depolama & Veritabanı</CardTitle>
            <p className="text-xs text-zinc-400 mt-0.5">Render çıktıları, geçici dosyalar ve SQLite veritabanı</p>
          </div>
        </CardHeader>
        <CardContent className="space-y-4 pt-2">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="p-4 rounded-lg bg-zinc-950/60 border border-zinc-800/80 flex items-center justify-between">
              <div>
                <p className="text-xs text-zinc-500">Kayıtlı Klip Sayısı</p>
                <p className="text-lg font-bold text-zinc-100 mt-0.5">{diskInfo?.clip_count || 0}</p>
              </div>
              <Button size="sm" variant="outline" onClick={() => refetchDisk()}>
                <RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Yenile
              </Button>
            </div>

            <div className="p-4 rounded-lg bg-zinc-950/60 border border-zinc-800/80 flex items-center justify-between">
              <div>
                <p className="text-xs text-zinc-500">Geçici Video Önbelleği</p>
                <p className="text-xs text-zinc-400 mt-1">İndirilen ham parçalar</p>
              </div>
              <Button
                size="sm"
                variant="outline"
                className="text-amber-500 hover:text-amber-400"
                onClick={() => clearCacheMutation.mutate()}
              >
                Önbelleği Temizle
              </Button>
            </div>
          </div>

          <div className="p-4 rounded-lg bg-red-950/20 border border-red-900/30 flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-red-400">Veritabanını Sıfırla</p>
              <p className="text-xs text-zinc-400 mt-0.5">
                Klipler ve işlenmiş video geçmişi silinir. Takip edilen kanallar korunur.
              </p>
            </div>
            <Button
              size="sm"
              variant="destructive"
              onClick={() => {
                if (confirm('Veritabanındaki tüm klipler ve iş geçmişi silinsin mi? (Kanallar korunacak)')) {
                  clearDbMutation.mutate(true);
                }
              }}
            >
              <Trash2 className="w-3.5 h-3.5 mr-1.5" /> Sıfırla
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
