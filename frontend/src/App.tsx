import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
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
