import { Outlet } from '@tanstack/react-router';
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
