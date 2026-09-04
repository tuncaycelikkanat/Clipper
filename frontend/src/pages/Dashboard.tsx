import { useState } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Badge } from '@/components/ui/Badge';
import { Search, Activity, Clock, Users, Scissors, ArrowRight, Play } from 'lucide-react';
import { api } from '@/lib/api';
import { useQuery } from '@tanstack/react-query';
import { formatDuration } from '@/lib/utils';

export default function Dashboard() {
  const [url, setUrl] = useState('');
  const navigate = useNavigate();

  const handleAnalyze = (e: React.FormEvent) => {
    e.preventDefault();
    if (url.trim()) {
      navigate({ to: '/analyze', search: { url: url.trim() } });
    }
  };

  // 1. Dashboard Stats
  const { data: stats } = useQuery({
    queryKey: ['dashboard-stats'],
    queryFn: async () => {
      const [clips, queue, channels, scheduler] = await Promise.all([
        api.clips.list({ limit: 6 }),
        api.queue.list(),
        api.channels.list(),
        api.scheduler.status(),
      ]);
      return {
        clipsCount: clips.length >= 6 ? '30+' : clips.length,
        pendingQueue: queue.length,
        activeChannels: channels.length,
        schedulerRunning: scheduler?.running ?? false,
        recentClips: clips,
      };
    },
  });

  return (
    <div className="space-y-8 max-w-6xl pb-12">
      {/* ── Hero Section ───────────────────────────────────────────── */}
      <section className="bg-gradient-to-b from-zinc-900 via-zinc-900/80 to-zinc-950 border border-zinc-800 rounded-2xl p-8 md:p-10 text-center max-w-3xl mx-auto mt-4 shadow-2xl relative overflow-hidden">
        <div className="absolute inset-0 bg-violet-600/5 backdrop-blur-3xl pointer-events-none" />
        <div className="relative z-10 space-y-4">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-violet-500/10 border border-violet-500/20 text-violet-400 text-xs font-semibold">
            <Scissors className="w-3.5 h-3.5" /> Otonom YouTube Gaming Klip Stüdyosu
          </div>
          <h2 className="text-3xl md:text-4xl font-extrabold tracking-tight text-zinc-100">
            Viral Anları Yapay Zeka ile Yakalayın
          </h2>
          <p className="text-zinc-400 text-sm max-w-xl mx-auto leading-relaxed">
            YouTube video veya yayın linkini yapıştırın; ses analizi, izleyici ısı haritası ve Gemini 3.5 Flash ile en iyi anları 9:16 formata dönüştürün.
          </p>

          <form onSubmit={handleAnalyze} className="flex flex-col sm:flex-row gap-2 max-w-lg mx-auto pt-4">
            <Input
              placeholder="https://www.youtube.com/watch?v=..."
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              className="h-12 text-sm bg-zinc-950/80 font-mono"
              required
            />
            <Button type="submit" size="lg" className="h-12 px-8 bg-violet-600 hover:bg-violet-700 whitespace-nowrap">
              Klip Üret
            </Button>
          </form>
        </div>
      </section>

      {/* ── İstatistik Kartları ─────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="bg-zinc-900/60 border-zinc-800">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-medium text-zinc-400">Toplam Üretilen Klip</CardTitle>
            <Search className="h-4 w-4 text-violet-400" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-zinc-100">{stats?.clipsCount ?? 0}</div>
          </CardContent>
        </Card>

        <Card className="bg-zinc-900/60 border-zinc-800">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-medium text-zinc-400">Bekleyen Yayın Sırası</CardTitle>
            <Clock className="h-4 w-4 text-amber-400" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-zinc-100">{stats?.pendingQueue ?? 0}</div>
          </CardContent>
        </Card>

        <Card className="bg-zinc-900/60 border-zinc-800">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-medium text-zinc-400">Takip Edilen Kanal</CardTitle>
            <Users className="h-4 w-4 text-blue-400" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-zinc-100">{stats?.activeChannels ?? 0}</div>
          </CardContent>
        </Card>

        <Card className="bg-zinc-900/60 border-zinc-800">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-medium text-zinc-400">AutoPilot Durumu</CardTitle>
            <Activity className={`h-4 w-4 ${stats?.schedulerRunning ? 'text-emerald-400' : 'text-zinc-500'}`} />
          </CardHeader>
          <CardContent>
            <div className={`text-xl font-bold ${stats?.schedulerRunning ? 'text-emerald-400' : 'text-zinc-400'}`}>
              {stats?.schedulerRunning ? 'Çalışıyor' : 'Durduruldu'}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ── Son Üretilen Klipler ────────────────────────────────────── */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-bold text-zinc-100">Son Klipler</h3>
          <Button variant="ghost" size="sm" onClick={() => (window.location.href = '/clips')}>
            Tümünü Gör <ArrowRight className="w-4 h-4 ml-1.5" />
          </Button>
        </div>

        {stats?.recentClips && stats.recentClips.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {stats.recentClips.slice(0, 3).map((clip: any) => (
              <div
                key={clip.id}
                onClick={() => (window.location.href = `/clips/${clip.id}`)}
                className="cursor-pointer"
              >
                <Card className="hover:border-violet-500/50 transition-colors overflow-hidden group bg-zinc-900/80 border-zinc-800">
                  <div className="aspect-video bg-zinc-950 relative flex items-center justify-center">
                    {clip.thumbnail_path ? (
                      <img src={api.clips.thumbnailUrl(clip.id)} alt={clip.title} className="w-full h-full object-cover" />
                    ) : (
                      <Play className="w-8 h-8 text-zinc-700 group-hover:text-violet-500 transition-colors" />
                    )}
                    {clip.duration && (
                      <div className="absolute bottom-2 right-2 bg-black/80 px-1.5 py-0.5 text-[11px] rounded font-mono text-zinc-300">
                        {formatDuration(clip.duration)}
                      </div>
                    )}
                  </div>
                  <CardContent className="p-4 space-y-2">
                    <div className="flex justify-between items-start">
                      <h4 className="font-semibold line-clamp-1 text-sm text-zinc-200">{clip.title}</h4>
                      <Badge variant={clip.score >= 80 ? 'success' : 'warning'} className="text-[10px]">
                        {clip.score}
                      </Badge>
                    </div>
                  </CardContent>
                </Card>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-zinc-500 py-6 text-center">Henüz üretilen klip bulunamadı.</p>
        )}
      </div>
    </div>
  );
}
