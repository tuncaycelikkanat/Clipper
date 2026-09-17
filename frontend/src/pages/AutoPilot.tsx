import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from '@tanstack/react-router';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Badge } from '@/components/ui/Badge';
import { api } from '@/lib/api';
import { Channel, Video } from '@/types';
import {
  Bot,
  Play,
  Square,
  Plus,
  Trash2,
  ExternalLink,
  Clock,
  ShieldCheck,
  CheckCircle2,
  Radar,
  Loader2,
  CheckSquare,
  Sparkles,
  Scissors,
  Layers,
  Share2,
} from 'lucide-react';

export default function AutoPilot() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [showAddModal, setShowAddModal] = useState(false);
  const [newUrl, setNewUrl] = useState('');
  const [newName, setNewName] = useState('');
  const [newMinScore, setNewMinScore] = useState(90);
  const [newAutoUpload, setNewAutoUpload] = useState(true);
  const [newInterval, setNewInterval] = useState(2.0);
  const [newPlaylist, setNewPlaylist] = useState('');
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  // Selected videos for batch processing
  const [selectedVideoIds, setSelectedVideoIds] = useState<string[]>([]);
  const [selectedChannelIds, setSelectedChannelIds] = useState<string[]>([]);
  const [batchTargetClips, setBatchTargetClips] = useState(0); // 0 = Otomatik (Süreye Göre)
  const [batchSubtitles, setBatchSubtitles] = useState(false); // Default FALSE
  const [batchHookCard, setBatchHookCard] = useState(false); // Default FALSE

  // 1. Fetch tracked channels
  const { data: channels, isLoading: channelsLoading } = useQuery({
    queryKey: ['channels'],
    queryFn: () => api.channels.list(),
  });

  // 2. Fetch pending videos in queue
  const { data: pendingVideos, isLoading: pendingLoading } = useQuery({
    queryKey: ['pending-videos'],
    queryFn: () => api.videos.pending(),
    refetchInterval: 5000,
  });

  // 3. Fetch Scheduler status
  const { data: schedulerStatus, refetch: refetchScheduler } = useQuery({
    queryKey: ['scheduler-status'],
    queryFn: () => api.scheduler.status(),
    refetchInterval: 5000,
  });

  // Mutations
  const scanChannelsMutation = useMutation({
    mutationFn: () => api.channels.scanLatest({ max_per_channel: 1 }),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['pending-videos'] });
      queryClient.invalidateQueries({ queryKey: ['channels'] });
      setStatusMsg(res.message || `${res.scanned_channels} kanal tarandı. ${res.new_videos_found} yeni video sıraya alındı.`);
      setTimeout(() => setStatusMsg(null), 6000);
    },
    onError: (err: any) => {
      setStatusMsg(`Tarama hatası: ${err.message || 'Bilinmeyen hata'}`);
      setTimeout(() => setStatusMsg(null), 5000);
    },
  });

  const batchProcessMutation = useMutation({
    mutationFn: (videoIds: string[]) =>
      api.pipeline.batchProcessVideos({
        video_ids: videoIds,
        target_clips: batchTargetClips,
        render_mode: 'shorts_9x16_blur',
        add_subtitles: batchSubtitles,
        add_hook_card: batchHookCard,
        enhance_colors: true,
      }),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['pending-videos'] });
      setSelectedVideoIds([]);
      setStatusMsg(`${res.count} video işleme alındı! Analiz sayfasına yönlendiriliyorsunuz...`);
      setTimeout(() => {
        setStatusMsg(null);
        if (res.jobs && res.jobs.length > 0) {
          const jobIds = res.jobs.map((j: any) => j.job_id);
          localStorage.setItem('clipper_active_job_ids', JSON.stringify(jobIds));
          localStorage.setItem('clipper_active_job_id', res.jobs[0].job_id);
          navigate({ to: '/analyze' });
        }
      }, 1500);
    },
    onError: (err: any) => {
      setStatusMsg(`İşleme hatası: ${err.message || 'Bilinmeyen hata'}`);
      setTimeout(() => setStatusMsg(null), 5000);
    },
  });

  const toggleDelayMutation = useMutation({
    mutationFn: ({ id, delayHours }: { id: string; delayHours: number }) =>
      api.videos.setDelay(id, delayHours),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pending-videos'] });
    },
    onError: (err: any) => {
      setStatusMsg(`Hata: ${err.message || 'Bekletme süresi güncellenemedi'}`);
      setTimeout(() => setStatusMsg(null), 4000);
    },
  });

  const batchDelayMutation = useMutation({
    mutationFn: (delayHours: number) =>
      api.videos.setBatchDelay(selectedVideoIds, delayHours),
    onSuccess: (_, delayHours) => {
      queryClient.invalidateQueries({ queryKey: ['pending-videos'] });
      setStatusMsg(
        delayHours > 0
          ? `Seçilen ${selectedVideoIds.length} video için 1 gün (24s) yorum bekleme süresi ayarlandı.`
          : `Seçilen ${selectedVideoIds.length} video için bekleme süresi kaldırıldı.`
      );
      setTimeout(() => setStatusMsg(null), 4000);
    },
    onError: (err: any) => {
      setStatusMsg(`Hata: ${err.message || 'Toplu işlem başarısız'}`);
      setTimeout(() => setStatusMsg(null), 4000);
    },
  });

  const getDelayInfo = (processAfter?: string | null) => {
    if (!processAfter) return null;
    const target = new Date(processAfter).getTime();
    const now = Date.now();
    const diffMs = target - now;
    if (diffMs <= 0) return null;
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffMins = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
    return {
      hours: diffHours,
      mins: diffMins,
      text: `${diffHours > 0 ? `${diffHours}s ` : ''}${diffMins}dk kaldı`,
      isWaiting: true,
    };
  };

  const deleteVideoMutation = useMutation({
    mutationFn: (id: string) => api.videos.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pending-videos'] });
      setStatusMsg('Video sıradan kaldırıldı.');
      setTimeout(() => setStatusMsg(null), 3000);
    },
  });

  const startSchedulerMutation = useMutation({
    mutationFn: (interval: number) => api.scheduler.start(interval),
    onSuccess: () => {
      refetchScheduler();
      setStatusMsg('AutoPilot arka plan servisi başlatıldı.');
      setTimeout(() => setStatusMsg(null), 4000);
    },
  });

  const stopSchedulerMutation = useMutation({
    mutationFn: () => api.scheduler.stop(),
    onSuccess: () => {
      refetchScheduler();
      setStatusMsg('AutoPilot durduruldu.');
      setTimeout(() => setStatusMsg(null), 4000);
    },
  });

  const startVideoScannerMutation = useMutation({
    mutationFn: (interval: number = 2.0) => api.scheduler.startVideoScanner(interval),
    onSuccess: () => {
      refetchScheduler();
      setStatusMsg('Yeni video tarama servisi başlatıldı.');
      setTimeout(() => setStatusMsg(null), 4000);
    },
  });

  const stopVideoScannerMutation = useMutation({
    mutationFn: () => api.scheduler.stopVideoScanner(),
    onSuccess: () => {
      refetchScheduler();
      setStatusMsg('Yeni video tarama servisi durduruldu.');
      setTimeout(() => setStatusMsg(null), 4000);
    },
  });

  const startClipPublisherMutation = useMutation({
    mutationFn: (intervalMinutes: number = 2) => api.scheduler.startClipPublisher(intervalMinutes),
    onSuccess: () => {
      refetchScheduler();
      setStatusMsg('Klip paylaşma servisi başlatıldı.');
      setTimeout(() => setStatusMsg(null), 4000);
    },
  });

  const stopClipPublisherMutation = useMutation({
    mutationFn: () => api.scheduler.stopClipPublisher(),
    onSuccess: () => {
      refetchScheduler();
      setStatusMsg('Klip paylaşma servisi durduruldu.');
      setTimeout(() => setStatusMsg(null), 4000);
    },
  });

  const createChannelMutation = useMutation({
    mutationFn: (body: any) => api.channels.create(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['channels'] });
      setShowAddModal(false);
      setNewUrl('');
      setNewName('');
      setStatusMsg('Yeni kanal takibe alındı.');
      setTimeout(() => setStatusMsg(null), 4000);
    },
  });

  const deleteChannelMutation = useMutation({
    mutationFn: (id: string) => api.channels.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['channels'] });
      setStatusMsg('Kanal takipten çıkarıldı.');
      setTimeout(() => setStatusMsg(null), 4000);
    },
  });

  const batchDeleteChannelsMutation = useMutation({
    mutationFn: ({ ids, all }: { ids: string[]; all?: boolean }) =>
      api.channels.batchDelete(ids, all),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['channels'] });
      setSelectedChannelIds([]);
      setStatusMsg(`${res.deleted_count} kanal takipten çıkarıldı.`);
      setTimeout(() => setStatusMsg(null), 4000);
    },
    onError: (err: any) => {
      setStatusMsg(`Kanal silme hatası: ${err.message || 'Bilinmeyen hata'}`);
      setTimeout(() => setStatusMsg(null), 5000);
    },
  });

  const batchDeleteVideosMutation = useMutation({
    mutationFn: (ids: string[]) => api.videos.batchDelete(ids),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['pending-videos'] });
      setSelectedVideoIds([]);
      setStatusMsg(`${res.deleted_count} video listeden silindi.`);
      setTimeout(() => setStatusMsg(null), 4000);
    },
    onError: (err: any) => {
      setStatusMsg(`Video silme hatası: ${err.message || 'Bilinmeyen hata'}`);
      setTimeout(() => setStatusMsg(null), 5000);
    },
  });

  const toggleChannelMutation = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) =>
      api.channels.update(id, { active } as any),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['channels'] });
    },
  });

  const handleAddChannel = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newUrl || !newName) return;
    createChannelMutation.mutate({
      url: newUrl,
      name: newName,
      min_score: Number(newMinScore),
      auto_upload: newAutoUpload,
      check_interval_h: Number(newInterval),
      target_playlist: newPlaylist || undefined,
    });
  };

  const toggleSelectVideo = (id: string) => {
    setSelectedVideoIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  };

  const toggleSelectAll = () => {
    if (!pendingVideos || pendingVideos.length === 0) return;
    if (selectedVideoIds.length === pendingVideos.length) {
      setSelectedVideoIds([]);
    } else {
      setSelectedVideoIds(pendingVideos.map((v) => v.id));
    }
  };

  const toggleSelectChannel = (id: string) => {
    setSelectedChannelIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  };

  const toggleSelectAllChannels = () => {
    if (!channels || channels.length === 0) return;
    const allIds = channels.map((c) => c.id || c.url);
    if (selectedChannelIds.length === allIds.length) {
      setSelectedChannelIds([]);
    } else {
      setSelectedChannelIds(allIds);
    }
  };

  const isVideoScannerRunning = schedulerStatus?.video_scanner_running ?? false;
  const isClipPublisherRunning = schedulerStatus?.clip_publisher_running ?? false;
  const isRunning = schedulerStatus?.running ?? (isVideoScannerRunning || isClipPublisherRunning);

  return (
    <div className="space-y-8 max-w-6xl pb-12">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">AutoPilot Otonom Motoru</h1>
          <p className="text-zinc-400 text-sm mt-1">
            YouTube kanallarını periyodik tarar, yeni videoları tespit eder ve seçilenleri otomatik işler.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            onClick={() => scanChannelsMutation.mutate()}
            disabled={scanChannelsMutation.isPending}
            className="bg-indigo-600 hover:bg-indigo-700 text-white shadow-lg shadow-indigo-600/20"
          >
            {scanChannelsMutation.isPending ? (
              <Loader2 className="w-4 h-4 mr-1.5 animate-spin" />
            ) : (
              <Radar className="w-4 h-4 mr-1.5" />
            )}
            Kanalları Tara
          </Button>

          <Button onClick={() => setShowAddModal(true)} className="bg-violet-600 hover:bg-violet-700">
            <Plus className="w-4 h-4 mr-1.5" /> Yeni Kanal Ekle
          </Button>
        </div>
      </div>

      {statusMsg && (
        <div className="bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 px-4 py-3 rounded-lg flex items-center gap-2 text-sm">
          <CheckCircle2 className="w-4 h-4" />
          <span>{statusMsg}</span>
        </div>
      )}

      {/* ── 1. İşleme Bekleyen Videolar Sırası (Seç ve İşle) ────────── */}
      <Card className="border-indigo-600/40 bg-zinc-900/90 shadow-xl overflow-hidden">
        <CardHeader className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-3 border-b border-zinc-800">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg flex items-center justify-center bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              <Layers className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <CardTitle className="text-base">İşleme Bekleyen Videolar & Sıra</CardTitle>
                <Badge variant="outline" className="text-xs bg-indigo-500/10 text-indigo-300 border-indigo-500/30">
                  {pendingVideos?.length || 0} Video
                </Badge>
              </div>
              <p className="text-xs text-zinc-400 mt-0.5">
                Kanallardan çekilen yeni videolar. Seçtiklerinizi tek tıkla işleyip klip üretebilirsiniz.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {selectedVideoIds.length > 0 && (
              <>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={batchDeleteVideosMutation.isPending}
                  onClick={() => {
                    if (confirm(`Seçili ${selectedVideoIds.length} videoyu listeden silmek istediğinize emin misiniz?`)) {
                      batchDeleteVideosMutation.mutate(selectedVideoIds);
                    }
                  }}
                  className="text-xs border-red-600/40 text-red-300 hover:bg-red-600/10"
                >
                  <Trash2 className="w-3.5 h-3.5 mr-1" />
                  Seçilenleri Sil ({selectedVideoIds.length})
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={batchDelayMutation.isPending}
                  onClick={() => batchDelayMutation.mutate(24)}
                  className="text-xs border-amber-600/40 text-amber-300 hover:bg-amber-600/10"
                >
                  <Clock className="w-3.5 h-3.5 mr-1" />
                  1 Gün Beklet ({selectedVideoIds.length})
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={batchDelayMutation.isPending}
                  onClick={() => batchDelayMutation.mutate(0)}
                  className="text-xs border-zinc-700 text-zinc-300 hover:bg-zinc-800"
                >
                  Bekletmeyi Kaldır
                </Button>
              </>
            )}

            <Button
              size="sm"
              variant="outline"
              onClick={toggleSelectAll}
              disabled={!pendingVideos || pendingVideos.length === 0}
              className="text-xs border-zinc-700"
            >
              <CheckSquare className="w-3.5 h-3.5 mr-1" />
              {selectedVideoIds.length === (pendingVideos?.length || 0) && pendingVideos && pendingVideos.length > 0
                ? 'Seçimi Kaldır'
                : 'Tümünü Seç'}
            </Button>

            <Button
              size="sm"
              disabled={selectedVideoIds.length === 0 || batchProcessMutation.isPending}
              onClick={() => batchProcessMutation.mutate(selectedVideoIds)}
              className="bg-emerald-600 hover:bg-emerald-700 text-white font-medium text-xs shadow-lg shadow-emerald-600/20"
            >
              {batchProcessMutation.isPending ? (
                <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
              ) : (
                <Scissors className="w-3.5 h-3.5 mr-1.5" />
              )}
              Seçilenleri İşle ({selectedVideoIds.length})
            </Button>
          </div>
        </CardHeader>

        {/* Seçenek Ayarları Şeridi */}
        <div className="bg-zinc-950/60 px-4 py-2.5 border-b border-zinc-800/80 flex flex-wrap items-center justify-between gap-4 text-xs text-zinc-400">
          <div className="flex flex-wrap items-center gap-6">
            <div className="flex items-center gap-2">
              <span>Hedef Klip:</span>
              <select
                value={batchTargetClips}
                onChange={(e) => setBatchTargetClips(Number(e.target.value))}
                className="bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-zinc-200 focus:outline-none"
              >
                <option value={0}>✨ Otomatik (Süreye Göre)</option>
                <option value={2}>2 Klip</option>
                <option value={3}>3 Klip</option>
                <option value={5}>5 Klip</option>
                <option value={8}>8 Klip</option>
                <option value={10}>10 Klip</option>
                <option value={15}>15 Klip</option>
              </select>
            </div>

            <label className="flex items-center gap-1.5 cursor-pointer">
              <input
                type="checkbox"
                checked={batchSubtitles}
                onChange={(e) => setBatchSubtitles(e.target.checked)}
                className="rounded border-zinc-700 bg-zinc-900 text-indigo-600"
              />
              <span>Altyazı ({batchSubtitles ? 'Açık' : 'Kapalı - Varsayılan'})</span>
            </label>

            <label className="flex items-center gap-1.5 cursor-pointer">
              <input
                type="checkbox"
                checked={batchHookCard}
                onChange={(e) => setBatchHookCard(e.target.checked)}
                className="rounded border-zinc-700 bg-zinc-900 text-indigo-600"
              />
              <span>Hook Başlık Kartı ({batchHookCard ? 'Açık' : 'Kapalı - Varsayılan'})</span>
            </label>
          </div>
          <span className="text-[11px] text-zinc-500">
            * ⏳ 1 Gün Beklet seçilen videolar yorumların dolması için 24 saat sonra işlenir.
          </span>
        </div>

        <CardContent className="pt-3">
          {pendingLoading ? (
            <div className="text-sm text-zinc-500 py-6 text-center">Bekleyen videolar taranıyor...</div>
          ) : !pendingVideos || pendingVideos.length === 0 ? (
            <div className="text-center py-8 text-sm text-zinc-500 space-y-2">
              <p>İşleme bekleyen video bulunmuyor.</p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => scanChannelsMutation.mutate()}
                disabled={scanChannelsMutation.isPending}
                className="text-xs"
              >
                <Radar className="w-3.5 h-3.5 mr-1" /> Kanalları Şimdi Tara
              </Button>
            </div>
          ) : (
            <div className="divide-y divide-zinc-800/80 border border-zinc-800 rounded-lg overflow-hidden bg-zinc-950/40 max-h-96 overflow-y-auto">
              {pendingVideos.map((video: Video) => {
                const isSelected = selectedVideoIds.includes(video.id);
                const delayInfo = getDelayInfo(video.process_after);
                const isDelayed = Boolean(delayInfo?.isWaiting);

                return (
                  <div
                    key={video.id}
                    className={`p-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 transition-colors ${
                      isSelected ? 'bg-indigo-950/20' : 'hover:bg-zinc-900/40'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => toggleSelectVideo(video.id)}
                        className="rounded border-zinc-700 bg-zinc-900 text-indigo-600 w-4 h-4 cursor-pointer"
                      />
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-sm text-zinc-100 line-clamp-1">{video.title}</span>
                          <a
                            href={video.url}
                            target="_blank"
                            rel="noreferrer"
                            className="text-zinc-500 hover:text-zinc-300 inline-flex items-center"
                          >
                            <ExternalLink className="w-3.5 h-3.5" />
                          </a>
                        </div>
                        <div className="flex flex-wrap items-center gap-2.5 text-xs text-zinc-400">
                          <span className="text-zinc-300 font-medium">{video.uploader || 'Kanal'}</span>
                          <span>•</span>
                          <span className="font-mono text-[11px] text-zinc-500">{video.id}</span>
                          <span>•</span>
                          {isDelayed ? (
                            <Badge variant="outline" className="text-[10px] py-0 px-1.5 bg-amber-500/10 text-amber-300 border-amber-500/30 flex items-center gap-1 font-normal">
                              <Clock className="w-2.5 h-2.5" /> 1 Gün Beklemede ({delayInfo?.text})
                            </Badge>
                          ) : (
                            <Badge variant="secondary" className="text-[10px] py-0 px-1.5 bg-emerald-500/10 text-emerald-300 border-emerald-500/20 font-normal">
                              Hemen İşlenebilir
                            </Badge>
                          )}
                        </div>
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center gap-2.5 self-end sm:self-auto">
                      {/* 1 Gün Beklet Kutucuğu */}
                      <label className={`flex items-center gap-1.5 cursor-pointer border rounded-md px-2.5 py-1 text-xs transition-colors select-none ${
                        isDelayed
                          ? 'bg-amber-950/30 border-amber-500/40 text-amber-300 shadow-sm shadow-amber-500/10'
                          : 'bg-zinc-900 border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-300'
                      }`}>
                        <input
                          type="checkbox"
                          checked={isDelayed}
                          disabled={toggleDelayMutation.isPending}
                          onChange={(e) =>
                            toggleDelayMutation.mutate({
                              id: video.id,
                              delayHours: e.target.checked ? 24 : 0,
                            })
                          }
                          className="rounded border-zinc-600 bg-zinc-950 text-amber-500 w-3.5 h-3.5 focus:ring-0 cursor-pointer"
                        />
                        <span className="font-medium">
                          {isDelayed ? '⏳ 1 Gün Bekliyor' : '⏳ 1 Gün Beklet (Yorumlar Dolsun)'}
                        </span>
                      </label>

                      <Button
                        size="sm"
                        variant="outline"
                        className="text-xs h-8 text-violet-400 border-violet-500/30 hover:bg-violet-500/10"
                        onClick={() => navigate({ to: '/analyze', search: { url: video.url } })}
                      >
                        <Sparkles className="w-3.5 h-3.5 mr-1" /> Analiz Et
                      </Button>

                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-8 text-red-400 hover:text-red-300 hover:bg-red-500/10"
                        onClick={() => deleteVideoMutation.mutate(video.id)}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Otomasyon Servisleri (Video Tarama & Klip Paylaşma) ──────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* 1. Yeni Video Tarama Servisi */}
        <Card className="border-zinc-800 bg-zinc-900/90 flex flex-col justify-between">
          <CardHeader className="flex flex-row items-center justify-between pb-3">
            <div className="flex items-center gap-3">
              <div
                className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                  isVideoScannerRunning
                    ? 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20'
                    : 'bg-zinc-800 text-zinc-400'
                }`}
              >
                <Radar className="w-5 h-5" />
              </div>
              <div>
                <CardTitle className="text-base">Yeni Video Tarama</CardTitle>
                <p className="text-xs text-zinc-400 mt-0.5">
                  {isVideoScannerRunning ? 'Kanallar periyodik taranıyor.' : 'Tarama kapalı. Manuel başlatabilirsiniz.'}
                </p>
              </div>
            </div>
            <Badge variant={isVideoScannerRunning ? 'success' : 'secondary'} className="px-3 py-1 text-xs">
              {isVideoScannerRunning ? '● Çalışıyor' : 'Durduruldu'}
            </Badge>
          </CardHeader>
          <CardContent className="pt-2">
            <div className="bg-zinc-950/70 p-4 rounded-lg border border-zinc-800/80 space-y-4">
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
                <div>
                  <span className="text-xs text-zinc-500 block">Tarama Sıklığı</span>
                  <span className="font-semibold text-zinc-200">
                    {schedulerStatus?.scanner_interval_hours ?? schedulerStatus?.interval_hours ?? 2} Saatte bir
                  </span>
                </div>
                <div>
                  <span className="text-xs text-zinc-500 block">Tamamlanan Döngü</span>
                  <span className="font-semibold text-zinc-200">{schedulerStatus?.cycle_count ?? 0}</span>
                </div>
                <div>
                  <span className="text-xs text-zinc-500 block">Son Tarama</span>
                  <span className="font-semibold text-zinc-200 text-xs">
                    {schedulerStatus?.last_scanner_run || schedulerStatus?.last_run
                      ? new Date(schedulerStatus.last_scanner_run || schedulerStatus.last_run!).toLocaleTimeString()
                      : 'Henüz yok'}
                  </span>
                </div>
              </div>

              <div className="flex justify-end pt-1">
                {!isVideoScannerRunning ? (
                  <Button
                    className="bg-indigo-600 hover:bg-indigo-700 text-white w-full sm:w-auto"
                    onClick={() => startVideoScannerMutation.mutate(2.0)}
                    disabled={startVideoScannerMutation.isPending}
                  >
                    <Play className="w-4 h-4 mr-1.5 fill-current" /> Taramayı Başlat
                  </Button>
                ) : (
                  <Button
                    variant="destructive"
                    className="w-full sm:w-auto"
                    onClick={() => stopVideoScannerMutation.mutate()}
                    disabled={stopVideoScannerMutation.isPending}
                  >
                    <Square className="w-4 h-4 mr-1.5 fill-current" /> Taramayı Durdur
                  </Button>
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* 2. Klip Paylaşma Servisi */}
        <Card className="border-zinc-800 bg-zinc-900/90 flex flex-col justify-between">
          <CardHeader className="flex flex-row items-center justify-between pb-3">
            <div className="flex items-center gap-3">
              <div
                className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                  isClipPublisherRunning
                    ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                    : 'bg-zinc-800 text-zinc-400'
                }`}
              >
                <Share2 className="w-5 h-5" />
              </div>
              <div>
                <CardTitle className="text-base">Klip Paylaşma Otomasyonu</CardTitle>
                <p className="text-xs text-zinc-400 mt-0.5">
                  {isClipPublisherRunning ? 'Zamanı gelen klipler sosyal medyada paylaşılıyor.' : 'Klip paylaşımı durduruldu.'}
                </p>
              </div>
            </div>
            <Badge variant={isClipPublisherRunning ? 'success' : 'secondary'} className="px-3 py-1 text-xs">
              {isClipPublisherRunning ? '● Çalışıyor' : 'Durduruldu'}
            </Badge>
          </CardHeader>
          <CardContent className="pt-2">
            <div className="bg-zinc-950/70 p-4 rounded-lg border border-zinc-800/80 space-y-4">
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
                <div>
                  <span className="text-xs text-zinc-500 block">Yayın Kontrolü</span>
                  <span className="font-semibold text-zinc-200">
                    {schedulerStatus?.publisher_interval_minutes ?? 2} Dakikada bir
                  </span>
                </div>
                <div>
                  <span className="text-xs text-zinc-500 block">Hedef Platform</span>
                  <span className="font-semibold text-zinc-200">YouTube & Reels</span>
                </div>
                <div>
                  <span className="text-xs text-zinc-500 block">Son Yayın Kontrolü</span>
                  <span className="font-semibold text-zinc-200 text-xs">
                    {schedulerStatus?.last_publisher_run
                      ? new Date(schedulerStatus.last_publisher_run).toLocaleTimeString()
                      : 'Henüz yok'}
                  </span>
                </div>
              </div>

              <div className="flex justify-end pt-1">
                {!isClipPublisherRunning ? (
                  <Button
                    className="bg-emerald-600 hover:bg-emerald-700 text-white w-full sm:w-auto"
                    onClick={() => startClipPublisherMutation.mutate(2)}
                    disabled={startClipPublisherMutation.isPending}
                  >
                    <Play className="w-4 h-4 mr-1.5 fill-current" /> Paylaşımı Başlat
                  </Button>
                ) : (
                  <Button
                    variant="destructive"
                    className="w-full sm:w-auto"
                    onClick={() => stopClipPublisherMutation.mutate()}
                    disabled={stopClipPublisherMutation.isPending}
                  >
                    <Square className="w-4 h-4 mr-1.5 fill-current" /> Paylaşımı Durdur
                  </Button>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ── 2. Yeni Kanal Ekleme Formu ──────────────────────────────── */}
      {showAddModal && (
        <Card className="border-violet-600/40 bg-zinc-900/95 shadow-xl">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Yeni Kanal Takibi Başlat</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleAddChannel} className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs text-zinc-400 font-medium block mb-1.5">Kanal URL veya Handle</label>
                  <Input
                    placeholder="https://www.youtube.com/@KanalAdi"
                    value={newUrl}
                    onChange={(e) => setNewUrl(e.target.value)}
                    required
                  />
                </div>
                <div>
                  <label className="text-xs text-zinc-400 font-medium block mb-1.5">Kanal Adı / Etiketi</label>
                  <Input
                    placeholder="Örn: Tolunay Ören"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    required
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="text-xs text-zinc-400 font-medium block mb-1.5">Min Viral Skor (50 - 100)</label>
                  <Input
                    type="number"
                    min="50"
                    max="100"
                    value={newMinScore}
                    onChange={(e) => setNewMinScore(Number(e.target.value))}
                  />
                </div>
                <div>
                  <label className="text-xs text-zinc-400 font-medium block mb-1.5">Kontrol Aralığı (Saat)</label>
                  <Input
                    type="number"
                    step="0.5"
                    min="0.5"
                    value={newInterval}
                    onChange={(e) => setNewInterval(Number(e.target.value))}
                  />
                </div>
                <div>
                  <label className="text-xs text-zinc-400 font-medium block mb-1.5">Hedef Playlist (Opsiyonel)</label>
                  <Input
                    placeholder="PL..."
                    value={newPlaylist}
                    onChange={(e) => setNewPlaylist(e.target.value)}
                  />
                </div>
              </div>

              <div className="flex items-center gap-2 pt-2">
                <input
                  type="checkbox"
                  id="autoUpload"
                  checked={newAutoUpload}
                  onChange={(e) => setNewAutoUpload(e.target.checked)}
                  className="rounded border-zinc-800 bg-zinc-950 text-violet-600 focus:ring-violet-500"
                />
                <label htmlFor="autoUpload" className="text-xs text-zinc-300">
                  Yeni video çıktığında klipleri doğrudan yayınlama kuyruğuna ekle (Auto Upload)
                </label>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <Button type="button" variant="ghost" onClick={() => setShowAddModal(false)}>
                  İptal
                </Button>
                <Button type="submit" className="bg-violet-600 hover:bg-violet-700">
                  Kanalı Kaydet
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {/* ── 3. Takip Edilen Kanallar Listesi ────────────────────────── */}
      <Card>
        <CardHeader className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3">
          <div>
            <CardTitle className="text-base">Takip Edilen Kanallar ({channels?.length || 0})</CardTitle>
            <p className="text-xs text-zinc-400 mt-0.5">Çift katmanlı anchor sistemi ile taranan kanallar</p>
          </div>

          {channels && channels.length > 0 && (
            <div className="flex flex-wrap items-center gap-2">
              {selectedChannelIds.length > 0 && (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={batchDeleteChannelsMutation.isPending}
                  onClick={() => {
                    if (confirm(`Seçili ${selectedChannelIds.length} kanalı takipten çıkarmak istediğinize emin misiniz?`)) {
                      batchDeleteChannelsMutation.mutate({ ids: selectedChannelIds });
                    }
                  }}
                  className="text-xs border-red-600/40 text-red-300 hover:bg-red-600/10"
                >
                  <Trash2 className="w-3.5 h-3.5 mr-1" />
                  Seçilenleri Sil ({selectedChannelIds.length})
                </Button>
              )}

              <Button
                size="sm"
                variant="outline"
                onClick={toggleSelectAllChannels}
                className="text-xs border-zinc-700"
              >
                <CheckSquare className="w-3.5 h-3.5 mr-1" />
                {selectedChannelIds.length === channels.length ? 'Seçimi Kaldır' : 'Tümünü Seç'}
              </Button>

              <Button
                size="sm"
                variant="ghost"
                disabled={batchDeleteChannelsMutation.isPending}
                onClick={() => {
                  if (confirm('DİKKAT: Takip edilen TÜM kanalları silmek istediğinize emin misiniz? Bu işlem geri alınamaz.')) {
                    batchDeleteChannelsMutation.mutate({ ids: [], all: true });
                  }
                }}
                className="text-xs text-red-400 hover:text-red-300 hover:bg-red-500/10"
              >
                <Trash2 className="w-3.5 h-3.5 mr-1" />
                Hepsini Sil
              </Button>
            </div>
          )}
        </CardHeader>
        <CardContent className="pt-0">
          {channelsLoading ? (
            <div className="text-sm text-zinc-500 py-8 text-center">Kanallar yükleniyor...</div>
          ) : !channels || channels.length === 0 ? (
            <div className="text-sm text-zinc-500 py-8 text-center">Henüz takip edilen kanal yok.</div>
          ) : (
            <div className="divide-y divide-zinc-800/80 border border-zinc-800 rounded-lg overflow-hidden bg-zinc-950/40">
              {channels.map((channel: Channel) => {
                const channelKey = channel.id || channel.url;
                const isSelected = selectedChannelIds.includes(channelKey);

                return (
                  <div
                    key={channelKey}
                    className={`p-4 flex flex-col md:flex-row md:items-center justify-between gap-4 transition-colors ${
                      isSelected ? 'bg-violet-950/25' : 'hover:bg-zinc-900/40'
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => toggleSelectChannel(channelKey)}
                        className="rounded border-zinc-700 bg-zinc-900 text-violet-600 w-4 h-4 cursor-pointer mt-1"
                      />
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-sm text-zinc-100">{channel.name}</span>
                          <a
                            href={channel.url}
                            target="_blank"
                            rel="noreferrer"
                            className="text-zinc-500 hover:text-zinc-300 inline-flex items-center"
                          >
                            <ExternalLink className="w-3.5 h-3.5" />
                          </a>
                          <Badge
                            variant={channel.active !== false ? 'success' : 'secondary'}
                            className="text-[10px] py-0 px-1.5"
                          >
                            {channel.active !== false ? 'Aktif' : 'Pasif'}
                          </Badge>
                        </div>
                        <p className="text-xs text-zinc-400 font-mono">{channel.url}</p>
                      </div>
                    </div>

                    <div className="flex items-center gap-6 text-xs text-zinc-400">
                      <div className="flex items-center gap-1.5">
                        <ShieldCheck className="w-4 h-4 text-violet-400" />
                        <span>Min Skor: <strong className="text-zinc-200">{channel.min_score || 90}</strong></span>
                      </div>

                      <div className="flex items-center gap-1.5">
                        <Clock className="w-4 h-4 text-zinc-500" />
                        <span>{channel.check_interval_h ? `${channel.check_interval_h}h` : '2h'}</span>
                      </div>

                      <Badge variant={channel.auto_upload ? 'default' : 'outline'} className="text-[10px]">
                        {channel.auto_upload ? 'Oto Yayın' : 'Manuel'}
                      </Badge>

                      <div className="flex items-center gap-2">
                        <Button
                          size="sm"
                          variant="ghost"
                          className={channel.active !== false ? 'text-amber-400 hover:text-amber-300' : 'text-emerald-400 hover:text-emerald-300'}
                          onClick={() =>
                            toggleChannelMutation.mutate({
                              id: channel.id || channel.url,
                              active: channel.active === false,
                            })
                          }
                        >
                          {channel.active !== false ? 'Durdur' : 'Aktifleştir'}
                        </Button>

                        <Button
                          size="sm"
                          variant="ghost"
                          className="text-red-400 hover:text-red-300 hover:bg-red-500/10"
                          onClick={() => {
                            if (confirm(`${channel.name} kanalını takipten çıkarmak istediğinize emin misiniz?`)) {
                              deleteChannelMutation.mutate(channel.id || channel.url);
                            }
                          }}
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
