import React from 'react';
import {
  ArrowLeftRight,
  Bell,
  BookOpen,
  ClipboardCheck,
  Cpu,
  FileText,
  GitBranch,
  LayoutDashboard,
  Moon,
  Network,
  RefreshCw,
  Settings,
  Siren,
  Sun,
} from 'lucide-react';
import type { V2Theme } from '../theme';
import type { V2View } from '../router';
import { compactCount } from '../lib/model';

type NavGroup = { items: Array<{ icon: React.ReactNode; id: V2View; label: string }>; label: string };

const navGroups: NavGroup[] = [
  {
    label: '모니터링',
    items: [
      { id: 'dashboard', label: '대시보드', icon: <LayoutDashboard size={17} /> },
      { id: 'executions', label: '실행 기록', icon: <ClipboardCheck size={17} /> },
      { id: 'rca', label: 'RCA 센터', icon: <GitBranch size={17} /> },
      { id: 'service-map', label: '서비스 맵', icon: <Network size={17} /> },
      { id: 'resources', label: '클러스터 리소스', icon: <Cpu size={17} /> },
      { id: 'alerts', label: '알림 & 이벤트', icon: <Siren size={17} /> },
    ],
  },
  {
    label: '운영',
    items: [
      { id: 'wiki', label: '위키 문서 관리', icon: <BookOpen size={17} /> },
      { id: 'reports', label: '보고서', icon: <FileText size={17} /> },
      { id: 'settings', label: '설정', icon: <Settings size={17} /> },
    ],
  },
];

const viewTitles: Record<V2View, string> = {
  dashboard: '대시보드',
  executions: '실행 기록',
  rca: 'RCA 센터',
  'service-map': '서비스 맵',
  resources: '클러스터 리소스',
  alerts: '알림 & 이벤트',
  wiki: '위키 문서 관리',
  reports: '보고서',
  settings: '설정',
};

export const V2Shell: React.FC<{
  active: V2View;
  alarmCount: number;
  children: React.ReactNode;
  clock: string;
  clusterName: string;
  healthScore: number;
  isLive: boolean;
  loading: boolean;
  onExitToV1: () => void;
  onNavigate: (view: V2View) => void;
  onOpenAlerts: () => void;
  onRefresh: () => void;
  onToggleTheme: () => void;
  theme: V2Theme;
}> = ({
  active,
  alarmCount,
  children,
  clock,
  clusterName,
  healthScore,
  isLive,
  loading,
  onExitToV1,
  onNavigate,
  onOpenAlerts,
  onRefresh,
  onToggleTheme,
  theme,
}) => {
  return (
    <div className="v2-shell">
      <aside className="v2-rail">
        <div className="v2-rail__brand">
          <span className="v2-rail__mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none">
              <path
                d="M12 2 3.5 7v10L12 22l8.5-5V7L12 2Z"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinejoin="round"
              />
              <circle cx="12" cy="12" r="3.4" fill="currentColor" />
            </svg>
          </span>
          <div>
            <strong>AIOps Console</strong>
            <span className="v2-rail__version">Ver.2 Preview</span>
          </div>
        </div>

        <div className={`v2-rail__health is-${healthScore >= 90 ? 'ok' : healthScore >= 70 ? 'warn' : 'risk'}`}>
          <span className="v2-rail__health-label">시스템 건강도</span>
          <div className="v2-rail__health-row">
            <strong className="v2-rail__health-value">{healthScore}%</strong>
            <span className="v2-rail__health-state">
              {healthScore >= 90 ? '정상' : healthScore >= 70 ? '주의' : '위험'}
            </span>
          </div>
          <span className="v2-rail__health-note">최근 동기화 {clock}</span>
          <svg className="v2-rail__spark" viewBox="0 0 190 44" aria-hidden="true">
            <path
              d="M0 32 L18 27 L30 29 L42 36 L54 22 L66 31 L78 18 L90 25 L104 13 L118 19 L132 12 L146 15 L160 8 L174 12 L190 4 L190 44 L0 44Z"
              fill="currentColor"
              opacity=".16"
            />
            <path
              d="M0 32 L18 27 L30 29 L42 36 L54 22 L66 31 L78 18 L90 25 L104 13 L118 19 L132 12 L146 15 L160 8 L174 12 L190 4"
              fill="none"
              stroke="currentColor"
              strokeLinecap="round"
              strokeWidth="2"
            />
          </svg>
          <span className="v2-rail__health-cluster">{clusterName}</span>
        </div>

        <nav className="v2-rail__nav">
          {navGroups.map((group) => (
            <div className="v2-rail__group" key={group.label}>
              <span className="v2-rail__group-label">{group.label}</span>
              {group.items.map((item) => (
                <button
                  key={item.id}
                  className={`v2-rail__item${active === item.id ? ' is-active' : ''}`}
                  onClick={() => onNavigate(item.id)}
                  type="button"
                >
                  <span className="v2-rail__item-icon">{item.icon}</span>
                  {item.label}
                </button>
              ))}
            </div>
          ))}
        </nav>

        <button className="v2-rail__exit" onClick={onExitToV1} type="button">
          <ArrowLeftRight size={14} />
          클래식 UI로 돌아가기
        </button>
      </aside>

      <div className="v2-main">
        <header className="v2-topbar">
          <div className="v2-topbar__title">
            <span className="v2-topbar__crumb">AIOps Console · Ver.2</span>
            <h1>{viewTitles[active]}</h1>
          </div>
          <button className="v2-topbar__search" onClick={onOpenAlerts} type="button">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" strokeWidth="2" />
              <line x1="16.5" y1="16.5" x2="21" y2="21" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
            <span>리소스, 이벤트, 문서 검색</span>
            <kbd>⌘K</kbd>
          </button>
          <div className="v2-topbar__controls">
            <span className={`v2-live-pill${isLive ? ' is-live' : ''}`}>
              <span className="v2-live-pill__dot" aria-hidden="true" />
              {isLive ? '실시간 연결' : '샘플 데이터'}
            </span>
            <span className="v2-topbar__clock">{clock}</span>
            <button
              className={`v2-icon-btn${loading ? ' is-spinning' : ''}`}
              onClick={onRefresh}
              type="button"
              aria-label="새로고침"
            >
              <RefreshCw size={15} />
            </button>
            <button className="v2-icon-btn v2-topbar__bell" onClick={onOpenAlerts} type="button" aria-label="알림">
              <Bell size={15} />
              {alarmCount > 0 && <span className="v2-topbar__bell-count">{compactCount(alarmCount)}</span>}
            </button>
            <button
              className="v2-icon-btn"
              onClick={onToggleTheme}
              type="button"
              aria-label={theme === 'dark' ? '라이트 모드' : '다크 모드'}
            >
              {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
            </button>
          </div>
        </header>
        <main className="v2-content">{children}</main>
      </div>
    </div>
  );
};
