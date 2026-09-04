import { Link, useLocation } from '@tanstack/react-router';
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
