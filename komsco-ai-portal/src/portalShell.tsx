import React from 'react';
import { Bell, RefreshCw } from 'lucide-react';
import aiopsIconUrl from './assets/aiops_icon.svg';
import { navGroupLabel, navItems } from './portalNavigation';
import { compactCount, formatTime, isOpenShiftAuthError, portalConnectionLabel } from './portalModel';
import type { ClusterSummary, NavView } from './types';

export const Sidebar: React.FC<{
  activeView: NavView;
  clock: string;
  setActiveView: (view: NavView) => void;
  summary: ClusterSummary;
}> = ({ activeView, clock, setActiveView, summary }) => (
  <aside className="portal-sidebar">
    <div className="portal-brand">
      <img alt="" aria-hidden="true" className="portal-brand__mark" src={aiopsIconUrl} />
      <div>
        <h1>AIOps for OCP</h1>
        <p>AI 운영 포털</p>
      </div>
    </div>

    <div className="portal-health">
      <div className="portal-health__label">시스템 건강도</div>
      <div className="portal-health__value">{summary.healthScore}%</div>
      <div className="portal-health__note">최근 업데이트 {formatTime(summary.updatedAt)}</div>
      <Sparkline color="#5df2ad" />
    </div>

    <nav className="portal-nav">
      {(['MONITORING', 'OPERATIONS'] as const).map((group) => (
        <React.Fragment key={group}>
          <div className="portal-nav__title">{navGroupLabel[group]}</div>
          {navItems
            .filter((item) => item.group === group)
            .map((item) => (
              <button
                className={`portal-nav__item ${activeView === item.id ? 'is-active' : ''}`}
                key={item.id}
                onClick={() => setActiveView(item.id)}
                type="button"
              >
                <span className="portal-nav__icon">{item.icon}</span>
                <span>{item.label}</span>
              </button>
            ))}
        </React.Fragment>
      ))}
    </nav>

    <div className="portal-sidebar__bottom">
      시스템 상태
      <div className="portal-sidebar__status">
        <span className="portal-sidebar__dot" />
        {summary.healthScore >= 90 ? '정상 상태' : '확인 필요'}
      </div>
      <div className="portal-sidebar__time">{clock} KST</div>
    </div>
  </aside>
);

export const Topbar: React.FC<{
  activeView: NavView;
  alarmCount: number;
  clusterName: string;
  error: string;
  isLive: boolean;
  loading: boolean;
  onNavigate: (view: NavView) => void;
  onRefresh: () => void;
}> = ({ activeView, alarmCount, clusterName, error, isLive, loading, onNavigate, onRefresh }) => {
  const activeItem = navItems.find((item) => item.id === activeView);
  const connectionLabel = portalConnectionLabel(isLive, error);

  return (
    <header className="portal-topbar">
      <div>
        <div className="portal-crumb">AIOps for OCP / {activeItem?.label ?? '대시보드'}</div>
        <div className="portal-title">{activeItem?.label ?? '대시보드'}</div>
      </div>
      <div className="portal-topbar__controls">
        <select aria-label="클러스터 선택" className="portal-select">
          <option>{clusterName}</option>
        </select>
        <select aria-label="조회 시간 선택" className="portal-select">
          <option>현재 상태</option>
          <option>최근 게이트웨이 응답</option>
        </select>
        <span className={`portal-mode ${isLive ? 'is-live' : 'is-demo'}`}>
          {connectionLabel}
        </span>
        <button
          aria-label="새로고침"
          className="portal-icon-btn"
          disabled={loading}
          onClick={onRefresh}
          title="새로고침"
          type="button"
        >
          <RefreshCw />
        </button>
        <button
          aria-label={`AIOps 위험/주의 이벤트 ${alarmCount}건`}
          className="portal-icon-btn portal-alarm"
          onClick={() => onNavigate('alerts')}
          title={`AIOps 위험/주의 이벤트 ${alarmCount}건`}
          type="button"
        >
          <Bell />
          {alarmCount > 0 && <span className="portal-alarm__badge">{compactCount(alarmCount)}</span>}
        </button>
        <div className="portal-user">
          <span>OC</span>
          OpenShift
        </div>
      </div>
    </header>
  );
};

export const ClusterSignalStrip: React.FC<{
  error: string;
  lastSnapshot: string;
  onNavigate: (view: NavView) => void;
  onRefresh: () => Promise<void>;
}> = ({ error, lastSnapshot, onNavigate, onRefresh }) => {
  const errorLine = error.split('\n').find(Boolean) ?? '게이트웨이 연결 실패';
  const authRequired = isOpenShiftAuthError(error);

  return (
    <div className="cluster-signal-strip">
      <span className="cluster-signal-strip__dot" aria-hidden="true" />
      <div>
        <strong>{authRequired ? 'OpenShift 인증 필요' : '게이트웨이 신호 확인 필요'}</strong>
        <span>
          {authRequired
            ? '독립 포털은 OKD 콘솔 토큰을 자동으로 받지 못해 클러스터 조회가 제한됩니다.'
            : '실시간 클러스터 텔레메트리를 사용할 수 없어 마지막 수집 스냅샷을 표시합니다.'}{' '}
          · {lastSnapshot}
        </span>
        <small>{errorLine}</small>
      </div>
      <button onClick={() => void onRefresh()} type="button">
        연결 재시도
      </button>
      <button onClick={() => onNavigate('alerts')} type="button">
        게이트웨이 이벤트
      </button>
    </div>
  );
};

const Sparkline: React.FC<{ color: string }> = ({ color }) => (
  <svg aria-hidden="true" className="sparkline" viewBox="0 0 190 44">
    <path
      d="M0 32 L18 27 L30 29 L42 36 L54 22 L66 31 L78 18 L90 25 L104 13 L118 19 L132 12 L146 15 L160 8 L174 12 L190 4 L190 44 L0 44Z"
      fill={color}
      opacity=".16"
    />
    <path
      d="M0 32 L18 27 L30 29 L42 36 L54 22 L66 31 L78 18 L90 25 L104 13 L118 19 L132 12 L146 15 L160 8 L174 12 L190 4"
      fill="none"
      stroke={color}
      strokeLinecap="round"
      strokeWidth="2"
    />
  </svg>
);
