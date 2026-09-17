import { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { formatDuration } from '@/lib/utils';
import { Search, Film, Play, Trash2, X, CheckCircle2, Upload, Image as ImageIcon } from 'lucide-react';

const CATEGORIES = ['Tümü', 'CLUTCH', 'FAIL', 'FUNNY', 'FAIL/FUNNY', 'RAGE/REACTION', 'JUMPSCARE', 'EPIC_MOMENT', 'STORY', 'MUNDANE'];
const SCORE_BANDS = ['Tümü', 'Yüksek', 'Orta-Yüksek', 'Orta', 'Düşük'];
const PUBLISH_STATUSES = ['Tümü', 'Yeniler (İşlenmemiş)', 'Takvimde', 'Yayınlananlar'];

export default function Clips() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('Tümü');
  const [scoreBand, setScoreBand] = useState('Tümü');
  const [publishFilter, setPublishFilter] = useState('Tümü');
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showThumbnailModal, setShowThumbnailModal] = useState(false);
  const [selectedClipIds, setSelectedClipIds] = useState<Set<string>>(new Set());
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [uploadingVideoId, setUploadingVideoId] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const selectedVideoIdRef = useRef<string | null>(null);

  const { data: clips, isLoading } = useQuery({
    queryKey: ['clips'],
    queryFn: () => api.clips.list(),
  });

  const { data: videos } = useQuery({
    queryKey: ['videos'],
    queryFn: () => api.videos.list(),
  });

  const uploadVideoThumbMutation = useMutation({
    mutationFn: ({ videoId, file }: { videoId: string; file: File }) =>
      api.videos.uploadThumbnail(videoId, file),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['clips'] });
      queryClient.invalidateQueries({ queryKey: ['videos'] });
      queryClient.invalidateQueries({ queryKey: ['calendar'] });
      setUploadingVideoId(null);
      setStatusMsg(`Kapak güncellendi! Bu videonun ${res.updated_clips_count} klibine yeni kapak atandı.`);
      setTimeout(() => setStatusMsg(null), 4000);
    },
    onError: (err: any) => {
      setUploadingVideoId(null);
      setStatusMsg(`Hata: ${err.message || 'Kapak yüklenemedi'}`);
    },
  });

  const batchDeleteMutation = useMutation({
    mutationFn: (ids: string[]) => api.clips.batchDelete(ids),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['clips'] });
      queryClient.invalidateQueries({ queryKey: ['calendar'] });
      setShowDeleteModal(false);
      setSelectedClipIds(new Set());
      setStatusMsg(`${res?.deleted_count || 0} klip başarıyla silindi.`);
      setTimeout(() => setStatusMsg(null), 3000);
    },
  });

  const filteredClips = clips?.filter((clip) => {
    const matchesSearch =
      !search ||
      clip.title.toLowerCase().includes(search.toLowerCase()) ||
      (clip.description && clip.description.toLowerCase().includes(search.toLowerCase())) ||
      (clip.rationale && clip.rationale.toLowerCase().includes(search.toLowerCase()));
    const matchesCategory = category === 'Tümü' || clip.category === category;
    const matchesScoreBand =
      scoreBand === 'Tümü' ||
      clip.score_band === scoreBand ||
      (!clip.score_band && (
        (scoreBand === 'Yüksek' && clip.score >= 75) ||
        (scoreBand === 'Orta-Yüksek' && clip.score >= 55 && clip.score < 75) ||
        (scoreBand === 'Orta' && clip.score >= 35 && clip.score < 55) ||
        (scoreBand === 'Düşük' && clip.score < 35)
      ));
    
    const pStat = clip.publish_status || 'new';
    const matchesPublish =
      publishFilter === 'Tümü' ||
      (publishFilter === 'Yeniler (İşlenmemiş)' && (!clip.publish_status || pStat === 'new' || pStat === 'pool')) ||
      (publishFilter === 'Takvimde' && pStat === 'scheduled') ||
      (publishFilter === 'Yayınlananlar' && pStat === 'published');

    return matchesSearch && matchesCategory && matchesScoreBand && matchesPublish;
  });

  const openDeleteModal = () => {
    setSelectedClipIds(new Set());
    setShowDeleteModal(true);
  };

  const toggleClipSelection = (id: string) => {
    const next = new Set(selectedClipIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelectedClipIds(next);
  };

  const selectPreset = (type: 'all' | 'lowScore' | 'none') => {
    if (!clips) return;
    if (type === 'all') {
      setSelectedClipIds(new Set(clips.map((c) => c.id)));
    } else if (type === 'lowScore') {
      setSelectedClipIds(new Set(clips.filter((c) => (c.score || 0) < 80).map((c) => c.id)));
    } else {
      setSelectedClipIds(new Set());
    }
  };

  const handleConfirmDelete = () => {
    if (selectedClipIds.size === 0) return;
    if (confirm(`${selectedClipIds.size} klibi kalıcı olarak silmek istediğinize emin misiniz?`)) {
      batchDeleteMutation.mutate(Array.from(selectedClipIds));
    }
  };

  const triggerUploadForVideo = (videoId: string) => {
    selectedVideoIdRef.current = videoId;
    fileInputRef.current?.click();
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    const vid = selectedVideoIdRef.current;
    if (file && vid) {
      setUploadingVideoId(vid);
      uploadVideoThumbMutation.mutate({ videoId: vid, file });
    }
    e.target.value = '';
  };

  return (
    <div className="space-y-6 max-w-7xl pb-12">
      <input
        ref={fileInputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        className="hidden"
        onChange={handleFileChange}
      />

      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Klip Kütüphanesi</h1>
          <p className="text-zinc-400 text-sm mt-1">
            Üretilen tüm dikey ve yatay oyun anları ({clips?.length || 0} Klip)
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            onClick={() => setShowThumbnailModal(true)}
            className="text-xs border-violet-500/30 text-violet-300 hover:bg-violet-500/10 hover:border-violet-500/50"
          >
            <ImageIcon className="w-3.5 h-3.5 mr-1.5" /> Video Kapağı Yükle
          </Button>

          <Button
            variant="outline"
            onClick={openDeleteModal}
            disabled={!clips || clips.length === 0}
            className="text-xs border-red-500/30 text-red-400 hover:bg-red-500/10 hover:border-red-500/50"
          >
            <Trash2 className="w-3.5 h-3.5 mr-1.5" /> Klipleri Sil
          </Button>
        </div>
      </div>

      {statusMsg && (
        <div className="bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 px-4 py-3 rounded-lg flex items-center gap-2 text-sm">
          <CheckCircle2 className="w-4 h-4" />
          <span>{statusMsg}</span>
        </div>
      )}

      {/* ── TOPLU SİLME MODALİ ───────────────────────────────────────── */}
      {showDeleteModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <Card className="w-full max-w-3xl bg-zinc-900 border-zinc-700 shadow-2xl animate-in fade-in zoom-in-95 duration-200">
            <CardHeader className="flex flex-row items-center justify-between pb-3 border-b border-zinc-800">
              <div className="flex items-center gap-2">
                <Trash2 className="w-5 h-5 text-red-400" />
                <div>
                  <CardTitle className="text-base font-bold text-zinc-100">Silinecek Klipleri Seçin</CardTitle>
                  <p className="text-xs text-zinc-400 mt-0.5">
                    Seçtiğiniz klipler veritabanından ve diskten kalıcı olarak silinecektir.
                  </p>
                </div>
              </div>
              <Button size="sm" variant="ghost" className="h-8 w-8 p-0 text-zinc-400 hover:text-white" onClick={() => setShowDeleteModal(false)}>
                <X className="w-4 h-4" />
              </Button>
            </CardHeader>

            <CardContent className="p-5 space-y-4">
              {/* Hızlı Seçim Butonları */}
              <div className="flex flex-wrap gap-2 text-xs">
                <Button size="sm" variant="outline" className="text-xs h-7 border-zinc-700" onClick={() => selectPreset('all')}>
                  Tümünü Seç ({clips?.length || 0})
                </Button>
                <Button size="sm" variant="outline" className="text-xs h-7 border-zinc-700" onClick={() => selectPreset('lowScore')}>
                  Düşük Skorlular (&lt; 80)
                </Button>
                <Button size="sm" variant="ghost" className="text-xs h-7 text-zinc-400 hover:text-red-400" onClick={() => selectPreset('none')}>
                  Seçimi Temizle
                </Button>
              </div>

              {/* Klip Izgarası */}
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 max-h-[380px] overflow-y-auto p-1">
                {clips?.map((clip) => {
                  const isSelected = selectedClipIds.has(clip.id);
                  return (
                    <div
                      key={clip.id}
                      onClick={() => toggleClipSelection(clip.id)}
                      className={`p-2.5 rounded-lg border cursor-pointer select-none transition-all flex flex-col justify-between ${
                        isSelected
                          ? 'bg-red-950/40 border-red-500 text-red-200 ring-1 ring-red-500/50 scale-[1.02]'
                          : 'bg-zinc-950/70 border-zinc-800 text-zinc-300 hover:border-zinc-700 hover:bg-zinc-800/60'
                      }`}
                    >
                      <div className="aspect-video bg-zinc-900 rounded overflow-hidden relative mb-2">
                        {clip.thumbnail_path ? (
                          <img
                            src={api.clips.thumbnailUrl(clip.id)}
                            alt={clip.title}
                            className="w-full h-full object-cover"
                          />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center">
                            <Play className="w-6 h-6 text-zinc-700" />
                          </div>
                        )}
                        <div className="absolute top-1.5 right-1.5">
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => {}}
                            className="rounded border-zinc-700 bg-zinc-950 text-red-600 focus:ring-red-500 cursor-pointer"
                          />
                        </div>
                      </div>

                      <div>
                        <p className="text-xs font-semibold line-clamp-1">{clip.title}</p>
                        <div className="flex items-center justify-between mt-1 text-[10px] text-zinc-500">
                          <span>{clip.duration ? formatDuration(clip.duration) : ''}</span>
                          <Badge variant={clip.score >= 80 ? 'success' : 'warning'} className="text-[9px] py-0 px-1">
                            Skor: {clip.score}
                          </Badge>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Modal Alt Çubuk */}
              <div className="flex items-center justify-between pt-3 border-t border-zinc-800">
                <span className="text-xs text-zinc-400">
                  <strong className="text-red-400">{selectedClipIds.size}</strong> klip seçildi
                </span>
                <div className="flex gap-2">
                  <Button size="sm" variant="ghost" onClick={() => setShowDeleteModal(false)}>
                    İptal
                  </Button>
                  <Button
                    size="sm"
                    disabled={selectedClipIds.size === 0 || batchDeleteMutation.isPending}
                    onClick={handleConfirmDelete}
                    className="bg-red-600 hover:bg-red-700 text-white"
                  >
                    {batchDeleteMutation.isPending ? 'Siliniyor...' : 'Seçilen Klipleri Sil'}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ── VİDEO KAPAĞI YÖNETİM MODALİ ───────────────────────────── */}
      {showThumbnailModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <Card className="w-full max-w-3xl bg-zinc-900 border-zinc-700 shadow-2xl animate-in fade-in zoom-in-95 duration-200">
            <CardHeader className="flex flex-row items-center justify-between pb-3 border-b border-zinc-800">
              <div className="flex items-center gap-2">
                <ImageIcon className="w-5 h-5 text-violet-400" />
                <div>
                  <CardTitle className="text-base font-bold text-zinc-100">Video Kapak Görselleri</CardTitle>
                  <p className="text-xs text-zinc-400 mt-0.5">
                    Bir videoya kapak yüklediğinizde, o videodan çıkan tüm klipler otomatik olarak güncellenir.
                  </p>
                </div>
              </div>
              <Button size="sm" variant="ghost" className="h-8 w-8 p-0 text-zinc-400 hover:text-white" onClick={() => setShowThumbnailModal(false)}>
                <X className="w-4 h-4" />
              </Button>
            </CardHeader>

            <CardContent className="p-5 space-y-4">
              {!videos || videos.length === 0 ? (
                <div className="text-center py-10 text-zinc-500 text-xs">
                  Henüz işlenmiş bir video bulunamadı.
                </div>
              ) : (
                <div className="space-y-3 max-h-[420px] overflow-y-auto p-1">
                  {videos.map((vid) => {
                    const vidClips = clips?.filter((c) => c.video_id === vid.id) || [];
                    const sampleClip = vidClips[0];
                    const isUploading = uploadingVideoId === vid.id;

                    return (
                      <div
                        key={vid.id}
                        className="p-3.5 rounded-xl border border-zinc-800 bg-zinc-950/70 hover:border-zinc-700 flex items-center justify-between gap-4 transition-colors"
                      >
                        <div className="flex items-center gap-3.5 min-w-0">
                          <div className="w-16 h-24 rounded-lg overflow-hidden border border-zinc-800 bg-black flex-shrink-0 relative group">
                            {sampleClip?.thumbnail_path ? (
                              <img
                                src={`${api.clips.thumbnailUrl(sampleClip.id)}?t=${Date.now()}`}
                                alt={vid.title || 'Video'}
                                className="w-full h-full object-cover"
                              />
                            ) : (
                              <div className="w-full h-full flex items-center justify-center text-zinc-600 text-[10px]">
                                Yok
                              </div>
                            )}
                          </div>

                          <div className="min-w-0">
                            <h4 className="text-sm font-semibold text-zinc-100 line-clamp-1">{vid.title || vid.id}</h4>
                            <div className="flex items-center gap-2 mt-1 text-xs text-zinc-400">
                              <span className="font-medium text-violet-300">{vid.uploader || 'Yayıncı'}</span>
                              <span>•</span>
                              <Badge variant="secondary" className="text-[10px] py-0 px-1.5 font-mono">
                                {vidClips.length} Klip
                              </Badge>
                            </div>
                            <p className="text-[11px] text-zinc-500 mt-1">
                              ID: <span className="font-mono">{vid.id}</span>
                            </p>
                          </div>
                        </div>

                        <div className="flex-shrink-0">
                          <Button
                            size="sm"
                            variant="outline"
                            className="text-xs border-violet-500/40 text-violet-300 hover:bg-violet-500/10 hover:border-violet-500/60"
                            disabled={isUploading}
                            onClick={() => triggerUploadForVideo(vid.id)}
                          >
                            <Upload className="w-3.5 h-3.5 mr-1.5" />
                            {isUploading ? 'Yükleniyor...' : 'Yeni Kapak Yükle'}
                          </Button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              <div className="flex justify-end pt-2 border-t border-zinc-800">
                <Button size="sm" variant="ghost" onClick={() => setShowThumbnailModal(false)}>
                  Kapat
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ── Filtreleme ve Arama Çubuğu ──────────────────────────────── */}
      <div className="space-y-3">
        <div className="flex flex-col sm:flex-row gap-3 items-center justify-between">
          <div className="relative w-full sm:w-80">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
            <Input
              placeholder="Klip başlığı veya anahtar kelime..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9 h-10 text-xs bg-zinc-900/80 border-zinc-800"
            />
          </div>

          <div className="flex gap-1.5 overflow-x-auto w-full sm:w-auto pb-1 sm:pb-0">
            {CATEGORIES.map((cat) => (
              <Button
                key={cat}
                size="sm"
                variant={category === cat ? 'default' : 'outline'}
                className={`text-xs h-8 px-3 ${category === cat ? 'bg-violet-600 hover:bg-violet-700' : 'border-zinc-800 text-zinc-400'}`}
                onClick={() => setCategory(cat)}
              >
                {cat}
              </Button>
            ))}
          </div>
        </div>

        {/* Skor Bandı Filtre Butonları */}
        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          <span className="text-[11px] font-medium text-zinc-500 uppercase tracking-wider whitespace-nowrap">Bant:</span>
          {SCORE_BANDS.map((sb) => (
            <button
              key={sb}
              onClick={() => setScoreBand(sb)}
              className={`text-xs px-2.5 py-1 rounded-full border transition-colors whitespace-nowrap ${
                scoreBand === sb
                  ? 'bg-violet-500/20 border-violet-500/50 text-violet-300 font-medium'
                  : 'bg-zinc-900/60 border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200'
              }`}
            >
              {sb}
            </button>
          ))}
        </div>

        {/* Yayın Durumu Filtre Butonları */}
        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          <span className="text-[11px] font-medium text-zinc-500 uppercase tracking-wider whitespace-nowrap">Durum:</span>
          {PUBLISH_STATUSES.map((ps) => (
            <button
              key={ps}
              onClick={() => setPublishFilter(ps)}
              className={`text-xs px-2.5 py-1 rounded-full border transition-colors whitespace-nowrap ${
                publishFilter === ps
                  ? 'bg-blue-500/20 border-blue-500/50 text-blue-300 font-medium'
                  : 'bg-zinc-900/60 border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200'
              }`}
            >
              {ps}
            </button>
          ))}
        </div>
      </div>

      {/* ── Klip Kartları Izgarası ──────────────────────────────────── */}
      {isLoading ? (
        <div className="text-sm text-zinc-500 py-16 text-center">Klipler yükleniyor...</div>
      ) : !filteredClips || filteredClips.length === 0 ? (
        <div className="text-center py-16 bg-zinc-900/40 rounded-xl border border-zinc-800">
          <Film className="w-10 h-10 text-zinc-600 mx-auto mb-3" />
          <p className="text-zinc-300 font-semibold text-sm">Eşleşen Klip Bulunamadı</p>
          <p className="text-xs text-zinc-500 mt-1">Arama kriterlerinizi değiştirebilir veya yeni analiz başlatabilirsiniz.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {filteredClips.map((clip) => (
            <div
              key={clip.id}
              onClick={() => (window.location.href = `/clips/${clip.id}`)}
              className="cursor-pointer"
            >
              <Card className="hover:border-violet-500/50 transition-colors overflow-hidden group bg-zinc-900/80 border-zinc-800 h-full flex flex-col justify-between">
                <div className="aspect-video bg-zinc-950 relative flex items-center justify-center">
                  {clip.thumbnail_path ? (
                    <img
                      src={api.clips.thumbnailUrl(clip.id)}
                      alt={clip.title}
                      onError={(e) => {
                        e.currentTarget.style.display = 'none';
                      }}
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                    />
                  ) : (
                    <Play className="w-8 h-8 text-zinc-700 group-hover:text-violet-500 transition-colors" />
                  )}
                  {clip.duration && (
                    <div className="absolute bottom-2 right-2 bg-black/80 px-1.5 py-0.5 text-[10px] rounded font-mono text-zinc-300">
                      {formatDuration(clip.duration)}
                    </div>
                  )}
                  
                  {/* Yayın Durumu Etiketi */}
                  <div className="absolute top-2 left-2 flex flex-col gap-1">
                    {(!clip.publish_status || clip.publish_status === 'new' || clip.publish_status === 'pool') && (
                      <Badge variant="outline" className="text-[9px] px-1 py-0 bg-black/70 border-zinc-500/40 text-zinc-300">Yeni</Badge>
                    )}
                    {clip.publish_status === 'scheduled' && (
                      <Badge variant="outline" className="text-[9px] px-1 py-0 bg-black/70 border-blue-500/40 text-blue-300">Takvimde</Badge>
                    )}
                    {clip.publish_status === 'published' && (
                      <Badge variant="outline" className="text-[9px] px-1 py-0 bg-black/70 border-emerald-500/40 text-emerald-300">Yayınlandı</Badge>
                    )}
                  </div>

                  <div className="absolute top-2 right-2 flex items-center gap-1">
                    {clip.score_band && (
                      <Badge variant="outline" className="text-[9px] px-1 py-0 bg-black/70 border-violet-500/40 text-violet-300">
                        {clip.score_band}
                      </Badge>
                    )}
                    <Badge variant={clip.score >= 80 ? 'success' : clip.score >= 55 ? 'warning' : 'destructive'} className="text-[10px]">
                      {clip.score}
                    </Badge>
                  </div>
                </div>
                <CardContent className="p-3">
                  <h3 className="font-semibold text-xs text-zinc-200 group-hover:text-violet-300 transition-colors line-clamp-2">
                    {clip.title}
                  </h3>
                  {clip.rationale && (
                    <p className="text-[10px] text-zinc-400 mt-1 line-clamp-1 italic">
                      "{clip.rationale}"
                    </p>
                  )}
                  <div className="flex items-center justify-between mt-2 pt-2 border-t border-zinc-800 text-[10px] text-zinc-500">
                    <span className="font-mono text-violet-300/80">{clip.category || 'EPIC_MOMENT'}</span>
                    <span>{clip.created_at ? new Date(clip.created_at).toLocaleDateString('tr-TR') : ''}</span>
                  </div>
                </CardContent>
              </Card>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
