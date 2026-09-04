import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Input } from '@/components/ui/Input';
import { api } from '@/lib/api';
import { CalendarDay, Clip } from '@/types';
import { formatDuration } from '@/lib/utils';
import {
  Calendar as CalendarIcon,
  Shuffle,
  CheckCircle2,
  Trash2,
  GripVertical,
  Search,
  Plus,
  Layers,
  X,
  Sparkles,
} from 'lucide-react';

export default function Planner() {
  const queryClient = useQueryClient();
  const [poolSearch, setPoolSearch] = useState('');
  const [draggedClip, setDraggedClip] = useState<Clip | null>(null);
  const [dragOverSlotKey, setDragOverSlotKey] = useState<string | null>(null);
  const [showShuffleModal, setShowShuffleModal] = useState(false);
  const [selectedDates, setSelectedDates] = useState<Set<string>>(new Set());
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  // 1. Fetch 14-day calendar
  const { data: calendarDays, isLoading: calendarLoading } = useQuery({
    queryKey: ['calendar'],
    queryFn: () => api.queue.calendar(14),
  });

  // 2. Fetch all clips to build unassigned pool
  const { data: allClips, isLoading: clipsLoading } = useQuery({
    queryKey: ['clips'],
    queryFn: () => api.clips.list(),
  });

  // Collect assigned clip IDs
  const assignedClipIds = new Set<string>();
  calendarDays?.forEach((day) => {
    day.slots.forEach((slot) => {
      if (slot.item?.clip_id) {
        assignedClipIds.add(slot.item.clip_id);
      }
    });
  });

  // Unassigned pool clips
  const poolClips = allClips?.filter((c) => !assignedClipIds.has(c.id)) || [];
  const filteredPool = poolClips.filter(
    (c) =>
      !poolSearch ||
      c.title.toLowerCase().includes(poolSearch.toLowerCase()) ||
      (c.tags && c.tags.toLowerCase().includes(poolSearch.toLowerCase()))
  );

  // Mutations
  const addToSlotMutation = useMutation({
    mutationFn: ({ clipId, scheduledAt }: { clipId: string; scheduledAt: string }) =>
      api.queue.add({ clip_id: clipId, scheduled_at: scheduledAt }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['calendar'] });
      setStatusMsg('Klip slota başarıyla yerleştirildi.');
      setTimeout(() => setStatusMsg(null), 3000);
    },
  });

  const shuffleMutation = useMutation({
    mutationFn: (dates?: string[]) => api.queue.shuffle(dates),
    onSuccess: (res: any) => {
      queryClient.invalidateQueries({ queryKey: ['calendar'] });
      setShowShuffleModal(false);
      const msg = res?.message || 'Seçilen günlerin slotları akıllıca karıştırıldı.';
      setStatusMsg(msg);
      setTimeout(() => setStatusMsg(null), 4000);
    },
  });

  const deleteQueueMutation = useMutation({
    mutationFn: (id: string) => api.queue.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['calendar'] });
      setStatusMsg('Klip slottan çıkarılıp havuza geri alındı.');
      setTimeout(() => setStatusMsg(null), 3000);
    },
  });

  // Convert Date string + Time to ISO UTC (+3 offset)
  const computeSlotUtcIso = (dateStr: string, timeStr: string) => {
    const [h, m] = timeStr.split(':').map(Number);
    const localDt = new Date(`${dateStr}T${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:00+03:00`);
    return localDt.toISOString();
  };

  // Drag & Drop Handlers
  const handleDragStart = (clip: Clip) => {
    setDraggedClip(clip);
  };

  const handleDragOver = (e: React.DragEvent, slotKey: string) => {
    e.preventDefault();
    setDragOverSlotKey(slotKey);
  };

  const handleDragLeave = () => {
    setDragOverSlotKey(null);
  };

  const handleDrop = (dateStr: string, timeStr: string) => {
    setDragOverSlotKey(null);
    if (!draggedClip) return;
    const isoUtc = computeSlotUtcIso(dateStr, timeStr);
    addToSlotMutation.mutate({ clipId: draggedClip.id, scheduledAt: isoUtc });
    setDraggedClip(null);
  };

  const handleQuickAssign = (clip: Clip) => {
    if (!calendarDays) return;
    for (const day of calendarDays) {
      for (const slot of day.slots) {
        if (!slot.item) {
          const isoUtc = computeSlotUtcIso(day.date, slot.time);
          addToSlotMutation.mutate({ clipId: clip.id, scheduledAt: isoUtc });
          return;
        }
      }
    }
    alert('Takvimde boş slot kalmadı.');
  };

  // Date selection helpers for the Shuffle Modal
  const openShuffleModal = () => {
    // Default: select all 14 days initially
    if (calendarDays) {
      setSelectedDates(new Set(calendarDays.map((d) => d.date)));
    }
    setShowShuffleModal(true);
  };

  const toggleModalDate = (dateStr: string) => {
    const next = new Set(selectedDates);
    if (next.has(dateStr)) next.delete(dateStr);
    else next.add(dateStr);
    setSelectedDates(next);
  };

  const selectPresetDays = (type: 'all' | 'next3' | 'next7' | 'none') => {
    if (!calendarDays) return;
    if (type === 'all') setSelectedDates(new Set(calendarDays.map((d) => d.date)));
    else if (type === 'next3') setSelectedDates(new Set(calendarDays.slice(0, 3).map((d) => d.date)));
    else if (type === 'next7') setSelectedDates(new Set(calendarDays.slice(0, 7).map((d) => d.date)));
    else setSelectedDates(new Set());
  };

  const handleConfirmShuffle = () => {
    if (selectedDates.size === 0) {
      alert('Lütfen en az bir gün seçin.');
      return;
    }
    shuffleMutation.mutate(Array.from(selectedDates));
  };

  return (
    <div className="space-y-6 max-w-[1600px] pb-12">
      {/* ── Üst Başlık ve Eylemler ─────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">14 Günlük Yayın Planlayıcı</h1>
          <p className="text-zinc-400 text-sm mt-1">
            Soldaki klip havuzundan klipleri slotlara sürükleyin veya "Akıllı Dağıt" ile istediğiniz günlere paylaştırın.
          </p>
        </div>
        <div>
          <Button
            onClick={openShuffleModal}
            className="bg-violet-600 hover:bg-violet-700 text-white shadow-lg shadow-violet-600/20 text-xs"
          >
            <Shuffle className="w-3.5 h-3.5 mr-1.5" /> Akıllı Dağıt (Shuffle)
          </Button>
        </div>
      </div>

      {statusMsg && (
        <div className="bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 px-4 py-3 rounded-lg flex items-center gap-2 text-sm">
          <CheckCircle2 className="w-4 h-4" />
          <span>{statusMsg}</span>
        </div>
      )}

      {/* ── AKILLI DAĞIT GÜN SEÇİM MODALİ ──────────────────────────── */}
      {showShuffleModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <Card className="w-full max-w-2xl bg-zinc-900 border-zinc-700 shadow-2xl animate-in fade-in zoom-in-95 duration-200">
            <CardHeader className="flex flex-row items-center justify-between pb-3 border-b border-zinc-800">
              <div className="flex items-center gap-2">
                <Shuffle className="w-5 h-5 text-violet-400" />
                <div>
                  <CardTitle className="text-base font-bold text-zinc-100">Akıllı Dağıtılacak Günleri Seçin</CardTitle>
                  <p className="text-xs text-zinc-400 mt-0.5">
                    Seçtiğiniz günlerin slotları havuzdaki kliplerle kanal/skor dengesine göre doldurulur.
                  </p>
                </div>
              </div>
              <Button size="sm" variant="ghost" className="h-8 w-8 p-0 text-zinc-400 hover:text-white" onClick={() => setShowShuffleModal(false)}>
                <X className="w-4 h-4" />
              </Button>
            </CardHeader>

            <CardContent className="p-5 space-y-4">
              {/* Hızlı Seçim Butonları */}
              <div className="flex flex-wrap gap-2 text-xs">
                <Button size="sm" variant="outline" className="text-xs h-7 border-zinc-700" onClick={() => selectPresetDays('all')}>
                  Tüm 14 Gün
                </Button>
                <Button size="sm" variant="outline" className="text-xs h-7 border-zinc-700" onClick={() => selectPresetDays('next3')}>
                  İlk 3 Gün
                </Button>
                <Button size="sm" variant="outline" className="text-xs h-7 border-zinc-700" onClick={() => selectPresetDays('next7')}>
                  İlk 7 Gün
                </Button>
                <Button size="sm" variant="ghost" className="text-xs h-7 text-zinc-400 hover:text-red-400" onClick={() => selectPresetDays('none')}>
                  Seçimi Temizle
                </Button>
              </div>

              {/* Gün Kartları Izgarası */}
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2.5 max-h-[320px] overflow-y-auto p-1">
                {calendarDays?.map((day) => {
                  const isSelected = selectedDates.has(day.date);
                  return (
                    <div
                      key={day.date}
                      onClick={() => toggleModalDate(day.date)}
                      className={`p-3 rounded-lg border text-center cursor-pointer select-none transition-all ${
                        isSelected
                          ? 'bg-violet-600 text-white border-violet-500 shadow-md shadow-violet-600/30 scale-[1.02]'
                          : 'bg-zinc-950/70 border-zinc-800 text-zinc-300 hover:border-zinc-700 hover:bg-zinc-800/60'
                      }`}
                    >
                      <p className="text-xs font-bold truncate">{day.label}</p>
                      <span className="text-[10px] font-mono opacity-70 block mt-0.5">{day.date}</span>
                    </div>
                  );
                })}
              </div>

              {/* Modal Alt Çubuk */}
              <div className="flex items-center justify-between pt-3 border-t border-zinc-800">
                <span className="text-xs text-zinc-400">
                  <strong className="text-violet-400">{selectedDates.size}</strong> gün seçildi ({selectedDates.size * 4} Slot)
                </span>
                <div className="flex gap-2">
                  <Button size="sm" variant="ghost" onClick={() => setShowShuffleModal(false)}>
                    İptal
                  </Button>
                  <Button
                    size="sm"
                    disabled={selectedDates.size === 0 || shuffleMutation.isPending}
                    onClick={handleConfirmShuffle}
                    className="bg-violet-600 hover:bg-violet-700 text-white"
                  >
                    {shuffleMutation.isPending ? 'Dağıtılıyor...' : 'Dağıtımı Başlat'}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ── İki Kolonlu Planlayıcı Gövdesi (Havuz + Takvim) ─────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* ── SOL KOLON: KLİP HAVUZU (4/12) ─────────────────────────── */}
        <Card className="lg:col-span-4 bg-zinc-900/90 border-zinc-800 sticky top-4 shadow-xl">
          <CardHeader className="p-4 pb-3 border-b border-zinc-800 flex flex-row items-center justify-between">
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-violet-400" />
              <CardTitle className="text-base font-bold">Klip Havuzu</CardTitle>
              <Badge variant="secondary" className="text-xs">
                {poolClips.length} Hazır
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="p-4 space-y-3">
            {/* Havuz Arama */}
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-500" />
              <Input
                placeholder="Havuzda ara..."
                value={poolSearch}
                onChange={(e) => setPoolSearch(e.target.value)}
                className="pl-8 h-9 text-xs bg-zinc-950/80 border-zinc-800"
              />
            </div>

            {/* Havuz Listesi */}
            {clipsLoading ? (
              <div className="text-xs text-zinc-500 py-8 text-center">Klipler yükleniyor...</div>
            ) : filteredPool.length === 0 ? (
              <div className="text-xs text-zinc-500 py-12 text-center border border-dashed border-zinc-800/80 rounded-lg">
                {poolClips.length === 0 ? 'Havuzda bekleyen klip yok. Yeni analiz başlatın.' : 'Eşleşen klip bulunamadı.'}
              </div>
            ) : (
              <div className="space-y-2 max-h-[calc(100vh-280px)] overflow-y-auto pr-1">
                {filteredPool.map((clip) => (
                  <div
                    key={clip.id}
                    draggable
                    onDragStart={() => handleDragStart(clip)}
                    className="p-2.5 rounded-lg border border-zinc-800 bg-zinc-950/70 hover:border-violet-500/60 hover:bg-zinc-900/80 cursor-grab active:cursor-grabbing transition-all group flex items-center justify-between gap-2.5 shadow-sm"
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <GripVertical className="w-4 h-4 text-zinc-600 group-hover:text-violet-400 shrink-0" />
                      {clip.thumbnail_path && (
                        <img
                          src={api.clips.thumbnailUrl(clip.id)}
                          alt={clip.title}
                          className="w-12 h-8 rounded object-cover shrink-0 bg-zinc-900"
                        />
                      )}
                      <div className="min-w-0 space-y-0.5">
                        <p className="text-xs font-semibold text-zinc-200 line-clamp-1 group-hover:text-violet-300">
                          {clip.title}
                        </p>
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] font-mono text-zinc-500">
                            {clip.duration ? formatDuration(clip.duration) : ''}
                          </span>
                          <Badge
                            variant={clip.score >= 80 ? 'success' : 'warning'}
                            className="text-[9px] py-0 px-1"
                          >
                            Skor: {clip.score}
                          </Badge>
                        </div>
                      </div>
                    </div>

                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 w-7 p-0 shrink-0 text-zinc-500 hover:text-violet-400 hover:bg-violet-600/10"
                      title="Sıradaki Boş Slota Ekle"
                      onClick={() => handleQuickAssign(clip)}
                    >
                      <Plus className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* ── SAĞ KOLON: 14 GÜNLÜK TAKVİM (8/12) ────────────────────── */}
        <div className="lg:col-span-8 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-bold text-zinc-200 flex items-center gap-2">
              <CalendarIcon className="w-4 h-4 text-violet-400" />
              14 Günlük Takvim ({calendarDays?.length || 0} Gün)
            </h2>
            <div className="flex items-center gap-3 text-xs text-zinc-400">
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-violet-500 inline-block" /> 11:30 / 15:30 / 19:00 / 22:30 Slotları
              </span>
            </div>
          </div>

          {calendarLoading ? (
            <div className="text-sm text-zinc-500 py-16 text-center">Takvim yükleniyor...</div>
          ) : !calendarDays || calendarDays.length === 0 ? (
            <div className="text-sm text-zinc-500 py-16 text-center">Takvim verisi bulunamadı.</div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {calendarDays.map((day: CalendarDay) => (
                <Card key={day.date} className="border-zinc-800 bg-zinc-900/80 shadow-md flex flex-col">
                  <CardHeader className="p-3 pb-2 border-b border-zinc-800/80 flex flex-row items-center justify-between">
                    <div>
                      <CardTitle className="text-xs font-bold text-zinc-100">{day.label}</CardTitle>
                      <span className="text-[10px] font-mono text-zinc-500">{day.date}</span>
                    </div>
                    <Badge variant="outline" className="text-[9px] py-0 px-1.5">
                      {day.slots.filter((s) => s.item).length} / 4 Dolu
                    </Badge>
                  </CardHeader>

                  <CardContent className="p-2.5 space-y-2 flex-1">
                    {day.slots.map((slot) => {
                      const item = slot.item;
                      const slotKey = `${day.date}-${slot.time}`;
                      const isDragOver = dragOverSlotKey === slotKey;

                      return (
                        <div
                          key={slot.time}
                          onDragOver={(e) => handleDragOver(e, slotKey)}
                          onDragLeave={handleDragLeave}
                          onDrop={() => handleDrop(day.date, slot.time)}
                          className={`p-2 rounded-lg border text-xs transition-all relative ${
                            isDragOver
                              ? 'border-violet-500 bg-violet-600/20 ring-2 ring-violet-500/50 scale-[1.02]'
                              : item
                              ? 'bg-zinc-950/90 border-zinc-800 hover:border-zinc-700'
                              : 'bg-zinc-950/30 border-dashed border-zinc-800/70 text-zinc-500 hover:border-violet-500/40'
                          }`}
                        >
                          <div className="flex items-center justify-between mb-1">
                            <span className="font-mono text-[11px] font-bold text-violet-400">{slot.time}</span>
                            {item && item.viral_score !== undefined && (
                              <Badge
                                variant={(item.viral_score ?? 0) >= 80 ? 'success' : 'warning'}
                                className="text-[9px] py-0 px-1"
                              >
                                Skor: {item.viral_score}
                              </Badge>
                            )}
                          </div>

                          {item ? (
                            <div className="space-y-1">
                              <p className="font-medium text-zinc-200 line-clamp-1 text-[11px]" title={item.title}>
                                {item.title}
                              </p>
                              <div className="flex items-center justify-between pt-0.5">
                                <span
                                  className={`text-[9px] font-bold uppercase ${
                                    String(item.status).toUpperCase() === 'PUBLISHED' ? 'text-emerald-400' : 'text-amber-400'
                                  }`}
                                >
                                  {item.status || 'SCHEDULED'}
                                </span>
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  className="h-5 px-1 text-[10px] text-zinc-500 hover:text-red-400"
                                  onClick={() => deleteQueueMutation.mutate(item.id)}
                                >
                                  <Trash2 className="w-3 h-3 mr-0.5" /> Çıkar
                                </Button>
                              </div>
                            </div>
                          ) : (
                            <div className="text-[10px] text-zinc-500 text-center py-1">
                              {isDragOver ? '✨ Buraya Bırak' : '+ Klip Sürükle veya Ekle'}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
