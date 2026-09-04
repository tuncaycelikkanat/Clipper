import os

files = {
    "src/hooks/useSSE.ts": """import { useEffect, useRef } from 'react';
import { SSEProgressEvent } from '../types';

export function useSSE(url: string | null, options: {
  onProgress?: (event: SSEProgressEvent) => void;
  onDone?: (data: any) => void;
  onError?: (error: any) => void;
}) {
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!url) return;

    const eventSource = new EventSource(url);
    eventSourceRef.current = eventSource;

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'progress' && options.onProgress) {
          options.onProgress(data.data);
        } else if (data.type === 'done' && options.onDone) {
          options.onDone(data.data);
        } else if (data.type === 'error' && options.onError) {
          options.onError(data.data);
        }
      } catch (e) {
        console.error('Failed to parse SSE message', e);
      }
    };

    eventSource.onerror = (error) => {
      console.error('SSE Error', error);
      if (options.onError) {
        options.onError(error);
      }
      eventSource.close();
    };

    return () => {
      eventSource.close();
    };
  }, [url]);

  return eventSourceRef.current;
}
""",
    "src/main.tsx": """import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
""",
    "src/App.tsx": """import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider, createRouter, createRoute, createRootRoute } from '@tanstack/react-router';
import Layout from './components/layout/Layout';
import Dashboard from './pages/Dashboard';
import Analyze from './pages/Analyze';
import Clips from './pages/Clips';
import ClipDetail from './pages/ClipDetail';
import Planner from './pages/Planner';
import AutoPilot from './pages/AutoPilot';
import Settings from './pages/Settings';

const queryClient = new QueryClient();

const rootRoute = createRootRoute({
  component: Layout,
});

const indexRoute = createRoute({ getParentRoute: () => rootRoute, path: '/', component: Dashboard });
const analyzeRoute = createRoute({ getParentRoute: () => rootRoute, path: '/analyze', component: Analyze });
const clipsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/clips', component: Clips });
const clipDetailRoute = createRoute({ getParentRoute: () => rootRoute, path: '/clips/$clipId', component: ClipDetail });
const plannerRoute = createRoute({ getParentRoute: () => rootRoute, path: '/planner', component: Planner });
const autoPilotRoute = createRoute({ getParentRoute: () => rootRoute, path: '/autopilot', component: AutoPilot });
const settingsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/settings', component: Settings });

const routeTree = rootRoute.addChildren([
  indexRoute,
  analyzeRoute,
  clipsRoute,
  clipDetailRoute,
  plannerRoute,
  autoPilotRoute,
  settingsRoute,
]);

const router = createRouter({ routeTree });

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
""",
    "src/components/layout/Layout.tsx": """import { Outlet } from '@tanstack/react-router';
import Sidebar from './Sidebar';
import TopBar from './TopBar';

export default function Layout() {
  return (
    <div className="flex h-screen w-full bg-zinc-950 text-foreground overflow-hidden">
      <Sidebar />
      <div className="flex flex-col flex-1 overflow-hidden">
        <TopBar />
        <main className="flex-1 overflow-y-auto p-4 md:p-6 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
""",
    "src/components/layout/Sidebar.tsx": """import { Link, useLocation } from '@tanstack/react-router';
import { Home, BarChart2, Video, Calendar, Bot, Settings, Scissors } from 'lucide-react';
import { cn } from '@/lib/utils';

const links = [
  { to: '/', label: 'Dashboard', icon: Home },
  { to: '/analyze', label: 'Analiz', icon: BarChart2 },
  { to: '/clips', label: 'Klipler', icon: Video },
  { to: '/planner', label: 'Planlayıcı', icon: Calendar },
  { to: '/autopilot', label: 'AutoPilot', icon: Bot },
  { to: '/settings', label: 'Ayarlar', icon: Settings },
];

export default function Sidebar() {
  const location = useLocation();

  return (
    <div className="w-64 bg-zinc-900 border-r border-zinc-800 flex flex-col hidden md:flex h-full">
      <div className="h-16 flex items-center px-6 border-b border-zinc-800">
        <Scissors className="w-6 h-6 text-violet-600 mr-2" />
        <span className="font-bold text-xl tracking-tight">Clipper</span>
      </div>
      <nav className="flex-1 py-4 flex flex-col gap-1 px-3">
        {links.map((link) => {
          const isActive = location.pathname === link.to;
          const Icon = link.icon;
          return (
            <Link
              key={link.to}
              to={link.to}
              className={cn(
                "flex items-center px-3 py-2 rounded-md transition-colors text-sm font-medium",
                isActive 
                  ? "bg-violet-600/10 text-violet-500" 
                  : "text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800/50"
              )}
            >
              <Icon className="w-5 h-5 mr-3" />
              {link.label}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
""",
    "src/components/layout/TopBar.tsx": """import { useLocation } from '@tanstack/react-router';
import { Menu } from 'lucide-react';

export default function TopBar() {
  const location = useLocation();
  const titleMap: Record<string, string> = {
    '/': 'Dashboard',
    '/analyze': 'Analiz',
    '/clips': 'Klipler',
    '/planner': 'Planlayıcı',
    '/autopilot': 'AutoPilot',
    '/settings': 'Ayarlar',
  };

  const title = titleMap[location.pathname] || 'Clipper';

  return (
    <header className="h-16 bg-zinc-900/50 border-b border-zinc-800 flex items-center justify-between px-4 md:px-6 sticky top-0 z-10 backdrop-blur-sm">
      <div className="flex items-center">
        <button className="md:hidden p-2 -ml-2 mr-2 text-zinc-400 hover:text-white">
          <Menu className="w-5 h-5" />
        </button>
        <h1 className="text-lg font-semibold text-zinc-100">{title}</h1>
      </div>
      <div className="flex items-center gap-4">
        {/* Actions can go here */}
      </div>
    </header>
  );
}
""",
    "src/components/ui/Button.tsx": """import * as React from "react"
import { cn } from "@/lib/utils"

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'default' | 'destructive' | 'outline' | 'secondary' | 'ghost' | 'link';
  size?: 'default' | 'sm' | 'lg' | 'icon';
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'default', size = 'default', ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          "inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
          {
            'bg-violet-600 text-white hover:bg-violet-700': variant === 'default',
            'bg-destructive text-destructive-foreground hover:bg-destructive/90': variant === 'destructive',
            'border border-input bg-background hover:bg-accent hover:text-accent-foreground': variant === 'outline',
            'bg-secondary text-secondary-foreground hover:bg-secondary/80': variant === 'secondary',
            'hover:bg-accent hover:text-accent-foreground': variant === 'ghost',
            'h-10 px-4 py-2': size === 'default',
            'h-9 rounded-md px-3': size === 'sm',
            'h-11 rounded-md px-8': size === 'lg',
            'h-10 w-10': size === 'icon',
          },
          className
        )}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"
export { Button }
""",
    "src/components/ui/Card.tsx": """import * as React from "react"
import { cn } from "@/lib/utils"

const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("rounded-xl border border-zinc-800 bg-zinc-900 text-card-foreground shadow-sm", className)} {...props} />
))
Card.displayName = "Card"

const CardHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("flex flex-col space-y-1.5 p-6", className)} {...props} />
))
CardHeader.displayName = "CardHeader"

const CardTitle = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLHeadingElement>>(({ className, ...props }, ref) => (
  <h3 ref={ref} className={cn("text-lg font-semibold leading-none tracking-tight", className)} {...props} />
))
CardTitle.displayName = "CardTitle"

const CardContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("p-6 pt-0", className)} {...props} />
))
CardContent.displayName = "CardContent"

export { Card, CardHeader, CardTitle, CardContent }
""",
    "src/components/ui/Input.tsx": """import * as React from "react"
import { cn } from "@/lib/utils"

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {}

const Input = React.forwardRef<HTMLInputElement, InputProps>(({ className, type, ...props }, ref) => {
  return (
    <input
      type={type}
      className={cn(
        "flex h-10 w-full rounded-md border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-zinc-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-600 focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-950 disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      ref={ref}
      {...props}
    />
  )
})
Input.displayName = "Input"
export { Input }
""",
    "src/components/ui/Badge.tsx": """import * as React from "react"
import { cn } from "@/lib/utils"

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: 'default' | 'secondary' | 'destructive' | 'outline' | 'success' | 'warning';
}

function Badge({ className, variant = "default", ...props }: BadgeProps) {
  return (
    <div
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
        {
          "border-transparent bg-violet-600 text-white hover:bg-violet-700": variant === "default",
          "border-transparent bg-secondary text-secondary-foreground hover:bg-secondary/80": variant === "secondary",
          "border-transparent bg-destructive text-destructive-foreground hover:bg-destructive/80": variant === "destructive",
          "border-transparent bg-green-600/20 text-green-500": variant === "success",
          "border-transparent bg-yellow-600/20 text-yellow-500": variant === "warning",
          "text-foreground": variant === "outline",
        },
        className
      )}
      {...props}
    />
  )
}
export { Badge }
""",
    "src/pages/Dashboard.tsx": """import { useState } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Search, Activity, Clock, Users, Play } from 'lucide-react';
import { api } from '@/lib/api';
import { useQuery } from '@tanstack/react-query';

export default function Dashboard() {
  const [url, setUrl] = useState('');
  const navigate = useNavigate();

  const handleAnalyze = () => {
    if (url) {
      navigate({ to: '/analyze', search: { url } });
    }
  };

  const { data: stats } = useQuery({
    queryKey: ['dashboard-stats'],
    queryFn: async () => {
      const [clips, queue, channels] = await Promise.all([
        api.clips.list({ limit: 5 }),
        api.queue.list(),
        api.channels.list()
      ]);
      return {
        clipsCount: 120, // Mocked for now
        pendingQueue: queue.length,
        activeChannels: channels.length,
        recentClips: clips,
      };
    }
  });

  return (
    <div className="space-y-8">
      <section className="bg-zinc-900 border border-zinc-800 rounded-xl p-8 text-center max-w-3xl mx-auto mt-8">
        <h2 className="text-3xl font-bold mb-4 tracking-tight">Otonom Klip Üreticisi</h2>
        <p className="text-zinc-400 mb-8 max-w-xl mx-auto">
          YouTube video linkini yapıştırın, yapay zeka en ilgi çekici anları bulup otomatik olarak kısa formatlı videolara dönüştürsün.
        </p>
        <div className="flex gap-2 max-w-lg mx-auto">
          <Input 
            placeholder="https://youtube.com/watch?v=..." 
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            className="h-12 text-base"
          />
          <Button onClick={handleAnalyze} size="lg" className="h-12 px-8">
            Klip Üret
          </Button>
        </div>
      </section>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Toplam Klip</CardTitle>
            <VideoIcon className="h-4 w-4 text-zinc-400" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.clipsCount || 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Bekleyen Sıra</CardTitle>
            <Clock className="h-4 w-4 text-zinc-400" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.pendingQueue || 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Aktif Kanallar</CardTitle>
            <Users className="h-4 w-4 text-zinc-400" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.activeChannels || 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Sistem Durumu</CardTitle>
            <Activity className="h-4 w-4 text-violet-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-violet-500">Aktif</div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
function VideoIcon(props: any) {
  return <Search {...props} /> // placeholder
}
""",
    "src/pages/Analyze.tsx": """import { useState } from 'react';
import { useSearch } from '@tanstack/react-router';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { api } from '@/lib/api';

export default function Analyze() {
  const search = useSearch({ strict: false });
  const [url, setUrl] = useState((search as any)?.url || '');
  const [running, setRunning] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);

  const handleStart = async () => {
    try {
      setRunning(true);
      const res = await api.pipeline.run({ url, target_clips: 3 });
      setJobId(res.job_id);
    } catch (e) {
      console.error(e);
      setRunning(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Yeni Analiz Başlat</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-4">
            <Input 
              value={url} 
              onChange={e => setUrl(e.target.value)} 
              placeholder="YouTube Video URL" 
            />
            <Button onClick={handleStart} disabled={!url || running}>
              {running ? 'Çalışıyor...' : 'Başlat'}
            </Button>
          </div>
        </CardContent>
      </Card>
      {jobId && (
        <Card>
          <CardHeader>
            <CardTitle>İşlem Durumu</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-zinc-400">İşlem ID: {jobId}</p>
            {/* SSE Progress hook integration would go here */}
            <div className="mt-4 animate-pulse text-violet-400">Video indiriliyor ve analiz ediliyor...</div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
""",
    "src/pages/Clips.tsx": """import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { Card, CardContent } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { formatDuration } from '@/lib/utils';
import { Link } from '@tanstack/react-router';

export default function Clips() {
  const { data: clips, isLoading } = useQuery({
    queryKey: ['clips'],
    queryFn: () => api.clips.list()
  });

  if (isLoading) return <div>Yükleniyor...</div>;

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold">Klipler</h1>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {clips?.map(clip => (
          <Link key={clip.id} to={`/clips/${clip.id}`}>
            <Card className="hover:border-violet-500/50 transition-colors cursor-pointer overflow-hidden group">
              <div className="aspect-video bg-zinc-800 relative">
                {clip.thumbnail_path ? (
                  <img src={api.clips.thumbnailUrl(clip.id)} alt={clip.title} className="w-full h-full object-cover" />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-zinc-500">Görsel Yok</div>
                )}
                <div className="absolute bottom-2 right-2 bg-black/70 px-1.5 py-0.5 text-xs rounded font-mono">
                  {formatDuration(clip.duration)}
                </div>
              </div>
              <CardContent className="p-4">
                <div className="flex justify-between items-start mb-2">
                  <h3 className="font-semibold line-clamp-2 text-sm" title={clip.title}>{clip.title}</h3>
                </div>
                <Badge variant={clip.score >= 80 ? 'success' : clip.score >= 60 ? 'warning' : 'destructive'}>
                  Score: {clip.score}
                </Badge>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
""",
    "src/pages/ClipDetail.tsx": """import { useParams } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';

export default function ClipDetail() {
  const { clipId } = useParams({ strict: false }) as { clipId: string };
  const { data: clip, isLoading } = useQuery({
    queryKey: ['clip', clipId],
    queryFn: () => api.clips.get(clipId)
  });

  if (isLoading) return <div>Yükleniyor...</div>;
  if (!clip) return <div>Klip bulunamadı.</div>;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div className="lg:col-span-2 space-y-6">
        <Card className="overflow-hidden bg-black border-zinc-800">
          <div className="aspect-video w-full flex items-center justify-center text-zinc-500">
            {/* Player will go here */}
            Video Player Placeholder
          </div>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{clip.title}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-zinc-300">{clip.description}</p>
            <div>
              <p className="text-sm text-zinc-500 mb-1">Tags</p>
              <div className="flex flex-wrap gap-2">
                {clip.tags?.split(',').map(tag => (
                  <Badge key={tag} variant="secondary">{tag.trim()}</Badge>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Metadatalar</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <div className="flex justify-between">
              <span className="text-zinc-500">Skor</span>
              <Badge variant={clip.score >= 80 ? 'success' : 'warning'}>{clip.score}</Badge>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-500">Kategori</span>
              <span>{clip.category || '-'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-500">Süre</span>
              <span>{clip.duration} sn</span>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Yayınla</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Button className="w-full bg-red-600 hover:bg-red-700">YouTube Shorts'a Yükle</Button>
            <Button className="w-full bg-pink-600 hover:bg-pink-700">Instagram Reels'e Yükle</Button>
            <Button className="w-full bg-teal-600 hover:bg-teal-700">TikTok'a Yükle</Button>
            <Button className="w-full" variant="outline">Sıraya Ekle</Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
""",
    "src/pages/Planner.tsx": """import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';

export default function Planner() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Planlayıcı</h1>
      <Card>
        <CardHeader>
          <CardTitle>Takvim Görünümü</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-zinc-400">Takvim ve planlanmış klipler burada listelenecektir.</p>
        </CardContent>
      </Card>
    </div>
  );
}
""",
    "src/pages/AutoPilot.tsx": """import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';

export default function AutoPilot() {
  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold">AutoPilot</h1>
        <Button>Yeni Kanal Ekle</Button>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Takip Edilen Kanallar</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-zinc-400">Otomatik takip edilen kanallar burada listelenecektir.</p>
        </CardContent>
      </Card>
    </div>
  );
}
""",
    "src/pages/Settings.tsx": """import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';

export default function Settings() {
  return (
    <div className="space-y-6 max-w-3xl">
      <h1 className="text-2xl font-bold">Ayarlar</h1>
      <Card>
        <CardHeader>
          <CardTitle>YouTube Bağlantısı</CardTitle>
        </CardHeader>
        <CardContent>
          <Button variant="outline">YouTube Hesabını Bağla</Button>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>AI Motorları</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-zinc-400">Gemini ve OpenRouter API anahtarları yapılandırması.</p>
        </CardContent>
      </Card>
    </div>
  );
}
"""
}

for path, content in files.items():
    full_path = os.path.join('/home/tuncay/Projects/clipper/frontend', path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, 'w') as f:
        f.write(content)

print("Created all files successfully.")
