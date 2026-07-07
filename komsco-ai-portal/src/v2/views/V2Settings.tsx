import React from 'react';
import { Moon, Sun } from 'lucide-react';
import type { V2Runtime } from '../V2App';
import type { V2Theme } from '../theme';
import { Card, DefList, Select, Toggle } from '../components/primitives';
import { clusterLabel, displayApiEndpoint } from '../lib/model';

export const V2Settings: React.FC<{
  onToggleTheme: () => void;
  runtime: V2Runtime;
  theme: V2Theme;
}> = ({ onToggleTheme, runtime, theme }) => {
  const { status, summary } = runtime;
  const capabilities = status.spec.capabilities;
  const [policyMode, setPolicyMode] = React.useState(
    capabilities.mutationsEnabled ? '승인 후 실행' : '읽기/증거 수집',
  );
  const [notifyOps, setNotifyOps] = React.useState(true);
  const [notifyAudit, setNotifyAudit] = React.useState(false);

  return (
    <div className="v2-view v2-settings">
      <section className="v2-config-banner">
        <strong>화면 설정</strong>
        <span>현재 설정 화면은 포털에서 정책과 표시 옵션을 확인하는 UI입니다.</span>
      </section>

      <section className="v2-grid v2-grid--settings">
        <Card title="게이트웨이 연결">
          <DefList
            rows={[
              { label: 'API', value: displayApiEndpoint(summary.apiUrl) },
              { label: '클러스터', value: clusterLabel(summary) },
              { label: '상태', value: summary.healthScore >= 90 ? '정상' : '확인 필요' },
            ]}
          />
        </Card>

        <Card title="승인/실행 정책">
          <label className="v2-field">
            <span>정책 모드</span>
            <Select
              onChange={setPolicyMode}
              options={[
                { label: '읽기/증거 수집', value: '읽기/증거 수집' },
                { label: '승인 후 실행', value: '승인 후 실행' },
                { label: '수동 승인 전용', value: '수동 승인 전용' },
              ]}
              value={policyMode}
            />
          </label>
          <div className="v2-capability-list">
            <span>
              변경 실행 <strong className={capabilities.mutationsEnabled ? 'is-on' : 'is-off'}>{capabilities.mutationsEnabled ? '허용' : '차단'}</strong>
            </span>
            <span>
              조치 실행기 <strong className={capabilities.actionExecutorConfigured ? 'is-on' : 'is-off'}>{capabilities.actionExecutorConfigured ? '설정됨' : '미설정'}</strong>
            </span>
            <span>
              감사 원장 <strong className={capabilities.recordStoreEnabled ? 'is-on' : 'is-off'}>{capabilities.recordStoreEnabled ? '켜짐' : '꺼짐'}</strong>
            </span>
          </div>
        </Card>

        <Card title="알림 채널">
          <div className="v2-toggle-list">
            <Toggle checked={notifyOps} label="운영 채널 알림" onChange={setNotifyOps} />
            <Toggle checked={notifyAudit} label="감사 채널 알림" onChange={setNotifyAudit} />
            <Toggle checked disabled label="포털 배너 알림" />
          </div>
        </Card>

        <Card title="데이터 보존">
          <DefList
            rows={[
              { label: '감사 ConfigMap', value: capabilities.recordStoreConfigMap ?? '미설정' },
              { label: '이벤트 폴링', value: '30초' },
              { label: '샘플 데이터', value: '문서/보고서 화면에만 표시' },
            ]}
          />
        </Card>

        <Card title="테마 (Ver.2 전용)">
          <div className="v2-theme-picker">
            <button
              className={`v2-theme-option${theme === 'dark' ? ' is-active' : ''}`}
              onClick={() => theme !== 'dark' && onToggleTheme()}
              type="button"
            >
              <span className="v2-theme-option__swatch is-dark" aria-hidden="true">
                <Moon size={15} />
              </span>
              <strong>다크</strong>
              <small>옵스센터 기본 테마</small>
            </button>
            <button
              className={`v2-theme-option${theme === 'light' ? ' is-active' : ''}`}
              onClick={() => theme !== 'light' && onToggleTheme()}
              type="button"
            >
              <span className="v2-theme-option__swatch is-light" aria-hidden="true">
                <Sun size={15} />
              </span>
              <strong>라이트</strong>
              <small>밝은 환경용 테마</small>
            </button>
          </div>
          <small className="v2-theme-note">선택한 테마는 이 브라우저에 저장되며 Ver.2 화면에만 적용됩니다.</small>
        </Card>
      </section>
    </div>
  );
};
