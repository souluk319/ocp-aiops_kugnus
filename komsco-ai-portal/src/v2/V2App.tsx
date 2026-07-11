import React from 'react';
import './v2.css';
import type { NavView, QueueItem } from '../types';
import { V2Shell } from './components/V2Shell';
import { useV2Theme } from './theme';
import { v2ViewFromHash, writeV2Hash, type V2View } from './router';
import { aiopsAlarmCount, clusterLabel } from './lib/model';
import { V2IssueDrawer } from './components/V2IssueDrawer';
import { V2Dashboard } from './views/V2Dashboard';
import { V2Executions } from './views/V2Executions';
import { V2Rca } from './views/V2Rca';
import { V2ServiceMap } from './views/V2ServiceMap';
import { V2Resources } from './views/V2Resources';
import { V2Alerts } from './views/V2Alerts';
import { V2Wiki } from './views/V2Wiki';
import { V2Reports } from './views/V2Reports';
import { V2Settings } from './views/V2Settings';
import type { V2Runtime } from './runtime';

export type { V2Runtime } from './runtime';

const V2App: React.FC<{
  clock: string;
  onExitToV1: (view: NavView) => void;
  runtime: V2Runtime;
}> = ({ clock, onExitToV1, runtime }) => {
  const { theme, toggle } = useV2Theme();
  const [view, setView] = React.useState<V2View>(() => v2ViewFromHash());
  const [issueItem, setIssueItem] = React.useState<QueueItem | null>(null);
  const contentRef = React.useRef<HTMLDivElement>(null);

  const navigate = React.useCallback((next: V2View) => {
    setView(next);
    setIssueItem(null);
    writeV2Hash(next);
  }, []);

  React.useEffect(() => {
    contentRef.current?.querySelector('.v2-content')?.scrollTo({ top: 0 });
  }, [view]);

  // 주소창/외부에서 #v2/<view> 해시가 바뀐 경우 동기화 (딥링크·뒤로가기 대응)
  React.useEffect(() => {
    const syncFromHash = () => {
      setView((current) => {
        const next = v2ViewFromHash();
        return current === next ? current : next;
      });
    };
    window.addEventListener('hashchange', syncFromHash);
    window.addEventListener('popstate', syncFromHash);
    return () => {
      window.removeEventListener('hashchange', syncFromHash);
      window.removeEventListener('popstate', syncFromHash);
    };
  }, []);

  const openIssue = React.useCallback((item: QueueItem) => {
    setIssueItem(item);
  }, []);

  return (
    <div className="v2-root" data-v2-theme={theme} ref={contentRef}>
      <V2Shell
        active={view}
        alarmCount={aiopsAlarmCount(runtime.events)}
        clock={clock}
        clusterName={clusterLabel(runtime.summary, runtime.error)}
        healthScore={runtime.summary.healthScore}
        isLive={runtime.isLive}
        loading={runtime.loading}
        onExitToV1={() => onExitToV1('dashboard')}
        onNavigate={navigate}
        onOpenAlerts={() => navigate('alerts')}
        onRefresh={() => void runtime.refresh()}
        onToggleTheme={toggle}
        theme={theme}
      >
        {view === 'dashboard' && (
          <V2Dashboard onNavigate={navigate} onOpenItem={openIssue} runtime={runtime} />
        )}
        {view === 'executions' && <V2Executions onNavigate={navigate} runtime={runtime} />}
        {view === 'rca' && <V2Rca onNavigate={navigate} onOpenItem={openIssue} runtime={runtime} />}
        {view === 'service-map' && <V2ServiceMap onNavigate={navigate} runtime={runtime} />}
        {view === 'resources' && <V2Resources runtime={runtime} />}
        {view === 'alerts' && <V2Alerts onNavigate={navigate} onOpenItem={openIssue} runtime={runtime} />}
        {view === 'wiki' && <V2Wiki />}
        {view === 'reports' && <V2Reports runtime={runtime} />}
        {view === 'settings' && <V2Settings onToggleTheme={toggle} runtime={runtime} theme={theme} />}
      </V2Shell>
      <V2IssueDrawer
        clusterName={clusterLabel(runtime.summary)}
        item={issueItem}
        onClose={() => setIssueItem(null)}
        onNavigate={navigate}
      />
    </div>
  );
};

export default V2App;
