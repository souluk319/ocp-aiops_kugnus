import * as React from 'react';
import {
  CoolCheckIcon,
  CoolDesktopTowerIcon,
  CoolInfoIcon,
  CoolListChecklistIcon,
  CoolShieldCheckIcon,
  CoolTerminalIcon,
  CoolWarningIcon,
} from './coolicons';
import {
  getPhaseTone,
  getRecordPhase,
  getRecordTargetLabel,
  phaseLabelKo,
} from './assistant.actionRecords';
import {
  canUseActionExecution,
  canUseUnrestrictedCommands,
  getActionExecutionDisabledReason,
  getActionLifecycleSteps,
  getActionLifecycleSummary,
  getUnrestrictedDisabledReason,
} from './assistant.actionState';
import type { AiopsExecutionMode, AiopsRecordView } from './assistant.types';
import type { AiopsRuntimeStatus, ClusterSummary } from '../services/aiGateway';

export type RailTone = 'ok' | 'warn' | 'danger' | 'review' | 'neutral';

export type CompactStatus = {
  label: string;
  title: string;
  tone: RailTone;
};

export const formatSummaryTime = (updatedAt?: string): string => {
  if (!updatedAt) {
    return '수집 대기';
  }

  const date = new Date(updatedAt);
  if (Number.isNaN(date.getTime())) {
    return '수집됨';
  }

  return date.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
};

const getNodePressureLabel = (node: ClusterSummary['nodes']['items'][number]): string => {
  const pressures = [];
  if (node.pressures.disk) {
    pressures.push('Disk');
  }
  if (node.pressures.memory) {
    pressures.push('Memory');
  }
  if (node.pressures.pid) {
    pressures.push('PID');
  }

  return pressures.length > 0 ? `${pressures.join('/')} Pressure` : 'Pressure 없음';
};

const formatCpuUsage = (value?: string): string | null => {
  if (!value) {
    return null;
  }

  const trimmed = value.trim();
  const match = trimmed.match(/^(\d+(?:\.\d+)?)([a-zA-Z]*)$/);
  if (!match) {
    return trimmed;
  }

  const amount = Number(match[1]);
  if (!Number.isFinite(amount)) {
    return trimmed;
  }

  const unit = match[2];
  const cores =
    unit === 'n'
      ? amount / 1_000_000_000
      : unit === 'u'
        ? amount / 1_000_000
        : unit === 'm'
          ? amount / 1_000
          : amount;

  if (cores >= 1) {
    return `${cores.toFixed(cores >= 10 ? 0 : 1)} cores`;
  }

  return `${Math.max(1, Math.round(cores * 1000))} m`;
};

const formatMemoryUsage = (value?: string): string | null => {
  if (!value) {
    return null;
  }

  const trimmed = value.trim();
  const match = trimmed.match(/^(\d+(?:\.\d+)?)([a-zA-Z]*)$/);
  if (!match) {
    return trimmed;
  }

  const amount = Number(match[1]);
  if (!Number.isFinite(amount)) {
    return trimmed;
  }

  const unitMultipliers: Record<string, number> = {
    Ki: 1024,
    Mi: 1024 ** 2,
    Gi: 1024 ** 3,
    Ti: 1024 ** 4,
    K: 1000,
    M: 1000 ** 2,
    G: 1000 ** 3,
    T: 1000 ** 4,
    '': 1,
  };
  const multiplier = unitMultipliers[match[2]];
  if (!multiplier) {
    return trimmed;
  }

  const bytes = amount * multiplier;
  const gib = bytes / 1024 ** 3;
  if (gib >= 1) {
    return `${gib.toFixed(gib >= 10 ? 1 : 2)} GiB`;
  }

  const mib = bytes / 1024 ** 2;
  if (mib >= 1) {
    return `${mib.toFixed(mib >= 10 ? 0 : 1)} MiB`;
  }

  return `${Math.round(bytes / 1024)} KiB`;
};

const cpuCoresFromUsage = (value?: string): number | null => {
  if (!value) {
    return null;
  }

  const match = value.trim().match(/^(\d+(?:\.\d+)?)([a-zA-Z]*)$/);
  if (!match) {
    return null;
  }

  const amount = Number(match[1]);
  if (!Number.isFinite(amount)) {
    return null;
  }

  const unit = match[2];
  if (unit === 'n') {
    return amount / 1_000_000_000;
  }
  if (unit === 'u') {
    return amount / 1_000_000;
  }
  if (unit === 'm') {
    return amount / 1_000;
  }

  return amount;
};

const memoryBytesFromUsage = (value?: string): number | null => {
  if (!value) {
    return null;
  }

  const match = value.trim().match(/^(\d+(?:\.\d+)?)([a-zA-Z]*)$/);
  if (!match) {
    return null;
  }

  const amount = Number(match[1]);
  if (!Number.isFinite(amount)) {
    return null;
  }

  const unitMultipliers: Record<string, number> = {
    Ki: 1024,
    Mi: 1024 ** 2,
    Gi: 1024 ** 3,
    Ti: 1024 ** 4,
    K: 1000,
    M: 1000 ** 2,
    G: 1000 ** 3,
    T: 1000 ** 4,
    '': 1,
  };
  const multiplier = unitMultipliers[match[2]];

  return multiplier ? amount * multiplier : null;
};

const formatCpuCores = (cores: number): string =>
  cores >= 1
    ? `${cores.toFixed(cores >= 10 ? 0 : 1)} cores`
    : `${Math.max(1, Math.round(cores * 1000))} m`;

const formatMemoryBytes = (bytes: number): string => {
  const gib = bytes / 1024 ** 3;
  if (gib >= 1) {
    return `${gib.toFixed(gib >= 10 ? 1 : 2)} GiB`;
  }

  const mib = bytes / 1024 ** 2;
  if (mib >= 1) {
    return `${mib.toFixed(mib >= 10 ? 0 : 1)} MiB`;
  }

  return `${Math.round(bytes / 1024)} KiB`;
};

export const getClusterUsageSummary = (summary: ClusterSummary): string => {
  const cpuTotal = summary.nodes.items.reduce((total, node) => {
    const cores = cpuCoresFromUsage(node.usage.cpu);
    return cores === null ? total : total + cores;
  }, 0);
  const memoryTotal = summary.nodes.items.reduce((total, node) => {
    const bytes = memoryBytesFromUsage(node.usage.memory);
    return bytes === null ? total : total + bytes;
  }, 0);

  if (!summary.nodes.metricsAvailable) {
    return 'Metrics API unavailable';
  }

  if (cpuTotal <= 0 && memoryTotal <= 0) {
    return 'Metrics connected, usage pending';
  }

  return `CPU ${cpuTotal > 0 ? formatCpuCores(cpuTotal) : '-'} · 메모리 ${
    memoryTotal > 0 ? formatMemoryBytes(memoryTotal) : '-'
  }`;
};

export const formatNodeUsage = (node: ClusterSummary['nodes']['items'][number]): string => {
  const cpu = formatCpuUsage(node.usage.cpu);
  const memory = formatMemoryUsage(node.usage.memory);
  if (!cpu && !memory) {
    return getNodePressureLabel(node);
  }

  return `CPU ${cpu ?? '-'} · 메모리 ${memory ?? '-'}`;
};

export const getClusterFaultCount = (summary: ClusterSummary): number =>
  summary.operators.degraded + summary.operators.unavailable;

export const getHealthTone = (
  summary: ClusterSummary | null,
): 'ok' | 'warn' | 'danger' | 'neutral' => {
  if (!summary) {
    return 'neutral';
  }

  if (summary.healthScore < 70 || getClusterFaultCount(summary) > 0 || summary.nodes.notReady > 0) {
    return 'danger';
  }

  if (summary.healthScore < 90 || summary.operators.progressing > 0) {
    return 'warn';
  }

  return 'ok';
};

export const getOperatorTone = (
  operator: ClusterSummary['operators']['issues'][number],
): 'warn' | 'danger' => {
  if (!operator.available || operator.degraded) {
    return 'danger';
  }

  return 'warn';
};

export const getNodeCompactStatus = (
  summary: ClusterSummary | null,
  loading: boolean,
  error: string,
): CompactStatus => {
  if (summary) {
    const label = `Node ${summary.nodes.ready}/${summary.nodes.total}`;
    if (summary.nodes.notReady > 0) {
      return {
        label: `${label} 확인 필요`,
        title: `${summary.nodes.notReady} node(s) are not ready.`,
        tone: 'danger',
      };
    }

    if (summary.nodes.total > 0 && summary.nodes.ready === summary.nodes.total) {
      return {
        label: `${label} · Ready`,
        title: 'All reported nodes are Ready.',
        tone: 'ok',
      };
    }

    return {
      label: `${label} 부분 확인`,
      title: 'Node readiness is partially available.',
      tone: 'warn',
    };
  }

  if (error) {
    return {
      label: 'Node 확인 필요',
      title: error,
      tone: 'danger',
    };
  }

  return {
    label: loading ? 'Node 수집 중' : 'Node 대기',
    title: 'Cluster node summary is not available yet.',
    tone: 'neutral',
  };
};

export const getOperatorCompactStatus = (
  summary: ClusterSummary | null,
  loading: boolean,
  error: string,
): CompactStatus => {
  if (summary) {
    const faultCount = getClusterFaultCount(summary);
    if (faultCount > 0) {
      return {
        label: `Operator ${faultCount}건 확인`,
        title: `${faultCount} degraded/unavailable operator issue(s) need attention.`,
        tone: 'danger',
      };
    }

    if (summary.operators.progressing > 0) {
      return {
        label: `Operator ${summary.operators.progressing}건 진행`,
        title: `${summary.operators.progressing} operator(s) are progressing.`,
        tone: 'warn',
      };
    }

    if (summary.operators.total > 0 && summary.operators.available === summary.operators.total) {
      return {
        label: `Operator ${summary.operators.available}/${summary.operators.total} 정상`,
        title: `All ${summary.operators.total} ClusterOperators are available.`,
        tone: 'ok',
      };
    }

    return {
      label: `Operator ${summary.operators.available}/${summary.operators.total} 확인`,
      title: 'ClusterOperator summary is partially available.',
      tone: 'warn',
    };
  }

  if (error) {
    return {
      label: 'Operator 확인 필요',
      title: error,
      tone: 'danger',
    };
  }

  return {
    label: loading ? 'Operator 수집 중' : 'Operator 대기',
    title: 'ClusterOperator summary is not available yet.',
    tone: 'neutral',
  };
};

export const renderStatusTag = (
  label: string,
  tone: RailTone = 'neutral',
  title?: string,
  icon?: React.ReactNode,
) => (
  <span className={`komsco-ai__scope-tag komsco-ai__scope-tag--${tone}`} title={title}>
    {icon && <span className="komsco-ai__scope-tag-icon">{icon}</span>}
    {label}
  </span>
);

const renderHeaderOpsChip = (
  label: string,
  tone: RailTone,
  title: string,
  icon: React.ReactNode,
) => (
  <span className={`komsco-ai__header-op-chip komsco-ai__header-op-chip--${tone}`} title={title}>
    <span className="komsco-ai__header-op-icon">{icon}</span>
    <span>{label}</span>
  </span>
);

export const renderHeaderOpsStatus = (
  summary: ClusterSummary | null,
  loading: boolean,
  error: string,
) => {
  const nodeStatus = getNodeCompactStatus(summary, loading, error);
  const operatorStatus = getOperatorCompactStatus(summary, loading, error);

  const headerNodeLabel = nodeStatus.label
    .replace(' · Ready', '')
    .replace(' 부분 확인', '')
    .replace(' 확인 필요', '');
  const headerOperatorLabel =
    summary && getClusterFaultCount(summary) > 0
      ? `Operator 장애 ${getClusterFaultCount(summary)}`
      : summary && summary.operators.progressing > 0
        ? `Operator 진행 ${summary.operators.progressing}`
        : summary &&
            summary.operators.total > 0 &&
            summary.operators.available === summary.operators.total
          ? 'Operator 정상'
          : operatorStatus.label.replace(' 확인 필요', ' 확인');

  return (
    <div className="komsco-ai__header-ops" aria-label="클러스터 운영 상태">
      {renderHeaderOpsChip(
        headerNodeLabel,
        nodeStatus.tone,
        nodeStatus.title,
        <CoolDesktopTowerIcon />,
      )}
      {renderHeaderOpsChip(
        headerOperatorLabel,
        operatorStatus.tone,
        operatorStatus.title,
        operatorStatus.tone === 'ok' ? <CoolCheckIcon /> : <CoolListChecklistIcon />,
      )}
    </div>
  );
};

export const renderRailSummaryBadges = (
  summary: ClusterSummary | null,
  loading: boolean,
  error: string,
) => {
  const nodeStatus = getNodeCompactStatus(summary, loading, error);
  const operatorStatus = getOperatorCompactStatus(summary, loading, error);

  return (
    <div className="komsco-ai__rail-status-pair" aria-label="클러스터 핵심 상태">
      {renderStatusTag(
        nodeStatus.label,
        nodeStatus.tone,
        nodeStatus.title,
        <CoolDesktopTowerIcon />,
      )}
      {renderStatusTag(
        operatorStatus.label,
        operatorStatus.tone,
        operatorStatus.title,
        <CoolWarningIcon />,
      )}
    </div>
  );
};

export const getClusterHost = (apiUrl?: string): string => {
  if (!apiUrl) {
    return 'cluster pending';
  }

  try {
    return new URL(apiUrl).host;
  } catch {
    return apiUrl;
  }
};

export const renderExecutionCapabilityBadges = (
  status: AiopsRuntimeStatus | null,
  executionMode: AiopsExecutionMode,
) => {
  const actionExecutionAvailable = canUseActionExecution(status);
  const unrestrictedAvailable = canUseUnrestrictedCommands(status);
  const readOnlyActive = executionMode === 'read-only';
  const executeActive = executionMode === 'execute';
  const unrestrictedActive = executionMode === 'unrestricted';

  return (
    <div className="komsco-ai__scope-list komsco-ai__scope-list--execution">
      {renderStatusTag(
        '읽기 전용',
        readOnlyActive ? 'ok' : 'neutral',
        '조회와 근거 수집만 수행하고 조치 계획, 승인, 실행은 만들지 않습니다.',
        <CoolShieldCheckIcon />,
      )}
      {renderStatusTag(
        '승인 실행',
        actionExecutionAvailable ? (executeActive ? 'review' : 'ok') : 'warn',
        actionExecutionAvailable
          ? 'Action Executor가 연결되어 승인된 실행 요청을 보낼 수 있습니다.'
          : getActionExecutionDisabledReason(status),
        <CoolTerminalIcon />,
      )}
      {renderStatusTag(
        '실행 무제한',
        unrestrictedActive ? 'danger' : unrestrictedAvailable ? 'review' : 'neutral',
        unrestrictedActive
          ? unrestrictedAvailable
            ? '로컬 실험 모드에서 제한 없는 명령 실행이 허용됩니다.'
            : '실행 무제한 모드가 선택되었습니다. Gateway capability가 OFF이면 실행 시 서버가 거절 사유를 반환합니다.'
          : unrestrictedAvailable
            ? '로컬 실험 모드에서 제한 없는 명령 실행이 허용됩니다.'
            : getUnrestrictedDisabledReason(status),
        <CoolInfoIcon />,
      )}
    </div>
  );
};

export const renderActionLifecycle = (
  aiopsStatus: AiopsRuntimeStatus | null,
  executionMode: AiopsExecutionMode,
) => {
  const summary = getActionLifecycleSummary(aiopsStatus, executionMode);
  const actionExecutorState = !aiopsStatus
    ? 'pending'
    : aiopsStatus.spec.capabilities.actionExecutorConfigured
      ? 'configured'
      : 'not-configured';
  const mutationFlagState = !aiopsStatus
    ? 'pending'
    : aiopsStatus.spec.capabilities.mutationsEnabled
      ? 'enabled'
      : 'disabled';

  return (
    <div
      className="komsco-ai__action-lifecycle"
      data-action-executor-state={actionExecutorState}
      data-execute-guard="sealed-plan-digest active-approval evidence-freshness ssar mutation-flag"
      data-komsco-action-lifecycle
      data-mutation-flag-state={mutationFlagState}
      data-ui-execution-mode={executionMode}
    >
      <div className="komsco-ai__action-lifecycle-steps" aria-label="AIOps action lifecycle">
        {getActionLifecycleSteps(aiopsStatus).map((step) => (
          <div
            className={`komsco-ai__action-lifecycle-step${
              step.count > 0 ? ' komsco-ai__action-lifecycle-step--active' : ''
            }`}
            data-action-lifecycle-step={step.key}
            key={step.key}
          >
            <span>{step.label}</span>
            <strong>{step.count}</strong>
            <small>{step.detail}</small>
          </div>
        ))}
      </div>
      <div className="komsco-ai__action-lifecycle-summary">
        <div className="komsco-ai__action-lifecycle-current">
          <div>
            <strong>{summary.label}</strong>
            <p>{summary.text}</p>
          </div>
          {renderStatusTag(summary.value, summary.tone)}
        </div>
        <p className="komsco-ai__action-lifecycle-proof">
          실행 전 안전장치: 계획 다이제스트, 유효한 승인, 근거 최신성, 권한 검증, 변경 실행 설정을
          확인합니다. 근거가 오래되었거나 만료되면 실행이 막히고 실패 사유로 표시됩니다 — 이 경우 새
          계획과 승인을 다시 만들어야 합니다.
        </p>
      </div>
    </div>
  );
};

export const renderRecordRows = (records: AiopsRecordView[], emptyLabel: string) => {
  if (records.length === 0) {
    return <div className="komsco-ai__rail-empty">{emptyLabel}</div>;
  }

  return records.slice(0, 4).map((record) => {
    const phase = getRecordPhase(record);
    return (
      <div className="komsco-ai__rail-command" key={record.metadata?.name ?? phase}>
        <code>{record.metadata?.name ?? record.kind ?? 'record'}</code>
        <p>{getRecordTargetLabel(record)}</p>
        {renderStatusTag(phaseLabelKo(phase), getPhaseTone(phase))}
      </div>
    );
  });
};
