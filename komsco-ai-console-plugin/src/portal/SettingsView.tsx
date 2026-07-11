import * as React from 'react';
import { clusterLabel, displayApiEndpoint } from './portalDisplayModel';
import type { AiopsRuntimeStatus, ClusterSummary } from './types';

const Panel: React.FC<{
  children: React.ReactNode;
  title: string;
}> = ({ children, title }) => (
  <section className="portal-panel ">
    <div className="portal-panel__head">
      <div className="portal-panel__title">{title}</div>
    </div>
    <div className="portal-panel__body">{children}</div>
  </section>
);

export const SettingsView: React.FC<{
  status: AiopsRuntimeStatus;
  summary: ClusterSummary;
}> = ({ status, summary }) => {
  const capabilities = status.spec.capabilities;
  const [policyMode, setPolicyMode] = React.useState(capabilities.mutationsEnabled ? '승인 후 실행' : '읽기/증거 수집');
  const [notifyOps, setNotifyOps] = React.useState(true);
  const [notifyAudit, setNotifyAudit] = React.useState(false);

  return (
    <section className="settings-workbench stack-view">
      <section className="sample-banner is-config">
        <strong>화면 설정</strong>
        <span>현재 설정 화면은 포털에서 정책과 표시 옵션을 확인하는 UI입니다.</span>
      </section>
      <section className="settings-grid">
        <Panel title="게이트웨이 연결">
          <div className="settings-form">
            <label><span>API URL</span><input readOnly value={displayApiEndpoint(summary.apiUrl)} /></label>
            <label><span>클러스터</span><input readOnly value={clusterLabel(summary)} /></label>
            <label><span>상태</span><input readOnly value={summary.healthScore >= 90 ? '정상' : '확인 필요'} /></label>
          </div>
        </Panel>
        <Panel title="승인/실행 정책">
          <div className="settings-form">
            <label>
              <span>정책 모드</span>
              <select onChange={(event) => setPolicyMode(event.target.value)} value={policyMode}>
                <option>읽기/증거 수집</option>
                <option>승인 후 실행</option>
                <option>수동 승인 전용</option>
              </select>
            </label>
            <div className="capability-list">
              <span>변경 실행 <strong>{capabilities.mutationsEnabled ? '허용' : '차단'}</strong></span>
              <span>조치 실행기 <strong>{capabilities.actionExecutorConfigured ? '설정됨' : '미설정'}</strong></span>
              <span>감사 원장 <strong>{capabilities.recordStoreEnabled ? '켜짐' : '꺼짐'}</strong></span>
            </div>
          </div>
        </Panel>
        <Panel title="알림 채널">
          <div className="toggle-list">
            <label><input checked={notifyOps} onChange={(event) => setNotifyOps(event.target.checked)} type="checkbox" /> 운영 채널 알림</label>
            <label><input checked={notifyAudit} onChange={(event) => setNotifyAudit(event.target.checked)} type="checkbox" /> 감사 채널 알림</label>
            <label><input checked readOnly type="checkbox" /> 포털 배너 알림</label>
          </div>
        </Panel>
        <Panel title="데이터 보존">
          <div className="settings-form">
            <label><span>감사 ConfigMap</span><input readOnly value={capabilities.recordStoreConfigMap ?? '미설정'} /></label>
            <label><span>이벤트 폴링</span><input readOnly value="30초" /></label>
            <label><span>샘플 데이터</span><input readOnly value="문서/보고서 화면에만 표시" /></label>
          </div>
        </Panel>
      </section>
    </section>
  );
};
