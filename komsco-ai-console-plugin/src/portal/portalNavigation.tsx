import * as React from 'react';
import {
  BookOpen,
  ClipboardCheck,
  Cpu,
  FileText,
  GitBranch,
  LayoutDashboard,
  Network,
  Settings,
  Siren,
} from 'lucide-react';
import type { NavView } from './types';

export type NavItem = {
  id: NavView;
  label: string;
  group: 'MONITORING' | 'OPERATIONS';
  icon: React.ReactNode;
};

export const navItems: NavItem[] = [
  { id: 'dashboard', label: '대시보드', group: 'MONITORING', icon: <LayoutDashboard /> },
  { id: 'executions', label: '실행 기록', group: 'MONITORING', icon: <ClipboardCheck /> },
  { id: 'rca', label: 'RCA 센터', group: 'MONITORING', icon: <GitBranch /> },
  { id: 'service-map', label: '서비스 맵', group: 'MONITORING', icon: <Network /> },
  { id: 'endpoints', label: '클러스터 리소스', group: 'MONITORING', icon: <Cpu /> },
  { id: 'alerts', label: '알림 & 이벤트', group: 'MONITORING', icon: <Siren /> },
  { id: 'wiki', label: '위키 문서 관리', group: 'OPERATIONS', icon: <BookOpen /> },
  { id: 'reports', label: '보고서', group: 'OPERATIONS', icon: <FileText /> },
  { id: 'settings', label: '설정', group: 'OPERATIONS', icon: <Settings /> },
];

export const navGroupLabel: Record<NavItem['group'], string> = {
  MONITORING: '모니터링',
  OPERATIONS: '운영',
};

export const isNavView = (value: string): value is NavView =>
  navItems.some((item) => item.id === value);

export const standaloneRouteByView: Record<NavView, string> = {
  alerts: '/dashboards/aiops/alerts',
  dashboard: '/dashboards/aiops',
  endpoints: '/dashboards/aiops/endpoints',
  executions: '/dashboards/aiops/executions',
  rca: '/dashboards/aiops/audit',
  reports: '/dashboards/aiops/reports',
  'service-map': '/dashboards/aiops/service-map',
  settings: '/dashboards/aiops/settings',
  wiki: '/dashboards/aiops/docs',
};

export const viewFromPathname = (pathname: string): NavView | undefined => {
  const normalized = pathname.replace(/\/+$/, '') || '/';
  if (normalized === '/') {
    return 'dashboard';
  }

  const match = (Object.entries(standaloneRouteByView) as Array<[NavView, string]>).find(
    ([, route]) => normalized === route,
  );
  return match?.[0];
};

export const viewFromLocation = (): NavView => {
  if (typeof window === 'undefined') {
    return 'dashboard';
  }

  const hashView = decodeURIComponent(window.location.hash.replace(/^#\/?/, ''));
  if (isNavView(hashView)) {
    return hashView;
  }

  return viewFromPathname(window.location.pathname) ?? 'dashboard';
};
