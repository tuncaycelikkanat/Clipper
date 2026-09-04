import { useState, useEffect, useRef } from 'react';
import { useParams } from '@tanstack/react-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Youtube, Instagram, Share2, Trash2, Save, CheckCircle2, AlertCircle, ArrowLeft, Upload, Image as ImageIcon } from 'lucide-react';
import { formatDuration } from '@/lib/utils';

export default function ClipDetail() {
  const { clipId } = useParams({ strict: false }) as { clipId: string };
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [tags, setTags] = useState('');
  const [statusMsg, setStatusMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const { data: clip, isLoading } = useQuery({
    queryKey: ['clip', clipId],
    queryFn: () => api.clips.get(clipId),
  });

  useEffect(() => {
    if (clip) {
      setTitle(clip.title || '');
      setDescription(clip.description || '');
      setTags(clip.tags || '');
    }
  }, [clip]);

  // Mutations
  const updateClipMutation = useMutation({
    mutationFn: (body: any) => api.clips.update(clipId, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clip', clipId] });
      queryClient.invalidateQueries({ queryKey: ['clips'] });
      setStatusMsg({ type: 'success', text: 'Klip detayları güncellendi.' });
      setTimeout(() => setStatusMsg(null), 4000);
    },
  });

  const uploadThumbMutation = useMutation({
    mutationFn: (file: File) => api.clips.uploadVideoThumbnail(clipId, file),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['clip', clipId] });
      queryClient.invalidateQueries({ queryKey: ['clips'] });
      queryClient.invalidateQueries({ queryKey: ['calendar'] });
      setStatusMsg({
        type: 'success',
        text: `Videonun kapağı güncellendi! Bu videodan çıkan tüm ${res.updated_clips_count} klip bu kapağı kullanacak.`,
      });
      setTimeout(() => setStatusMsg(null), 5000);
    },
    onError: (err: any) => {
      setStatusMsg({ type: 'error', text: err.message || 'Kapak yükleme hatası.' });
    },
  });

  const uploadYtMutation = useMutation({
    mutationFn: () => api.upload.youtube(clipId),
    onSuccess: (res: any) => {
      setStatusMsg({ type: 'success', text: `YouTube Shorts yüklendi! ${res.youtube_url || ''}` });
    },
    onError: (err: any) => {
      setStatusMsg({ type: 'error', text: err.message || 'YouTube yükleme hatası.' });
    },
  });

  const uploadIgMutation = useMutation({
    mutationFn: () => api.upload.instagram(clipId),
    onSuccess: (res: any) => {
      setStatusMsg({ type: 'success', text: `Instagram Reels yüklendi! ${res.instagram_url || ''}` });
    },
    onError: (err: any) => {
      setStatusMsg({ type: 'error', text: err.message || 'Instagram yükleme hatası.' });
    },
  });

  const addToQueueMutation = useMutation({
    mutationFn: () => api.queue.add({ clip_id: clipId }),
    onSuccess: () => {
      setStatusMsg({ type: 'success', text: 'Klip yayın takvimine eklendi.' });
      setTimeout(() => setStatusMsg(null), 4000);
    },
  });

  const deleteClipMutation = useMutation({
    mutationFn: () => api.clips.delete(clipId),
    onSuccess: () => {
      window.location.href = '/clips';
    },
  });

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      uploadThumbMutation.mutate(file);
      e.target.value = '';
    }
  };

  if (isLoading) return <div className="text-zinc-400 py-12 text-center">Klip yükleniyor...</div>;
  if (!clip) return <div className="text-zinc-400 py-12 text-center">Klip bulunamadı.</div>;

  return (
    <div className="space-y-6 max-w-6xl pb-12">
      <div className="flex items-center justify-between">
        <Button variant="ghost" size="sm" onClick={() => (window.location.href = '/clips')}>
          <ArrowLeft className="w-4 h-4 mr-1.5" /> Kliplere Dön
        </Button>
        <div className="flex items-center gap-2">
          {clip.score_band && (
            <Badge variant="outline" className="text-xs border-violet-500/40 text-violet-300 bg-violet-500/10">
              Bant: {clip.score_band}
            </Badge>
          )}
          <Badge variant={clip.score >= 80 ? 'success' : clip.score >= 55 ? 'warning' : 'destructive'} className="text-xs">
            Viral Skor: {clip.score} / 100
          </Badge>
          <Button
            variant="destructive"
            size="sm"
            onClick={() => {
              if (confirm('Bu klibi ve render dosyasını silmek istediğinize emin misiniz?')) {
                deleteClipMutation.mutate();
              }
            }}
          >
            <Trash2 className="w-3.5 h-3.5 mr-1" /> Sil
          </Button>
        </div>
      </div>

      {statusMsg && (
        <div
          className={`p-3.5 rounded-lg border text-sm flex items-center gap-2 ${
            statusMsg.type === 'success'
              ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
              : 'bg-red-500/10 border-red-500/30 text-red-400'
          }`}
        >
          {statusMsg.type === 'success' ? <CheckCircle2 className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
          <span>{statusMsg.text}</span>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* ── Sol Kolon: Video Oynatıcı & Editör ─────────────────────── */}
        <div className="lg:col-span-2 space-y-6">
          <Card className="overflow-hidden bg-black border-zinc-800 flex items-center justify-center relative min-h-[380px]">
            {clip.render_path ? (
              <video
                controls
                className="w-full max-h-[500px] object-contain rounded-t-xl"
                src={api.clips.fileUrl(clipId)}
                poster={clip.thumbnail_path ? api.clips.thumbnailUrl(clipId) : undefined}
              />
            ) : (
              <div className="p-8 text-center text-zinc-500 text-sm">Render dosyası bulunamadı.</div>
            )}
          </Card>

          {/* AI Viral Gerekçe & Analiz Kartı */}
          {(clip.rationale || clip.hook_caption) && (
            <Card className="border-violet-500/30 bg-violet-950/20 shadow-lg">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold flex items-center gap-2 text-violet-300">
                  <span>🤖</span> AI Viral Analizi & Seçim Gerekçesi
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2.5 text-xs">
                {clip.rationale && (
                  <div className="p-3 rounded-lg bg-zinc-950/60 border border-violet-500/20 text-zinc-300 leading-relaxed">
                    <span className="font-semibold text-violet-400 block mb-1">Tespit Gerekçesi:</span>
                    {clip.rationale}
                  </div>
                )}
                <div className="flex flex-wrap gap-2 pt-1">
                  {clip.category && (
                    <Badge variant="secondary" className="text-[11px] font-mono bg-zinc-900 border border-zinc-700">
                      Kategori: {clip.category}
                    </Badge>
                  )}
                  {clip.score_band && (
                    <Badge variant="secondary" className="text-[11px] font-mono bg-zinc-900 border border-zinc-700">
                      Bant: {clip.score_band}
                    </Badge>
                  )}
                  {clip.hook_caption && (
                    <Badge variant="outline" className="text-[11px] text-amber-300 border-amber-500/40 bg-amber-500/10">
                      🎯 Kanca: "{clip.hook_caption}"
                    </Badge>
                  )}
                </div>
              </CardContent>
            </Card>
          )}

          <Card className="border-zinc-800 bg-zinc-900/80">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Klip Bilgileri ve Metinler</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="text-xs text-zinc-400 font-medium block mb-1.5">Klip Başlığı</label>
                <Input value={title} onChange={(e) => setTitle(e.target.value)} className="text-sm font-semibold" />
              </div>

              <div>
                <label className="text-xs text-zinc-400 font-medium block mb-1.5">Açıklama (SEO & Bio)</label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={4}
                  className="flex w-full rounded-md border border-zinc-800 bg-zinc-950 px-3 py-2 text-xs text-zinc-200 focus:outline-none focus:ring-2 focus:ring-violet-600"
                />
              </div>

              <div>
                <label className="text-xs text-zinc-400 font-medium block mb-1.5">Etiketler (Virgülle ayrılmış)</label>
                <Input value={tags} onChange={(e) => setTags(e.target.value)} className="text-xs font-mono" />
              </div>

              <div className="flex justify-end pt-2">
                <Button
                  onClick={() => updateClipMutation.mutate({ title, description, tags })}
                  className="bg-violet-600 hover:bg-violet-700"
                >
                  <Save className="w-4 h-4 mr-1.5" /> Değişiklikleri Kaydet
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* ── Sağ Kolon: Metadata & Kapak & Platform Yayınlama ──────────────── */}
        <div className="space-y-6">
          {/* Ortak Video Kapağı Yükleme Kartı */}
          <Card className="border-zinc-800 bg-zinc-900/80 overflow-hidden">
            <CardHeader className="pb-2.5 flex flex-row items-center justify-between">
              <CardTitle className="text-sm font-semibold flex items-center gap-1.5">
                <ImageIcon className="w-4 h-4 text-violet-400" /> Video Kapağı (Ortak)
              </CardTitle>
              <Badge variant="secondary" className="text-[10px] uppercase font-mono">
                Tüm Klipler
              </Badge>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="relative aspect-[2/3] max-h-56 mx-auto rounded-lg overflow-hidden border border-zinc-800 bg-black flex items-center justify-center group shadow-md">
                {clip.thumbnail_path ? (
                  <img
                    src={`${api.clips.thumbnailUrl(clipId)}?t=${Date.now()}`}
                    alt="Video Kapağı"
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="text-xs text-zinc-500 text-center p-4">Kapak görseli yok</div>
                )}
                <div
                  onClick={() => fileInputRef.current?.click()}
                  className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col items-center justify-center cursor-pointer text-zinc-200"
                >
                  <Upload className="w-6 h-6 mb-1 text-violet-400 animate-bounce" />
                  <span className="text-xs font-medium">Değiştirmek İçin Tıkla</span>
                </div>
              </div>

              <input
                ref={fileInputRef}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                className="hidden"
                onChange={handleFileChange}
              />

              <Button
                variant="outline"
                size="sm"
                className="w-full text-xs border-violet-500/30 text-violet-300 hover:bg-violet-500/10 hover:border-violet-500/50"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploadThumbMutation.isPending}
              >
                <Upload className="w-3.5 h-3.5 mr-1.5" />
                {uploadThumbMutation.isPending ? 'Kapak Yükleniyor...' : 'Yeni Kapak Yükle'}
              </Button>
              <p className="text-[11px] text-zinc-400 text-center leading-tight">
                Yükleyeceğiniz kapak bu videodan çıkan <strong>tüm kliplere</strong> otomatik bağlanır.
              </p>
            </CardContent>
          </Card>

          <Card className="border-zinc-800 bg-zinc-900/80">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold">Video Detayları</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-xs">
              <div className="flex justify-between py-1 border-b border-zinc-800/60">
                <span className="text-zinc-400">Viral Skor</span>
                <div className="flex items-center gap-1.5">
                  {clip.score_band && (
                    <span className="text-[11px] px-1.5 py-0.5 rounded bg-violet-500/20 text-violet-300 font-mono">
                      {clip.score_band}
                    </span>
                  )}
                  <span className="font-bold text-violet-400">{clip.score} / 100</span>
                </div>
              </div>
              <div className="flex justify-between py-1 border-b border-zinc-800/60">
                <span className="text-zinc-400">Kategori</span>
                <span className="font-medium text-zinc-200">{clip.category || 'EPIC_MOMENT'}</span>
              </div>
              <div className="flex justify-between py-1 border-b border-zinc-800/60">
                <span className="text-zinc-400">Süre</span>
                <span className="font-mono text-zinc-200">{clip.duration ? formatDuration(clip.duration) : '-'}</span>
              </div>
              <div className="flex justify-between py-1">
                <span className="text-zinc-400">Kanca Başlığı</span>
                <span className="font-medium text-zinc-300 line-clamp-1">{clip.hook_caption || '-'}</span>
              </div>
            </CardContent>
          </Card>

          <Card className="border-zinc-800 bg-zinc-900/80">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold">Yayınla & Paylaş</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2.5">
              <Button
                className="w-full bg-red-600 hover:bg-red-700 text-white justify-start"
                onClick={() => uploadYtMutation.mutate()}
                disabled={uploadYtMutation.isPending}
              >
                <Youtube className="w-4 h-4 mr-2" />
                {uploadYtMutation.isPending ? 'YouTube Yükleniyor...' : "YouTube Shorts'a Yükle"}
              </Button>

              <Button
                className="w-full bg-pink-600 hover:bg-pink-700 text-white justify-start"
                onClick={() => uploadIgMutation.mutate()}
                disabled={uploadIgMutation.isPending}
              >
                <Instagram className="w-4 h-4 mr-2" />
                {uploadIgMutation.isPending ? 'Instagram Yükleniyor...' : "Instagram Reels'e Yükle"}
              </Button>

              <Button
                variant="outline"
                className="w-full justify-start text-zinc-200 border-zinc-700"
                onClick={() => addToQueueMutation.mutate()}
              >
                <Share2 className="w-4 h-4 mr-2 text-violet-400" />
                Yayın Takvimine Ekle (14 Gün)
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
