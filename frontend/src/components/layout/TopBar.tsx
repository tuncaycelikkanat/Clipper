import { useLocation } from '@tanstack/react-router';
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
      </div>
    </header>
  );
}
