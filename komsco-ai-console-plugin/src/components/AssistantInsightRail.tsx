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

const text = (language: UiLanguage, ko: string, en: string): string =>
  language === 'ko' ? ko : en;

const countText = (count: number, language: UiLanguage): string =>
  language === 'ko' ? `${count}건` : String(count);

const connectionLabel = (
  summary: ClusterSummary | null,
  error: string,
  aiopsStatusError: string,
  loading: boolean,
  language: UiLanguage,
): string => {
  if (summary) {
    return text(language, '클러스터 연결됨', 'Cluster connected');
  }
  if (error || aiopsStatusError) {
    return text(language, '연결 확인 필요', 'Connection needs check');
  }
  if (loading) {
    return text(language, '연결 확인 중', 'Checking connection');
  }
  return text(language, '연결 대기', 'Connection pending');
};

const capabilityLabel = (
  language: UiLanguage,
  status: boolean | null,
  koOn: string,
  koOff: string,
  koPending: string,
  enOn: string,
  enOff: string,
  enPending: string,
): string => {
  if (status === null) {
    return text(language, koPending, enPending);
  }
  return status ? text(language, koOn, enOn) : text(language, koOff, enOff);
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
  <aside
    className="komsco-ai__insight-rail"
    aria-label={text(language, '현재 분석 컨텍스트', 'Current analysis context')}
  >
    <h2 className="komsco-ai__rail-title">
      {text(language, '현재 클러스터 컨텍스트', 'Current cluster context')}
    </h2>
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
          {connectionLabel(summary && aiopsStatus ? summary : null, error, aiopsStatusError, loading, language)}
        </strong>
      </div>
      <div className="komsco-ai__connection-target">
        {summary?.apiUrl || 'console proxy / gateway'}
      </div>
      <div className="komsco-ai__connection-metrics">
        {summary
          ? `${summary.nodes.ready}/${summary.nodes.total} Ready · ${getClusterUsageSummary(
              summary,
              language,
            )}`
          : error || aiopsStatusError
            ? error || aiopsStatusError
            : text(
                language,
                'Gateway와 cluster summary를 가져오는 중입니다.',
                'Loading Gateway and cluster summary.',
              )}
      </div>
    </div>
    <AssistantConversationRail
      conversationHistory={conversationHistory}
      language={language}
      messages={messages}
    />

    {renderRailSummaryBadges(summary, loading, error, language)}
    <div className={`komsco-ai__health-card komsco-ai__health-card--${getHealthTone(summary)}`}>
      <div className="komsco-ai__health-head">
        <span>{text(language, '클러스터 건강도', 'Cluster health')}</span>
        <span>
          {text(language, '마지막 갱신', 'Last updated')}{' '}
          {formatSummaryTime(summary?.updatedAt, language)}
        </span>
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
      <div className="komsco-ai__rail-error">
        {text(language, '클러스터 요약을 가져오지 못했습니다.', 'Could not load cluster summary.')}{' '}
        {error}
      </div>
    )}

    {aiopsStatusError && (
      <div className="komsco-ai__rail-error">
        {text(language, 'AIOps 상태를 가져오지 못했습니다.', 'Could not load AIOps status.')}{' '}
        {aiopsStatusError}
      </div>
    )}

    <div className="komsco-ai__rail-section">
      <div className="komsco-ai__rail-section-head">
        <strong>{text(language, '노드 상태', 'Node status')}</strong>
        <span>{getNodeCompactStatus(summary, loading, error, language).label}</span>
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
            <div className="komsco-ai__alert-mini-sub">{formatNodeUsage(node, language)}</div>
          </div>
          <span
            className={`komsco-ai__rail-badge${node.ready ? ' komsco-ai__rail-badge--ok' : ''}`}
          >
            {node.ready ? 'READY' : 'CHECK'}
          </span>
        </div>
      ))}
      {summary && summary.nodes.items.length === 0 && (
        <div className="komsco-ai__rail-empty">
          {text(language, '조회 가능한 노드가 없습니다.', 'No nodes are available.')}
        </div>
      )}
    </div>

    <div className="komsco-ai__rail-section">
      <div className="komsco-ai__rail-section-head">
        <strong>{text(language, '클러스터 상태', 'Cluster status')}</strong>
        <span>{summary?.version.version ?? 'version pending'}</span>
      </div>
      <div className="komsco-ai__scope-list">
        {summary
          ? renderStatusTag(
              text(
                language,
                `정상 Operator ${summary.operators.available}/${summary.operators.total}`,
                `Ready Operator ${summary.operators.available}/${summary.operators.total}`,
              ),
              summary.operators.available === summary.operators.total ? 'ok' : 'warn',
            )
          : renderStatusTag(text(language, 'Operator 대기', 'Operator pending'))}
        {summary
          ? renderStatusTag(
              text(
                language,
                `장애 ${getClusterFaultCount(summary)}건`,
                `Faults ${getClusterFaultCount(summary)}`,
              ),
              getClusterFaultCount(summary) > 0 ? 'danger' : 'ok',
              text(
                language,
                'Degraded + Unavailable Operator 수',
                'Degraded + unavailable operator count',
              ),
            )
          : renderStatusTag(text(language, '장애 대기', 'Faults pending'))}
        {summary
          ? renderStatusTag(
              text(
                language,
                `진행 중 ${summary.operators.progressing}건`,
                `Progressing ${summary.operators.progressing}`,
              ),
              summary.operators.progressing > 0 ? 'warn' : 'neutral',
            )
          : renderStatusTag(text(language, '진행 상태 대기', 'Progress pending'))}
        {summary
          ? renderStatusTag(
              summary.version.channel ?? text(language, '채널 미확인', 'Channel unknown'),
              'neutral',
            )
          : renderStatusTag(text(language, '채널 대기', 'Channel pending'))}
        {summary
          ? renderStatusTag(
              summary.version.updateAvailable
                ? text(language, '업데이트 가능', 'Update available')
                : text(language, '업데이트 신호 없음', 'No update signal'),
              summary.version.updateAvailable ? 'review' : 'neutral',
            )
          : renderStatusTag(text(language, '업데이트 대기', 'Update pending'))}
        {summary
          ? renderStatusTag(
              summary.version.upgradeable === false
                ? text(language, '업그레이드 차단', 'Upgrade blocked')
                : text(language, '업그레이드 가능', 'Upgradeable'),
              summary.version.upgradeable === false ? 'warn' : 'ok',
              summary.version.upgradeableMessage,
            )
          : renderStatusTag(text(language, '업그레이드 상태 대기', 'Upgrade status pending'))}
        {summary
          ? renderStatusTag(
              text(
                language,
                `메트릭 ${summary.nodes.metricsAvailable ? '수집 가능' : '수집 불가'}`,
                `Metrics ${summary.nodes.metricsAvailable ? 'available' : 'unavailable'}`,
              ),
              summary.nodes.metricsAvailable ? 'ok' : 'warn',
            )
          : renderStatusTag(text(language, '메트릭 대기', 'Metrics pending'))}
      </div>
    </div>

    <div className="komsco-ai__rail-section">
      <div className="komsco-ai__rail-section-head">
        <strong>{text(language, 'Operator 이슈', 'Operator issues')}</strong>
        <span>{getOperatorCompactStatus(summary, loading, error, language).label}</span>
      </div>
      {(summary?.operators.issues ?? []).slice(0, 5).map((operator) => (
        <div
          className={`komsco-ai__rail-command komsco-ai__rail-command--${getOperatorTone(
            operator,
          )}`}
          key={operator.name}
        >
          <code>{operator.name}</code>
          <p>
            {operator.reason ||
              operator.message ||
              text(language, '상태 확인 필요', 'Status needs check')}
          </p>
        </div>
      ))}
      {summary && summary.operators.issues.length === 0 && (
        <div className="komsco-ai__rail-empty">
          {text(language, '주요 Operator 이슈가 없습니다.', 'No major operator issues.')}
        </div>
      )}
    </div>

    <div className="komsco-ai__rail-section">
      <div className="komsco-ai__rail-section-head">
        <strong>{text(language, 'AIOps 실행 상태', 'AIOps execution status')}</strong>
        <span>
          {aiopsStatus
            ? text(language, '연결됨', 'Connected')
            : aiopsStatusError
              ? text(language, '확인 필요', 'Needs check')
              : text(language, '수집 중', 'Loading')}
        </span>
      </div>
      {renderExecutionCapabilityBadges(aiopsStatus, executionMode, language)}
      <div className="komsco-ai__scope-list komsco-ai__scope-list--secondary">
        {renderStatusTag(
          capabilityLabel(
            language,
            aiopsStatus ? aiopsStatus.spec.capabilities.diagnosticsEnabled : null,
            '진단 가능',
            '진단 꺼짐',
            '진단 상태 대기',
            'Diagnostics ready',
            'Diagnostics off',
            'Diagnostics pending',
          ),
          aiopsStatus
            ? aiopsStatus.spec.capabilities.diagnosticsEnabled
              ? 'ok'
              : 'warn'
            : 'neutral',
        )}
        {renderStatusTag(
          capabilityLabel(
            language,
            aiopsStatus ? aiopsStatus.spec.capabilities.mutationsEnabled : null,
            '변경 실행 가능',
            '변경 실행 꺼짐',
            '변경 실행 대기',
            'Mutation ready',
            'Mutation off',
            'Mutation pending',
          ),
          aiopsStatus
            ? aiopsStatus.spec.capabilities.mutationsEnabled
              ? 'review'
              : 'neutral'
            : 'neutral',
        )}
        {renderStatusTag(
          capabilityLabel(
            language,
            aiopsStatus ? aiopsStatus.spec.capabilities.recordStoreEnabled : null,
            '감사 기록 가능',
            '감사 기록 꺼짐',
            '감사 기록 대기',
            'Audit ready',
            'Audit off',
            'Audit pending',
          ),
          aiopsStatus
            ? aiopsStatus.spec.capabilities.recordStoreEnabled
              ? 'ok'
              : 'warn'
            : 'neutral',
        )}
        {renderStatusTag(
          aiopsStatus
            ? aiopsStatus.spec.capabilities.rag?.status === 'not_configured'
              ? text(language, 'RAG 미설정', 'RAG not configured')
              : aiopsStatus.spec.capabilities.rag?.status === 'configured_skeleton'
                ? text(language, 'RAG 골격 연결', 'RAG skeleton connected')
                : `RAG ${aiopsStatus.spec.capabilities.rag?.status ?? 'unknown'}`
            : text(language, 'RAG 대기', 'RAG pending'),
          aiopsStatus
            ? aiopsStatus.spec.capabilities.rag?.status === 'not_configured'
              ? 'warn'
              : 'neutral'
            : 'neutral',
        )}
      </div>
      {aiopsStatusError && (
        <div className="komsco-ai__rail-error">
          {text(language, 'AIOps 상태를 가져오지 못했습니다.', 'Could not load AIOps status.')}
        </div>
      )}
    </div>

    <div className="komsco-ai__rail-section">
      <div className="komsco-ai__rail-section-head">
        <strong>{text(language, '답변 근거', 'Answer evidence')}</strong>
        <span>
          {rcaStatusLabel(aiopsStatus?.spec.safetyContract?.rcaContextStatus?.status, language)}
        </span>
      </div>
      <div className="komsco-ai__scope-list">
        {renderStatusTag(
          text(
            language,
            `수집 ${rcaRailEvidenceCounts(aiopsStatus).collected}건`,
            `Collected ${rcaRailEvidenceCounts(aiopsStatus).collected}`,
          ),
          'ok',
        )}
        {renderStatusTag(
          text(
            language,
            `추가 확인 ${rcaRailEvidenceCounts(aiopsStatus).missing}건`,
            `Needs check ${rcaRailEvidenceCounts(aiopsStatus).missing}`,
          ),
          'warn',
        )}
      </div>
      <div className="komsco-ai__rail-command">
        <p>
          {aiopsStatus?.spec.safetyContract?.rcaContextStatus?.latestContext
            ? text(
                language,
                '최근 답변에 사용한 근거가 연결되어 있습니다.',
                'Evidence used by the latest answer is connected.',
              )
            : text(
                language,
                '질문 실행 후 답변 근거가 연결됩니다.',
                'Answer evidence is connected after a question runs.',
              )}
        </p>
      </div>
    </div>

    <div className="komsco-ai__rail-section">
      <div className="komsco-ai__rail-section-head">
        <strong>{text(language, '최근 진단', 'Recent diagnostics')}</strong>
        <span>
          {aiopsStatus
            ? countText(aiopsStatus.spec.records.diagnosticRequests.length, language)
            : text(language, '대기', 'Pending')}
        </span>
      </div>
      {renderRecordRows(
        aiopsStatus?.spec.records.diagnosticRequests ?? [],
        text(language, '최근 진단 요청이 없습니다.', 'No recent diagnostic requests.'),
        language,
      )}
    </div>

    <div className="komsco-ai__rail-section">
      <div className="komsco-ai__rail-section-head">
        <strong>{text(language, '승인·실행', 'Approval and execution')}</strong>
        <span>
          {aiopsStatus
            ? countText(
                aiopsStatus.spec.records.actionProposals.length +
                  aiopsStatus.spec.records.sealedActionPlans.length +
                  aiopsStatus.spec.records.approvalDecisions.length +
                  aiopsStatus.spec.records.executionRecords.length,
                language,
              )
            : text(language, '대기', 'Pending')}
        </span>
      </div>
      {renderActionLifecycle(aiopsStatus, executionMode, language)}
      {aiopsActionError && <div className="komsco-ai__rail-error">{aiopsActionError}</div>}
      {aiopsActionNotice && <div className="komsco-ai__rail-success">{aiopsActionNotice}</div>}
      <AssistantRailActionRecords
        aiopsStatus={aiopsStatus}
        busyActionId={aiopsActionBusyId}
        collapseRemaining
        emptyLabel={text(
          language,
          '최근 승인 또는 실행 기록이 없습니다.',
          'No recent approval or execution records.',
        )}
        executionMode={executionMode}
        language={language}
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
