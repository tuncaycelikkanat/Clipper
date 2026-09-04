import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Badge } from '@/components/ui/Badge';
import { api } from '@/lib/api';
import { Channel } from '@/types';
import { Bot, Play, Square, Plus, Trash2, ExternalLink, Clock, ShieldCheck, CheckCircle2 } from 'lucide-react';

export default function AutoPilot() {
  const queryClient = useQueryClient();
  const [showAddModal, setShowAddModal] = useState(false);
  const [newUrl, setNewUrl] = useState('');
  const [newName, setNewName] = useState('');
  const [newMinScore, setNewMinScore] = useState(90);
  const [newAutoUpload, setNewAutoUpload] = useState(true);
  const [newInterval, setNewInterval] = useState(2.0);
  const [newPlaylist, setNewPlaylist] = useState('');
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  // 1. Fetch tracked channels
  const { data: channels, isLoading: channelsLoading } = useQuery({
    queryKey: ['channels'],
    queryFn: () => api.channels.list(),
  });

  // 2. Fetch Scheduler status
  const { data: schedulerStatus, refetch: refetchScheduler } = useQuery({
    queryKey: ['scheduler-status'],
    queryFn: () => api.scheduler.status(),
    refetchInterval: 5000,
  });

  // Mutations
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

  const isRunning = schedulerStatus?.running ?? false;

  return (
    <div className="space-y-8 max-w-6xl pb-12">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">AutoPilot Otonom Motoru</h1>
          <p className="text-zinc-400 text-sm mt-1">
            YouTube kanallarını periyodik tarar, yeni videoları tespit eder ve otomatik klip üretir.
          </p>
        </div>
        <Button onClick={() => setShowAddModal(true)} className="bg-violet-600 hover:bg-violet-700">
          <Plus className="w-4 h-4 mr-1.5" /> Yeni Kanal Ekle
        </Button>
      </div>

      {statusMsg && (
        <div className="bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 px-4 py-3 rounded-lg flex items-center gap-2 text-sm">
          <CheckCircle2 className="w-4 h-4" />
          <span>{statusMsg}</span>
        </div>
      )}

      {/* ── 1. Daemon Durumu ve Kontrol Kartı ────────────────────────── */}
      <Card className="border-zinc-800 bg-zinc-900/90">
        <CardHeader className="flex flex-row items-center justify-between pb-3">
          <div className="flex items-center gap-3">
            <div
              className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                isRunning ? 'bg-emerald-500/10 text-emerald-400' : 'bg-zinc-800 text-zinc-400'
              }`}
            >
              <Bot className="w-5 h-5" />
            </div>
            <div>
              <CardTitle className="text-base">Arka Plan Otomasyon Servisi</CardTitle>
              <p className="text-xs text-zinc-400 mt-0.5">
                {isRunning ? 'Tüm aktif kanallar otomatik kontrol ediliyor.' : 'Servis durduruldu. Manuel başlatabilirsiniz.'}
              </p>
            </div>
          </div>
          <Badge variant={isRunning ? 'success' : 'secondary'} className="px-3 py-1 text-xs">
            {isRunning ? '● Çalışıyor' : 'Durduruldu'}
          </Badge>
        </CardHeader>
        <CardContent className="pt-2">
          <div className="flex flex-wrap items-center justify-between gap-4 bg-zinc-950/70 p-4 rounded-lg border border-zinc-800/80">
            <div className="grid grid-cols-2 md:grid-cols-3 gap-6 text-sm">
              <div>
                <span className="text-xs text-zinc-500 block">Kontrol Sıklığı</span>
                <span className="font-semibold text-zinc-200">
                  {schedulerStatus?.interval_hours ? `${schedulerStatus.interval_hours} Saatte bir` : '2 Saatte bir'}
                </span>
              </div>
              <div>
                <span className="text-xs text-zinc-500 block">Tamamlanan Döngü</span>
                <span className="font-semibold text-zinc-200">{schedulerStatus?.cycle_count ?? 0}</span>
              </div>
              <div>
                <span className="text-xs text-zinc-500 block">Son Tarama</span>
                <span className="font-semibold text-zinc-200">
                  {schedulerStatus?.last_run ? new Date(schedulerStatus.last_run).toLocaleTimeString() : 'Henüz yok'}
                </span>
              </div>
            </div>

            <div className="flex gap-2">
              {!isRunning ? (
                <Button
                  className="bg-emerald-600 hover:bg-emerald-700 text-white"
                  onClick={() => startSchedulerMutation.mutate(2.0)}
                >
                  <Play className="w-4 h-4 mr-1.5 fill-current" /> Otomasyonu Başlat
                </Button>
              ) : (
                <Button
                  variant="destructive"
                  onClick={() => stopSchedulerMutation.mutate()}
                >
                  <Square className="w-4 h-4 mr-1.5 fill-current" /> Otomasyonu Durdur
                </Button>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

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
        <CardHeader className="flex flex-row items-center justify-between pb-3">
          <div>
            <CardTitle className="text-base">Takip Edilen Kanallar ({channels?.length || 0})</CardTitle>
            <p className="text-xs text-zinc-400 mt-0.5">Çift katmanlı anchor sistemi ile taranan kanallar</p>
          </div>
        </CardHeader>
        <CardContent className="pt-0">
          {channelsLoading ? (
            <div className="text-sm text-zinc-500 py-8 text-center">Kanallar yükleniyor...</div>
          ) : !channels || channels.length === 0 ? (
            <div className="text-sm text-zinc-500 py-8 text-center">Henüz takip edilen kanal yok.</div>
          ) : (
            <div className="divide-y divide-zinc-800/80 border border-zinc-800 rounded-lg overflow-hidden bg-zinc-950/40">
              {channels.map((channel: Channel) => (
                <div
                  key={channel.id || channel.url}
                  className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-4 hover:bg-zinc-900/40 transition-colors"
                >
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
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
