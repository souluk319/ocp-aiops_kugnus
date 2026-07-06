import * as React from 'react';
import { AssistantRailActionRecords } from './AssistantActionRecords';
import AssistantConversationRail from './AssistantConversationRail';
import { getAiopsRecordAction } from './assistant.actionState';
import { rcaRailEvidenceCounts, rcaStatusLabel } from './assistant.evidence';
import {
  formatNodeUsage,
  formatSummaryTime,
  getClusterFaultCount,
  getClusterUsageSummary,
  getHealthTone,
  getNodeCompactStatus,
  getOperatorCompactStatus,
  getOperatorTone,
  renderActionLifecycle,
  renderExecutionCapabilityBadges,
  renderRailSummaryBadges,
  renderRecordRows,
  renderStatusTag,
} from './assistant.insightRailHelpers';
import type {
  AiopsExecutionMode,
  AiopsRecordAction,
  AiopsRecordView,
  ConversationHistoryItem,
  Message,
  UiLanguage,
} from './assistant.types';
import type { AiopsRuntimeStatus, ClusterSummary } from '../services/aiGateway';

type AssistantInsightRailProps = {
  aiopsActionBusyId: string;
  aiopsActionError: string;
  aiopsActionNotice: string;
  aiopsStatus: AiopsRuntimeStatus | null;
  aiopsStatusError: string;
  conversationHistory: ConversationHistoryItem[];
  error: string;
  executionMode: AiopsExecutionMode;
  language: UiLanguage;
  loading: boolean;
  messages: Message[];
  onAiopsAction: (record: AiopsRecordView, action: AiopsRecordAction) => void;
  summary: ClusterSummary | null;
};

const AssistantInsightRail: React.FC<AssistantInsightRailProps> = ({
  aiopsActionBusyId,
  aiopsActionError,
  aiopsActionNotice,
  aiopsStatus,
  aiopsStatusError,
  conversationHistory,
  error,
  executionMode,
  language,
  loading,
  messages,
  onAiopsAction,
  summary,
}) => (
  <aside className="komsco-ai__insight-rail" aria-label="현재 분석 컨텍스트">
    <h2 className="komsco-ai__rail-title">현재 클러스터 컨텍스트</h2>
    <div
      className={`komsco-ai__connection-card${
        summary
          ? ' komsco-ai__connection-card--connected'
          : error || aiopsStatusError
            ? ' komsco-ai__connection-card--danger'
            : ''
      }`}
    >
      <div className="komsco-ai__connection-main">
        <span
          className={`komsco-ai__connection-dot${
            summary && aiopsStatus ? ' komsco-ai__connection-dot--connected' : ''
          }`}
        />
        <strong>
          {summary && aiopsStatus
            ? '클러스터 연결됨'
            : error || aiopsStatusError
              ? '연결 확인 필요'
              : loading
                ? '연결 확인 중'
                : '연결 대기'}
        </strong>
      </div>
      <div className="komsco-ai__connection-target">
        {summary?.apiUrl || 'console proxy / gateway'}
      </div>
      <div className="komsco-ai__connection-metrics">
        {summary
          ? `${summary.nodes.ready}/${summary.nodes.total} Ready · ${getClusterUsageSummary(summary)}`
          : error || aiopsStatusError
            ? error || aiopsStatusError
            : 'Gateway와 cluster summary를 가져오는 중입니다.'}
      </div>
    </div>
    <AssistantConversationRail
      conversationHistory={conversationHistory}
      language={language}
      messages={messages}
    />

    {renderRailSummaryBadges(summary, loading, error)}
    <div className={`komsco-ai__health-card komsco-ai__health-card--${getHealthTone(summary)}`}>
      <div className="komsco-ai__health-head">
        <span>클러스터 건강도</span>
        <span>마지막 갱신 {formatSummaryTime(summary?.updatedAt)}</span>
      </div>
      <div className="komsco-ai__health-score">
        {summary ? summary.healthScore : loading ? '...' : '--'} <small>/ 100</small>
      </div>
      <div className={`komsco-ai__health-bar${summary ? '' : ' komsco-ai__health-bar--pending'}`}>
        {summary ? (
          <span
            className={`komsco-ai__health-bar-fill komsco-ai__health-bar-fill--${getHealthTone(
              summary,
            )}`}
            style={{ width: `${summary.healthScore}%` }}
          />
        ) : (
          <span className="komsco-ai__health-bar-placeholder">status pending</span>
        )}
      </div>
    </div>

    {error && (
      <div className="komsco-ai__rail-error">클러스터 요약을 가져오지 못했습니다. {error}</div>
    )}

    {aiopsStatusError && (
      <div className="komsco-ai__rail-error">
        AIOps 상태를 가져오지 못했습니다. {aiopsStatusError}
      </div>
    )}

    <div className="komsco-ai__rail-section">
      <div className="komsco-ai__rail-section-head">
        <strong>노드 상태</strong>
        <span>{getNodeCompactStatus(summary, loading, error).label}</span>
      </div>
      {(summary?.nodes.items ?? []).slice(0, 5).map((node) => (
        <div className="komsco-ai__alert-mini" key={node.name}>
          <span
            className={`komsco-ai__alert-mini-dot${
              node.ready && !Object.values(node.pressures).some(Boolean)
                ? ' komsco-ai__alert-mini-dot--green'
                : ''
            }`}
          />
          <div>
            <div className="komsco-ai__alert-mini-title">{node.name}</div>
            <div className="komsco-ai__alert-mini-sub">
              {node.roles.join(', ')} · {node.kubeletVersion ?? 'version unknown'}
            </div>
            <div className="komsco-ai__alert-mini-sub">{formatNodeUsage(node)}</div>
          </div>
          <span
            className={`komsco-ai__rail-badge${node.ready ? ' komsco-ai__rail-badge--ok' : ''}`}
          >
            {node.ready ? 'READY' : 'CHECK'}
          </span>
        </div>
      ))}
      {summary && summary.nodes.items.length === 0 && (
        <div className="komsco-ai__rail-empty">조회 가능한 노드가 없습니다.</div>
      )}
    </div>

    <div className="komsco-ai__rail-section">
      <div className="komsco-ai__rail-section-head">
        <strong>클러스터 상태</strong>
        <span>{summary?.version.version ?? 'version pending'}</span>
      </div>
      <div className="komsco-ai__scope-list">
        {summary
          ? renderStatusTag(
              `정상 Operator ${summary.operators.available}/${summary.operators.total}`,
              summary.operators.available === summary.operators.total ? 'ok' : 'warn',
            )
          : renderStatusTag('Operator 대기')}
        {summary
          ? renderStatusTag(
              `장애 ${getClusterFaultCount(summary)}건`,
              getClusterFaultCount(summary) > 0 ? 'danger' : 'ok',
              'Degraded + Unavailable Operator 수',
            )
          : renderStatusTag('장애 대기')}
        {summary
          ? renderStatusTag(
              `진행 중 ${summary.operators.progressing}건`,
              summary.operators.progressing > 0 ? 'warn' : 'neutral',
            )
          : renderStatusTag('진행 상태 대기')}
        {summary
          ? renderStatusTag(summary.version.channel ?? '채널 미확인', 'neutral')
          : renderStatusTag('채널 대기')}
        {summary
          ? renderStatusTag(
              summary.version.updateAvailable ? '업데이트 가능' : '업데이트 신호 없음',
              summary.version.updateAvailable ? 'review' : 'neutral',
            )
          : renderStatusTag('업데이트 대기')}
        {summary
          ? renderStatusTag(
              summary.version.upgradeable === false ? '업그레이드 차단' : '업그레이드 가능',
              summary.version.upgradeable === false ? 'warn' : 'ok',
              summary.version.upgradeableMessage,
            )
          : renderStatusTag('업그레이드 상태 대기')}
        {summary
          ? renderStatusTag(
              `메트릭 ${summary.nodes.metricsAvailable ? '수집 가능' : '수집 불가'}`,
              summary.nodes.metricsAvailable ? 'ok' : 'warn',
            )
          : renderStatusTag('메트릭 대기')}
      </div>
    </div>

    <div className="komsco-ai__rail-section">
      <div className="komsco-ai__rail-section-head">
        <strong>Operator 이슈</strong>
        <span>{getOperatorCompactStatus(summary, loading, error).label}</span>
      </div>
      {(summary?.operators.issues ?? []).slice(0, 5).map((operator) => (
        <div
          className={`komsco-ai__rail-command komsco-ai__rail-command--${getOperatorTone(
            operator,
          )}`}
          key={operator.name}
        >
          <code>{operator.name}</code>
          <p>{operator.reason || operator.message || '상태 확인 필요'}</p>
        </div>
      ))}
      {summary && summary.operators.issues.length === 0 && (
        <div className="komsco-ai__rail-empty">주요 Operator 이슈가 없습니다.</div>
      )}
    </div>

    <div className="komsco-ai__rail-section">
      <div className="komsco-ai__rail-section-head">
        <strong>AIOps 실행 상태</strong>
        <span>{aiopsStatus ? '연결됨' : aiopsStatusError ? '확인 필요' : '수집 중'}</span>
      </div>
      {renderExecutionCapabilityBadges(aiopsStatus, executionMode, language)}
      <div className="komsco-ai__scope-list komsco-ai__scope-list--secondary">
        {renderStatusTag(
          aiopsStatus
            ? aiopsStatus.spec.capabilities.diagnosticsEnabled
              ? '진단 가능'
              : '진단 꺼짐'
            : '진단 상태 대기',
          aiopsStatus
            ? aiopsStatus.spec.capabilities.diagnosticsEnabled
              ? 'ok'
              : 'warn'
            : 'neutral',
        )}
        {renderStatusTag(
          aiopsStatus
            ? aiopsStatus.spec.capabilities.mutationsEnabled
              ? '변경 실행 가능'
              : '변경 실행 꺼짐'
            : '변경 실행 대기',
          aiopsStatus
            ? aiopsStatus.spec.capabilities.mutationsEnabled
              ? 'review'
              : 'neutral'
            : 'neutral',
        )}
        {renderStatusTag(
          aiopsStatus
            ? aiopsStatus.spec.capabilities.recordStoreEnabled
              ? '감사 기록 가능'
              : '감사 기록 꺼짐'
            : '감사 기록 대기',
          aiopsStatus
            ? aiopsStatus.spec.capabilities.recordStoreEnabled
              ? 'ok'
              : 'warn'
            : 'neutral',
        )}
        {renderStatusTag(
          aiopsStatus
            ? aiopsStatus.spec.capabilities.rag?.status === 'not_configured'
              ? 'RAG 미설정'
              : aiopsStatus.spec.capabilities.rag?.status === 'configured_skeleton'
                ? 'RAG 골격 연결'
                : `RAG ${aiopsStatus.spec.capabilities.rag?.status ?? 'unknown'}`
            : 'RAG 대기',
          aiopsStatus
            ? aiopsStatus.spec.capabilities.rag?.status === 'not_configured'
              ? 'warn'
              : 'neutral'
            : 'neutral',
        )}
      </div>
      {aiopsStatusError && (
        <div className="komsco-ai__rail-error">AIOps 상태를 가져오지 못했습니다.</div>
      )}
    </div>

    <div className="komsco-ai__rail-section">
      <div className="komsco-ai__rail-section-head">
        <strong>답변 근거</strong>
        <span>{rcaStatusLabel(aiopsStatus?.spec.safetyContract?.rcaContextStatus?.status)}</span>
      </div>
      <div className="komsco-ai__scope-list">
        {renderStatusTag(`수집 ${rcaRailEvidenceCounts(aiopsStatus).collected}건`, 'ok')}
        {renderStatusTag(`추가 확인 ${rcaRailEvidenceCounts(aiopsStatus).missing}건`, 'warn')}
      </div>
      <div className="komsco-ai__rail-command">
        <p>
          {aiopsStatus?.spec.safetyContract?.rcaContextStatus?.latestContext
            ? '최근 답변에 사용한 근거가 연결되어 있습니다.'
            : '질문 실행 후 답변 근거가 연결됩니다.'}
        </p>
      </div>
    </div>

    <div className="komsco-ai__rail-section">
      <div className="komsco-ai__rail-section-head">
        <strong>최근 진단</strong>
        <span>
          {aiopsStatus ? `${aiopsStatus.spec.records.diagnosticRequests.length}건` : '대기'}
        </span>
      </div>
      {renderRecordRows(
        aiopsStatus?.spec.records.diagnosticRequests ?? [],
        '최근 진단 요청이 없습니다.',
      )}
    </div>

    <div className="komsco-ai__rail-section">
      <div className="komsco-ai__rail-section-head">
        <strong>승인·실행</strong>
        <span>
          {aiopsStatus
            ? `${
                aiopsStatus.spec.records.actionProposals.length +
                aiopsStatus.spec.records.sealedActionPlans.length +
                aiopsStatus.spec.records.approvalDecisions.length +
                aiopsStatus.spec.records.executionRecords.length
              }건`
            : '대기'}
        </span>
      </div>
      {renderActionLifecycle(aiopsStatus, executionMode)}
      {aiopsActionError && <div className="komsco-ai__rail-error">{aiopsActionError}</div>}
      {aiopsActionNotice && <div className="komsco-ai__rail-success">{aiopsActionNotice}</div>}
      <AssistantRailActionRecords
        aiopsStatus={aiopsStatus}
        busyActionId={aiopsActionBusyId}
        collapseRemaining
        emptyLabel="최근 승인 또는 실행 기록이 없습니다."
        executionMode={executionMode}
        onAction={onAiopsAction}
        records={[
          ...(aiopsStatus?.spec.records.actionProposals ?? []),
          ...(aiopsStatus?.spec.records.sealedActionPlans ?? []),
          ...(aiopsStatus?.spec.records.approvalDecisions ?? []),
          ...(aiopsStatus?.spec.records.executionRecords ?? []),
        ].sort(
          (a, b) =>
            new Date(String(b.metadata?.createdAt ?? 0)).getTime() -
            new Date(String(a.metadata?.createdAt ?? 0)).getTime(),
        )}
        resolveAction={getAiopsRecordAction}
        visibleLimit={3}
      />
    </div>
  </aside>
);

export default AssistantInsightRail;
