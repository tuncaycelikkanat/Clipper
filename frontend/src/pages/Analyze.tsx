import { useState, useEffect, useRef } from 'react';
import { useSearch } from '@tanstack/react-router';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Badge } from '@/components/ui/Badge';
import { api } from '@/lib/api';
import { useSSE } from '@/hooks/useSSE';
import {
  Sliders,
  Sparkles,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
  Camera,
  Terminal,
  RotateCcw,
  Loader2,
} from 'lucide-react';

const PIPELINE_STEPS = [
  { key: 'extract', label: '1. Video & Metadata Çıkarımı', icon: '📥' },
  { key: 'audio', label: '2. Multimodal DSP (Ses, Pitch & Görsel Sahne)', icon: '🎵' },
  { key: 'rank', label: '3. Aday Klip & Dinamik Pencereleme', icon: '📊' },
  { key: 'llm', label: '4. Gemini Flash Viral Skorlama', icon: '🤖' },
  { key: 'align', label: '5. Hassas Sınır Hizalama (Görsel & Ses)', icon: '⏱️' },
  { key: 'cut', label: '6. 9:16 Render (Facecam / Blur)', icon: '🎬' },
];

export interface LogItem {
  time?: string;
  step?: string;
  progress?: number;
  message: string;
}

export default function Analyze() {
  const search = useSearch({ strict: false });
  const [url, setUrl] = useState((search as any)?.url || '');
  const [targetClips, setTargetClips] = useState(3);
  const [addSubtitles, setAddSubtitles] = useState(true);
  const [addHookCard, setAddHookCard] = useState(true);
  const [enhanceColors, setEnhanceColors] = useState(true);

  const [jobId, setJobId] = useState<string | null>(() => {
    return localStorage.getItem('clipper_active_job_id');
  });

  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [currentStep, setCurrentStep] = useState<string>('extract');
  const [stepMsg, setStepMsg] = useState<string>('');
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [completedClips, setCompletedClips] = useState<any[]>([]);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [previewData, setPreviewData] = useState<import('@/types').VideoPreview | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);

  const logContainerRef = useRef<HTMLDivElement>(null);

  // Fetch video preview and duration-based clip recommendations
  useEffect(() => {
    const trimmed = url.trim();
    if (!trimmed || (!trimmed.includes('youtube.com') && !trimmed.includes('youtu.be') && trimmed.length !== 11)) {
      setPreviewData(null);
      return;
    }

    let isMounted = true;
    const timer = setTimeout(async () => {
      try {
        setLoadingPreview(true);
        const data = await api.videos.preview(trimmed);
        if (isMounted && data) {
          setPreviewData(data);
          if (data.recommended_clips) {
            setTargetClips(data.recommended_clips);
          }
        }
      } catch {
        if (isMounted) setPreviewData(null);
      } finally {
        if (isMounted) setLoadingPreview(false);
      }
    }, 600);

    return () => {
      isMounted = false;
      clearTimeout(timer);
    };
  }, [url]);

  // Auto-scroll logs
  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [logs]);

  // Check initial active job on load
  useEffect(() => {
    if (jobId) {
      api.pipeline.getJob(jobId).then((job) => {
        if (job) {
          setProgress(job.progress || 0);
          setCurrentStep(job.current_step || 'extract');
          setStepMsg(job.current_step || '');
          if (job.logs && job.logs.length > 0) {
            setLogs(job.logs);
          }
          if (job.status === 'running' || job.status === 'queued') {
            setRunning(true);
          } else if (job.status === 'done') {
            setRunning(false);
            setCompletedClips(job.result || []);
          } else if (job.status === 'failed') {
            setRunning(false);
            setErrorMsg(job.error_msg || 'İşlem başarısız oldu.');
          }
        }
      }).catch(() => {
        localStorage.removeItem('clipper_active_job_id');
        setJobId(null);
      });
    }
  }, [jobId]);

  // SSE Stream
  const streamUrl = jobId ? api.pipeline.streamUrl(jobId) : null;
  useSSE(streamUrl, {
    onInit: (data: any) => {
      if (data.progress !== undefined) setProgress(data.progress);
      if (data.current_step) setStepMsg(data.current_step);
      if (data.logs && Array.isArray(data.logs)) setLogs(data.logs);
      if (data.clips && data.clips.length > 0) setCompletedClips(data.clips);
      if (data.status === 'running') setRunning(true);
      else if (data.status === 'done') setRunning(false);
    },
    onProgress: (data: any) => {
      setProgress(data.progress || 0);
      if (data.step) setCurrentStep(data.step);
      if (data.message) {
        setStepMsg(data.message);
        setLogs((prev) => [
          ...prev,
          {
            time: new Date().toLocaleTimeString('tr-TR'),
            step: data.step,
            progress: data.progress,
            message: data.message,
          },
        ]);
      }
    },
    onDone: (data: any) => {
      setProgress(100);
      setRunning(false);
      setCompletedClips(data.clips || []);
      setStepMsg('🎉 Tüm klipler başarıyla üretildi!');
      setLogs((prev) => [
        ...prev,
        {
          time: new Date().toLocaleTimeString('tr-TR'),
          step: 'done',
          progress: 100,
          message: '🎉 Tüm klipler başarıyla üretildi ve kütüphaneye kaydedildi!',
        },
      ]);
      localStorage.removeItem('clipper_active_job_id');
    },
    onError: (err: any) => {
      setRunning(false);
      setErrorMsg(err.message || 'Pipeline çalışırken bir hata oluştu.');
      setLogs((prev) => [
        ...prev,
        {
          time: new Date().toLocaleTimeString('tr-TR'),
          step: 'error',
          progress,
          message: `❌ Hata: ${err.message || 'Bilinmeyen hata'}`,
        },
      ]);
      localStorage.removeItem('clipper_active_job_id');
    },
  });

  const handleStart = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;

    setErrorMsg(null);
    setCompletedClips([]);
    setLogs([
      {
        time: new Date().toLocaleTimeString('tr-TR'),
        step: 'init',
        progress: 5,
        message: `🚀 Video analizi başlatılıyor: ${url.trim()}`,
      },
    ]);
    setProgress(5);
    setRunning(true);
    setStepMsg('Pipeline başlatılıyor...');

    try {
      const res = await api.pipeline.run({
        url: url.trim(),
        target_clips: Number(targetClips),
        render_mode: 'shorts_9x16_blur',
        add_subtitles: addSubtitles,
        add_hook_card: addHookCard,
        enhance_colors: enhanceColors,
      });
      setJobId(res.job_id);
      localStorage.setItem('clipper_active_job_id', res.job_id);
    } catch (err: any) {
      setErrorMsg(err.message || 'Pipeline başlatılamadı.');
      setRunning(false);
      localStorage.removeItem('clipper_active_job_id');
    }
  };

  const handleResetJob = () => {
    localStorage.removeItem('clipper_active_job_id');
    setJobId(null);
    setRunning(false);
    setProgress(0);
    setLogs([]);
    setCompletedClips([]);
    setErrorMsg(null);
  };

  return (
    <div className="space-y-8 max-w-5xl mx-auto pb-16">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Yeni Klip Analizi & Canlı Render</h1>
          <p className="text-zinc-400 text-sm mt-1">
            İşlem arka planda otonom yürütülür; başka sayfalara geçseniz dahi kesintiye uğramaz ve ilerleme kaydedilir.
          </p>
        </div>
        {jobId && (
          <Button
            size="sm"
            variant="outline"
            onClick={handleResetJob}
            className="text-xs border-zinc-700 hover:bg-zinc-800"
          >
            <RotateCcw className="w-3.5 h-3.5 mr-1.5" /> Yeni Analiz Formu
          </Button>
        )}
      </div>

      {errorMsg && (
        <div className="bg-red-500/10 border border-red-500/30 text-red-400 px-4 py-3 rounded-lg flex items-center gap-2 text-sm">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* ── 1. Parametreler ve Başlatma Formu ───────────────────────── */}
      <Card className="border-zinc-800 bg-zinc-900/90 shadow-xl">
        <CardHeader className="pb-4">
          <CardTitle className="text-base flex items-center gap-2">
            <Sliders className="w-4 h-4 text-violet-400" /> Analiz Parametreleri
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleStart} className="space-y-6">
            <div>
              <label className="text-xs text-zinc-400 font-medium block mb-1.5">YouTube Video URL</label>
              <div className="relative">
                <Input
                  placeholder="https://www.youtube.com/watch?v=..."
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  disabled={running}
                  className="h-11 font-mono text-sm pr-10"
                  required
                />
                {loadingPreview && (
                  <div className="absolute right-3 top-1/2 -translate-y-1/2">
                    <Loader2 className="w-4 h-4 text-violet-400 animate-spin" />
                  </div>
                )}
              </div>
            </div>

            {/* Video Önizleme & Süreye Göre Akıllı Klip Önerisi Kartı */}
            {previewData && (
              <div className="p-4 rounded-xl border border-violet-500/30 bg-violet-950/20 space-y-3 animate-in fade-in duration-300">
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                  <div className="flex items-center gap-3 min-w-0">
                    {previewData.thumbnail && (
                      <img
                        src={previewData.thumbnail}
                        alt={previewData.title}
                        className="w-16 h-10 object-cover rounded-md border border-zinc-700 shadow-sm shrink-0"
                      />
                    )}
                    <div className="min-w-0">
                      <h4 className="text-sm font-semibold text-zinc-200 truncate">{previewData.title}</h4>
                      <p className="text-xs text-zinc-400 truncate">
                        {previewData.uploader} • <span className="text-violet-300 font-medium font-mono">{previewData.duration_formatted}</span> ({previewData.duration_minutes} dakika)
                      </p>
                    </div>
                  </div>
                  <Badge variant="outline" className="border-violet-500/40 text-violet-300 bg-violet-500/10 shrink-0">
                    <Sparkles className="w-3 h-3 mr-1 text-violet-400" /> {previewData.tier_label}
                  </Badge>
                </div>

                <div className="pt-2 border-t border-violet-500/20 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
                  <span className="text-zinc-300">
                    🎯 <strong>Öneri:</strong> {previewData.explanation}
                  </span>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => setTargetClips(previewData.recommended_clips)}
                    className="h-7 text-xs border-violet-500/40 text-violet-300 hover:bg-violet-600/20 shrink-0"
                  >
                    ✨ Önerilen {previewData.recommended_clips} Klibi Seç
                  </Button>
                </div>
              </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-xs text-zinc-400 font-medium">Hedef Klip Sayısı</label>
                  <span className="text-xs font-mono text-violet-400 font-bold">{targetClips} Adet Klip</span>
                </div>
                <Input
                  type="number"
                  min="1"
                  max="25"
                  value={targetClips}
                  onChange={(e) => setTargetClips(Math.max(1, Math.min(25, Number(e.target.value))))}
                  disabled={running}
                  className="font-mono text-sm"
                />
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {[3, 5, 8, 10, 12, 15, 20].map((count) => (
                    <button
                      key={count}
                      type="button"
                      disabled={running}
                      onClick={() => setTargetClips(count)}
                      className={`px-2 py-0.5 rounded text-xs transition-colors font-mono ${
                        targetClips === count
                          ? 'bg-violet-600 text-white font-bold shadow-sm'
                          : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200'
                      }`}
                    >
                      {count}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="text-xs text-zinc-400 font-medium block mb-1.5">Otonom Düzen Formatı</label>
                <div className="h-10 px-3 rounded-md border border-zinc-800 bg-zinc-950/80 flex items-center gap-2 text-xs text-zinc-300">
                  <Camera className="w-4 h-4 text-violet-400 shrink-0" />
                  <span className="truncate">Facecam varsa Split, yoksa Blur Zoom</span>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2 border-t border-zinc-800/80">
              <label className="flex items-center gap-2 cursor-pointer text-xs text-zinc-300">
                <input
                  type="checkbox"
                  checked={addSubtitles}
                  onChange={(e) => setAddSubtitles(e.target.checked)}
                  disabled={running}
                  className="rounded border-zinc-800 bg-zinc-950 text-violet-600 focus:ring-violet-500"
                />
                <span>Whisper Karaoke Altyazı</span>
              </label>

              <label className="flex items-center gap-2 cursor-pointer text-xs text-zinc-300">
                <input
                  type="checkbox"
                  checked={addHookCard}
                  onChange={(e) => setAddHookCard(e.target.checked)}
                  disabled={running}
                  className="rounded border-zinc-800 bg-zinc-950 text-violet-600 focus:ring-violet-500"
                />
                <span>Kanca Başlık Kartı (Hook)</span>
              </label>

              <label className="flex items-center gap-2 cursor-pointer text-xs text-zinc-300">
                <input
                  type="checkbox"
                  checked={enhanceColors}
                  onChange={(e) => setEnhanceColors(e.target.checked)}
                  disabled={running}
                  className="rounded border-zinc-800 bg-zinc-950 text-violet-600 focus:ring-violet-500"
                />
                <span>Vibrancy Renk Canlandırma</span>
              </label>
            </div>

            <div className="flex justify-end pt-2">
              <Button
                type="submit"
                size="lg"
                disabled={!url.trim() || running}
                className="bg-violet-600 hover:bg-violet-700 px-8 font-semibold shadow-lg shadow-violet-600/25"
              >
                {running ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Pipeline İşleniyor (%{progress})...
                  </>
                ) : (
                  'Klip Üretimini Başlat'
                )}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {/* ── 2. Canlı İlerleme ve Detaylı Log Konsolu ─────────────────── */}
      {jobId && (
        <Card className="border-violet-600/30 bg-zinc-900/90 shadow-2xl">
          <CardHeader className="pb-3 border-b border-zinc-800">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-violet-400" />
                <CardTitle className="text-base font-bold text-zinc-100">
                  Canlı Pipeline Durumu & Klip Süreçleri
                </CardTitle>
              </div>
              <Badge
                variant={progress === 100 ? 'success' : running ? 'warning' : 'secondary'}
                className="text-xs px-2.5 py-0.5"
              >
                {progress === 100 ? '✓ Tamamlandı' : running ? `%${progress} İşleniyor` : 'Beklemede'}
              </Badge>
            </div>
          </CardHeader>

          <CardContent className="p-5 space-y-6">
            {/* İlerleme Çubuğu */}
            <div className="space-y-2">
              <div className="flex justify-between text-xs text-zinc-400 font-mono">
                <span>{stepMsg || 'İşleniyor...'}</span>
                <span className="font-bold text-violet-400">%{progress}</span>
              </div>
              <div className="w-full bg-zinc-950 rounded-full h-3 overflow-hidden border border-zinc-800 p-0.5">
                <div
                  className="bg-gradient-to-r from-violet-600 via-purple-500 to-indigo-500 h-full rounded-full transition-all duration-500 ease-out shadow-sm"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>

            {/* 6 Adımlı Aşama Kartları */}
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2.5">
              {PIPELINE_STEPS.map((step) => {
                const isCurrent = currentStep === step.key && running;
                const isPassed = progress === 100 || (progress >= 15 && step.key === 'extract') || (progress >= 30 && step.key === 'audio') || (progress >= 45 && step.key === 'rank') || (progress >= 60 && step.key === 'llm') || (progress >= 75 && step.key === 'align');

                return (
                  <div
                    key={step.key}
                    className={`p-3 rounded-lg border text-xs flex items-center justify-between transition-all ${
                      isCurrent
                        ? 'bg-violet-600/20 border-violet-500 text-violet-200 font-bold ring-1 ring-violet-500/50 scale-[1.02]'
                        : isPassed
                        ? 'bg-emerald-950/20 border-emerald-500/40 text-emerald-300'
                        : 'bg-zinc-950/40 border-zinc-800/80 text-zinc-500'
                    }`}
                  >
                    <div className="flex items-center gap-2 truncate">
                      <span className="text-base">{step.icon}</span>
                      <span className="truncate">{step.label}</span>
                    </div>
                    {isCurrent && <Loader2 className="w-3.5 h-3.5 animate-spin text-violet-400 shrink-0" />}
                    {isPassed && !isCurrent && <span className="text-emerald-400 text-xs font-bold">✓</span>}
                  </div>
                );
              })}
            </div>

            {/* Gerçek Zamanlı Terminal / Log Konsolu */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-zinc-300 flex items-center gap-1.5">
                  <Terminal className="w-3.5 h-3.5 text-violet-400" />
                  Arka Plan Olay Günlüğü (Live Event Logs)
                </span>
                <span className="text-[10px] font-mono text-zinc-500">{logs.length} olay kaydedildi</span>
              </div>

              <div
                ref={logContainerRef}
                className="bg-zinc-950 rounded-lg border border-zinc-800 p-3.5 font-mono text-xs text-zinc-300 max-h-60 overflow-y-auto space-y-1.5 shadow-inner"
              >
                {logs.length === 0 ? (
                  <div className="text-zinc-600 text-center py-4">Olaylar bekleniyor...</div>
                ) : (
                  logs.map((log, idx) => (
                    <div key={idx} className="flex items-start gap-2 leading-relaxed">
                      <span className="text-zinc-600 text-[11px] shrink-0">
                        {log.time || `[${idx + 1}]`}
                      </span>
                      <span
                        className={`text-[10px] px-1 py-0.2 rounded shrink-0 uppercase font-bold ${
                          log.step === 'cut'
                            ? 'bg-violet-950 text-violet-300 border border-violet-800'
                            : log.step === 'llm'
                            ? 'bg-amber-950 text-amber-300 border border-amber-800'
                            : log.step === 'error'
                            ? 'bg-red-950 text-red-300 border border-red-800'
                            : 'bg-zinc-900 text-zinc-400'
                        }`}
                      >
                        {log.step || 'INFO'}
                      </span>
                      <span
                        className={`break-all ${
                          log.message.includes('Hata') || log.message.includes('failed')
                            ? 'text-red-400'
                            : log.message.includes('Tamamlandı') || log.message.includes('Başarıyla')
                            ? 'text-emerald-400 font-semibold'
                            : 'text-zinc-300'
                        }`}
                      >
                        {log.message}
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ── 3. Tamamlanan Klipler Listesi ───────────────────────────── */}
      {completedClips.length > 0 && (
        <div className="space-y-4">
          <h2 className="text-lg font-bold text-zinc-100 flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5 text-emerald-400" />
            Üretilen Klipler ({completedClips.length})
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {completedClips.map((clip, idx) => (
              <Card key={idx} className="border-zinc-800 bg-zinc-900/80 overflow-hidden shadow-lg">
                <CardContent className="p-4 space-y-3">
                  <div className="flex justify-between items-start">
                    <span className="text-xs font-bold text-violet-400">Klip #{idx + 1}</span>
                    <Badge variant="success">Skor: {clip.score || clip.viral_confidence || 90}</Badge>
                  </div>
                  <h3 className="font-semibold text-sm text-zinc-100 line-clamp-2">{clip.title}</h3>
                  <p className="text-xs text-zinc-400 line-clamp-2">{clip.description}</p>
                  <Button
                    size="sm"
                    variant="outline"
                    className="w-full text-xs hover:border-violet-500 hover:text-violet-300"
                    onClick={() => (window.location.href = '/clips')}
                  >
                    Klip Kütüphanesinde Gör <ArrowRight className="w-3.5 h-3.5 ml-1.5" />
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
