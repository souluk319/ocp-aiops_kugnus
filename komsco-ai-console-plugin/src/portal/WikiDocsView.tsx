import * as React from 'react';
import { FileText, Search, Upload, X } from 'lucide-react';
import {
  fetchRagUploadedDocuments,
  searchRagDocuments,
  uploadRagDocumentFile,
} from './api';
import { StatusBadge } from './portalBadges';
import { formatTime } from './portalModel';
import type {
  RagSearchResultItem,
  RagUploadedDocument,
  RagUploadedDocumentList,
  Severity,
} from './types';

const Panel: React.FC<{
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  title: string;
}> = ({ action, children, className = '', title }) => (
  <section className={`portal-panel ${className}`}>
    <div className="portal-panel__head">
      <div className="portal-panel__title">{title}</div>
      {action}
    </div>
    <div className="portal-panel__body">{children}</div>
  </section>
);

const EmptyState: React.FC<{ label: string }> = ({ label }) => (
  <div className="empty-state">{label}</div>
);

type KnowledgeDoc = {
  category: string;
  chunks: number;
  dataSource: 'gateway' | 'sample';
  id: string;
  keywords: string[];
  linkedIssues: string[];
  owner: string;
  rcaLinks: number;
  searchStatus: '색인 완료' | '검증 필요' | '초안';
  status: '검증됨' | '검증 필요' | '초안';
  targetScopes: string[];
  title: string;
  updatedAt: string;
  verifiedAt: string;
  version: string;
  summary: string;
  tags: string[];
  steps: string[];
};

type WikiUploadItem = {
  chunks: number;
  collection: string;
  detail?: string;
  id: string;
  name: string;
  size: string;
  status: '업로드 대기' | '업로드 중' | '검증 필요' | '색인됨' | '실패';
  type: string;
  updatedAt: string;
};

const sampleKnowledgeDocs: KnowledgeDoc[] = [
  {
    category: '장애 대응',
    chunks: 12,
    dataSource: 'sample',
    id: 'runbook-crashloop',
    keywords: ['CrashLoopBackOff', 'BackOff', 'restart count', 'exit code', 'image pull'],
    linkedIssues: ['Pods degraded', 'Deployment availability drift', 'CrashLoopBackOff detected'],
    owner: 'AIOps 운영팀',
    rcaLinks: 3,
    searchStatus: '색인 완료',
    status: '검증됨',
    targetScopes: ['Pod', 'Deployment', 'ReplicaSet', 'RCA'],
    title: 'CrashLoopBackOff 파드 대응 런북',
    updatedAt: '07. 03. 오전 09:20',
    verifiedAt: '07. 03. 오전 09:20',
    version: 'v1.7',
    summary: '반복 재시작 파드의 이벤트, 로그, 최근 배포 변경을 분리해 확인하는 표준 절차입니다.',
    tags: ['Pod', 'Deployment', 'RCA'],
    steps: ['최근 이벤트와 종료 코드를 확인합니다.', '동일 ReplicaSet 내 Pod 상태와 로그를 비교합니다.', '배포 변경, 이미지 pull, probe 실패를 분리합니다.', '승인 게이트 필요 시 변경 요청을 생성합니다.'],
  },
  {
    category: '변경 통제',
    chunks: 8,
    dataSource: 'sample',
    id: 'policy-approval',
    keywords: ['approval gate', 'audit', 'change request', '자동 조치', '승인 정책'],
    linkedIssues: ['조치 승인 대기', 'Runbook gate required'],
    owner: '플랫폼 아키텍트',
    rcaLinks: 2,
    searchStatus: '색인 완료',
    status: '검증됨',
    targetScopes: ['Approval', 'Audit', 'Runbook', 'Policy'],
    title: 'AIOps 조치 승인 정책',
    updatedAt: '07. 02. 오후 05:40',
    verifiedAt: '07. 02. 오후 05:40',
    version: 'v2.1',
    summary: '자동 조치 제안, 승인 검증, 실행 원장 기록에 필요한 운영 통제 기준입니다.',
    tags: ['Approval', 'Audit', 'Policy'],
    steps: ['읽기/증거 수집 단계와 변경 실행 단계를 분리합니다.', '운영자 승인 없이 클러스터 변경을 실행하지 않습니다.', '모든 실행 결과는 감사 원장에 남깁니다.'],
  },
  {
    category: '업데이트',
    chunks: 10,
    dataSource: 'sample',
    id: 'ocp-update-check',
    keywords: ['ClusterVersion', 'Upgradeable=False', 'AdminAck', 'conditional update', '4.20'],
    linkedIssues: ['OCP 업데이트 사전 확인 필요', 'Admin acknowledgement required'],
    owner: 'OpenShift 운영팀',
    rcaLinks: 1,
    searchStatus: '검증 필요',
    status: '검증 필요',
    targetScopes: ['ClusterVersion', 'Update', 'AdminAck', 'Operator'],
    title: 'OCP 업데이트 차단 사전 점검',
    updatedAt: '07. 01. 오후 02:10',
    verifiedAt: '07. 01. 오후 02:10',
    version: 'v0.9',
    summary: 'ClusterVersion Upgradeable=False, AdminAck, conditional update 항목을 점검하는 문서입니다.',
    tags: ['ClusterVersion', 'Update', 'AdminAck'],
    steps: ['ClusterVersion condition을 확인합니다.', '추천 업데이트와 조건부 업데이트를 분리합니다.', 'AdminAck 또는 mirror signature 준비 여부를 확인합니다.'],
  },
];

const formatUploadSize = (size: number): string => {
  if (size >= 1024 * 1024) {
    return `${(size / 1024 / 1024).toFixed(1)} MB`;
  }
  if (size >= 1024) {
    return `${Math.ceil(size / 1024)} KB`;
  }
  return `${size} B`;
};

const uploadStatusSeverity = (status: WikiUploadItem['status']): Severity =>
  status === '색인됨' ? 'ok' : status === '실패' ? 'risk' : 'warn';

const docStatusSeverity = (status: KnowledgeDoc['status']): Severity =>
  status === '검증됨' ? 'ok' : status === '초안' ? 'warn' : 'risk';

const docStatusLabel = (doc: KnowledgeDoc): string =>
  doc.dataSource === 'sample' ? '샘플' : doc.status;

const ragListDocuments = (payload: RagUploadedDocumentList | null): RagUploadedDocument[] =>
  payload?.spec.documents ?? payload?.spec.items ?? [];

const ragDateLabel = (value?: string): string => (value ? formatTime(value) : '-');

const ragDocLabelValues = (doc: RagUploadedDocument): string[] =>
  Array.from(new Set([
    doc.labels?.domain,
    doc.labels?.scenario,
    doc.labels?.source,
    doc.namespace,
    doc.sourceType,
  ].filter((value): value is string => Boolean(value && value.trim()))));

const ragUploadedDocumentToKnowledgeDoc = (doc: RagUploadedDocument): KnowledgeDoc => {
  const labelValues = ragDocLabelValues(doc);
  const title = doc.title || doc.documentId;
  const tags = labelValues.length > 0 ? labelValues.slice(0, 4) : ['Runbook'];
  const updatedAt = ragDateLabel(doc.updatedAt || doc.ingestedAt);
  const chunks = Math.max(1, Number(doc.chunkCount ?? 0));

  return {
    category: doc.labels?.category || doc.sourceType || '운영 문서',
    chunks,
    dataSource: 'gateway',
    id: doc.documentId,
    keywords: Array.from(new Set([title, doc.sourceType, doc.namespace, doc.customer, ...tags].filter((value): value is string => Boolean(value)))),
    linkedIssues: doc.labels?.scenario ? [doc.labels.scenario] : ['RAG 검색 대상'],
    owner: doc.uploadedBy || 'Gateway RAG',
    rcaLinks: 0,
    searchStatus: '색인 완료',
    status: '검증됨',
    targetScopes: tags,
    title,
    updatedAt,
    verifiedAt: updatedAt,
    version: doc.version || '-',
    summary: `${doc.customer ?? 'komsco'} / ${doc.namespace ?? 'namespace 미지정'} · ${chunks}개 chunk · ${doc.mimeType ?? '문서'}`,
    tags,
    steps: [
      'Gateway RAG 업로드 목록에서 확인된 운영 문서입니다.',
      '검색 테스트로 관련 chunk가 반환되는지 확인합니다.',
      'RCA 답변에서는 문서 위치와 원문을 상세 보기로 분리합니다.',
    ],
  };
};

const ragSearchResultToKnowledgeDoc = (result: RagSearchResultItem, index: number): KnowledgeDoc => {
  const title = result.title || result.documentId || `검색 결과 ${index + 1}`;
  const tags = [result.sourceType, result.namespace, result.customer, result.version]
    .filter((value): value is string => Boolean(value && value.trim()))
    .slice(0, 4);

  return {
    category: result.sourceType || '검색 결과',
    chunks: Number(result.metadata?.chunkIndex ?? index + 1) + 1,
    dataSource: 'gateway',
    id: result.id || result.documentId || `rag-search-${index}`,
    keywords: [title, ...tags],
    linkedIssues: ['RAG 검색 결과'],
    owner: 'Gateway RAG',
    rcaLinks: 0,
    searchStatus: '색인 완료',
    status: '검증됨',
    targetScopes: tags.length > 0 ? tags : ['Runbook'],
    title,
    updatedAt: '-',
    verifiedAt: '-',
    version: result.version || '-',
    summary: result.contentPreview || 'Gateway RAG 검색에서 반환된 문서 chunk입니다.',
    tags: tags.length > 0 ? tags : ['Runbook'],
    steps: ['검색 결과의 문서 제목과 chunk 점수를 확인합니다.', '운영 답변에서는 원문 URL 대신 문서명을 먼저 노출합니다.'],
  };
};

const buildDocSearchResults = (docs: KnowledgeDoc[], query: string, activeDoc: KnowledgeDoc): Array<{ doc: KnowledgeDoc; score: string; reason: string }> => {
  const normalized = query.trim().toLowerCase();
  return docs
    .map((doc, index) => {
      const haystack = `${doc.title} ${doc.summary} ${doc.tags.join(' ')} ${doc.keywords.join(' ')}`.toLowerCase();
      const exactMatch = normalized ? haystack.includes(normalized) : doc.id === activeDoc.id;
      const keywordMatch = normalized
        ? doc.keywords.some((keyword) => normalized.includes(keyword.toLowerCase()) || keyword.toLowerCase().includes(normalized))
        : false;
      const baseScore = doc.id === activeDoc.id ? 0.91 : exactMatch ? 0.84 : keywordMatch ? 0.78 : 0.64 - index * 0.06;
      return {
        doc,
        reason: doc.id === activeDoc.id ? '선택 문서 절차와 키워드 매칭' : `${doc.tags.slice(0, 2).join(', ')} 근거 chunk 매칭`,
        score: Math.max(0.42, baseScore).toFixed(2),
      };
    })
    .sort((left, right) => Number(right.score) - Number(left.score))
    .slice(0, 3);
};

const WikiUploadDrawer: React.FC<{
  dragActive: boolean;
  handleUploadFiles: (fileList: FileList | null) => void;
  indexedCount: number;
  onClose: () => void;
  open: boolean;
  ragChunkSize: string;
  ragCollection: string;
  setDragActive: (value: boolean) => void;
  setRagChunkSize: (value: string) => void;
  setRagCollection: (value: string) => void;
  setShowAdvancedSettings: React.Dispatch<React.SetStateAction<boolean>>;
  showAdvancedSettings: boolean;
  uploadItems: WikiUploadItem[];
}> = ({
  dragActive,
  handleUploadFiles,
  indexedCount,
  onClose,
  open,
  ragChunkSize,
  ragCollection,
  setDragActive,
  setRagChunkSize,
  setRagCollection,
  setShowAdvancedSettings,
  showAdvancedSettings,
  uploadItems,
}) => (
  <div className={`portal-drawer wiki-drawer wiki-upload-drawer ${open ? 'is-open' : ''}`} onClick={onClose}>
    <aside className="portal-drawer__panel" onClick={(event) => event.stopPropagation()}>
      <div className="portal-drawer__head">
        <div>
          <span>문서 추가</span>
          <strong>Runbook 문서 업로드</strong>
        </div>
        <button aria-label="닫기" className="portal-icon-btn" onClick={onClose} title="닫기" type="button">
          <X />
        </button>
      </div>
      <div className="portal-drawer__body">
        <div
          className={`rag-dropzone ${dragActive ? 'is-active' : ''}`}
          onDragLeave={() => setDragActive(false)}
          onDragOver={(event) => {
            event.preventDefault();
            setDragActive(true);
          }}
          onDrop={(event) => {
            event.preventDefault();
            setDragActive(false);
            handleUploadFiles(event.dataTransfer.files);
          }}
        >
          <Upload />
          <div>
            <strong>운영 지식으로 색인할 문서 선택</strong>
            <p>PDF, DOCX, MD, TXT, YAML, 로그 파일을 업로드할 수 있습니다.</p>
          </div>
          <label className="portal-button" htmlFor="wiki-upload-input">파일 선택</label>
          <input
            accept=".pdf,.doc,.docx,.md,.txt,.yaml,.yml,.json,.log"
            hidden
            id="wiki-upload-input"
            multiple
            onChange={(event) => {
              handleUploadFiles(event.target.files);
              event.target.value = '';
            }}
            type="file"
          />
        </div>
        <button className="wiki-advanced-toggle" onClick={() => setShowAdvancedSettings((value) => !value)} type="button">
          고급 설정 {showAdvancedSettings ? '접기' : '보기'}
        </button>
        {showAdvancedSettings && (
          <div className="rag-ingest-settings">
            <label>
              <span>컬렉션</span>
              <select onChange={(event) => setRagCollection(event.target.value)} value={ragCollection}>
                <option value="ocp-runbooks">ocp-runbooks</option>
                <option value="incident-rca">incident-rca</option>
                <option value="platform-policy">platform-policy</option>
              </select>
            </label>
            <label>
              <span>Chunk 크기</span>
              <select onChange={(event) => setRagChunkSize(event.target.value)} value={ragChunkSize}>
                <option value="600">600 tokens</option>
                <option value="900">900 tokens</option>
                <option value="1200">1200 tokens</option>
              </select>
            </label>
            <label>
              <span>검색 범위</span>
              <select defaultValue="ops">
                <option value="ops">운영팀 공개</option>
                <option value="private">업로드 사용자만</option>
                <option value="all">전체 포털</option>
              </select>
            </label>
          </div>
        )}
        <section className="wiki-drawer-section">
          <strong>업로드 대기열</strong>
          {uploadItems.length === 0 ? (
            <div className="wiki-index-compact">
              <article><span>최근 인덱싱 작업</span><strong>성공 {indexedCount} · 실패 0 · 대기 0</strong><small>마지막 성공 07. 03. 오전 09:20</small></article>
            </div>
          ) : (
            <div className="rag-upload-list">
              {uploadItems.map((item) => (
                <article key={item.id}>
                  <FileText />
                  <div>
                    <strong>{item.name}</strong>
                    <span>{item.type} · {item.size} · {item.collection} · chunk {item.chunks}{item.detail ? ` · ${item.detail}` : ''}</span>
                  </div>
                  <StatusBadge label={item.status} severity={uploadStatusSeverity(item.status)} />
                </article>
              ))}
            </div>
          )}
        </section>
      </div>
    </aside>
  </div>
);

const WikiDocDetailDrawer: React.FC<{
  activeDoc: KnowledgeDoc;
  onClose: () => void;
  open: boolean;
  searchError: string;
  searchResults: Array<{ doc: KnowledgeDoc; score: string; reason: string }>;
  searchStatus: string;
  setTestQuery: (value: string) => void;
  testQuery: string;
}> = ({ activeDoc, onClose, open, searchError, searchResults, searchStatus, setTestQuery, testQuery }) => (
  <div className={`portal-drawer wiki-drawer wiki-doc-detail-drawer ${open ? 'is-open' : ''}`} onClick={onClose}>
    <aside className="portal-drawer__panel" onClick={(event) => event.stopPropagation()}>
      <div className="portal-drawer__head">
        <div>
          <span>문서 상세</span>
          <strong>{activeDoc.title}</strong>
        </div>
        <button aria-label="닫기" className="portal-icon-btn" onClick={onClose} title="닫기" type="button">
          <X />
        </button>
      </div>
      <div className="portal-drawer__body">
        <article className="doc-preview">
          <div className="doc-preview__top">
            <StatusBadge label={activeDoc.status} severity={docStatusSeverity(activeDoc.status)} />
            <span>{activeDoc.category}</span>
          </div>
          <h2>{activeDoc.title}</h2>
          <p>{activeDoc.summary}</p>
          <div className="doc-readiness-grid">
            <article><span>검색 준비 상태</span><strong>{activeDoc.searchStatus}</strong></article>
            <article><span>RCA 연결</span><strong>{activeDoc.rcaLinks}건</strong></article>
            <article><span>마지막 검증일</span><strong>{activeDoc.verifiedAt}</strong></article>
            <article><span>문서 버전</span><strong>{activeDoc.version}</strong></article>
          </div>
          <div className="doc-section">
            <strong>적용 대상</strong>
            <div className="doc-tags">
              {activeDoc.targetScopes.map((tag) => <b key={tag}>{tag}</b>)}
            </div>
          </div>
          <div className="doc-section">
            <strong>연결 이슈</strong>
            <ul className="doc-linked-issues">
              {activeDoc.linkedIssues.map((issue) => <li key={issue}>{issue}</li>)}
            </ul>
          </div>
          <div className="doc-section">
            <strong>검색 키워드</strong>
            <div className="doc-tags is-muted">
              {activeDoc.keywords.map((tag) => <b key={tag}>{tag}</b>)}
            </div>
          </div>
          <ol className="checkpoint-list">
            {activeDoc.steps.map((step, index) => (
              <li key={step}><span>{String(index + 1).padStart(2, '0')}</span><p>{step}</p></li>
            ))}
          </ol>
          <footer>소유자 {activeDoc.owner} · 업데이트 {activeDoc.updatedAt}</footer>
        </article>
        <section className="wiki-drawer-section">
          <strong>검색 테스트</strong>
          <div className="wiki-search-test">
            <label className="portal-search">
              <Search />
              <input onChange={(event) => setTestQuery(event.target.value)} value={testQuery} />
            </label>
            <small>{searchStatus}{searchError ? ` · ${searchError}` : ''}</small>
            <div className="wiki-search-results">
              {searchResults.map((result, index) => (
                <article key={result.doc.id}>
                  <strong>{index + 1}. {result.doc.title}</strong>
                  <span>점수 {result.score} · chunk {Math.min(result.doc.chunks, index + 3)} · {result.reason}</span>
                </article>
              ))}
            </div>
          </div>
        </section>
      </div>
    </aside>
  </div>
);

const WikiIndexDetailDrawer: React.FC<{
  backendReason: string;
  backendStatus: string;
  indexedCount: number;
  lastIndexedAt: string;
  onClose: () => void;
  open: boolean;
  pendingUploadCount: number;
  ragChunkSize: string;
  ragCollection: string;
  totalChunks: number;
  usingSampleDocs: boolean;
}> = ({
  backendReason,
  backendStatus,
  indexedCount,
  lastIndexedAt,
  onClose,
  open,
  pendingUploadCount,
  ragChunkSize,
  ragCollection,
  totalChunks,
  usingSampleDocs,
}) => (
  <div className={`portal-drawer wiki-drawer ${open ? 'is-open' : ''}`} onClick={onClose}>
    <aside className="portal-drawer__panel" onClick={(event) => event.stopPropagation()}>
      <div className="portal-drawer__head">
        <div>
          <span>인덱싱 세부 상태</span>
          <strong>{ragCollection}</strong>
        </div>
        <button aria-label="닫기" className="portal-icon-btn" onClick={onClose} title="닫기" type="button">
          <X />
        </button>
      </div>
      <div className="portal-drawer__body">
        <div className="wiki-index-compact">
          <article><span>컬렉션</span><strong>{ragCollection}</strong><small>Gateway RAG 컬렉션</small></article>
          <article><span>문서</span><strong>{indexedCount}개 {usingSampleDocs ? '샘플 표시' : '색인'}</strong><small>{pendingUploadCount}개 대기</small></article>
          <article><span>청크</span><strong>{totalChunks}개</strong><small>{ragChunkSize} token 기준</small></article>
          <article><span>검색 상태</span><strong>{backendStatus}</strong><small>{backendReason || `마지막 확인 ${lastIndexedAt}`}</small></article>
        </div>
        <section className="wiki-drawer-section">
          <strong>파이프라인</strong>
          <div className="rag-pipeline">
            {['업로드', '텍스트 추출', '청크 분리', '임베딩', '벡터 색인'].map((step, index) => (
              <article key={step}>
                <span>{String(index + 1).padStart(2, '0')}</span>
                <strong>{step}</strong>
              </article>
            ))}
          </div>
        </section>
      </div>
    </aside>
  </div>
);

export const WikiDocsView: React.FC = () => {
  const [activeDocId, setActiveDocId] = React.useState(sampleKnowledgeDocs[0].id);
  const [query, setQuery] = React.useState('');
  const [category, setCategory] = React.useState('전체');
  const [ragCollection, setRagCollection] = React.useState('komsco-aiops-runbooks');
  const [ragChunkSize, setRagChunkSize] = React.useState('900');
  const [dragActive, setDragActive] = React.useState(false);
  const [uploadItems, setUploadItems] = React.useState<WikiUploadItem[]>([]);
  const [showAdvancedSettings, setShowAdvancedSettings] = React.useState(false);
  const [openDrawer, setOpenDrawer] = React.useState<'upload' | 'doc' | 'index' | null>(null);
  const [testQuery, setTestQuery] = React.useState('CrashLoopBackOff가 발생한 Pod를 어떻게 확인해?');
  const [ragUploads, setRagUploads] = React.useState<RagUploadedDocumentList | null>(null);
  const [ragLoadError, setRagLoadError] = React.useState('');
  const [ragSearchRows, setRagSearchRows] = React.useState<Array<{ doc: KnowledgeDoc; score: string; reason: string }>>([]);
  const [ragSearchStatus, setRagSearchStatus] = React.useState('');
  const [ragSearchError, setRagSearchError] = React.useState('');
  const [refreshTick, setRefreshTick] = React.useState(0);
  const liveDocs = React.useMemo(
    () => ragListDocuments(ragUploads).map(ragUploadedDocumentToKnowledgeDoc),
    [ragUploads],
  );
  const usingSampleDocs = liveDocs.length === 0;
  const knowledgeDocs = usingSampleDocs ? sampleKnowledgeDocs : liveDocs;
  const backendCollection = ragUploads?.spec.backend?.collection;
  const backendStatus = ragUploads?.spec.status ?? (ragLoadError ? 'unavailable' : 'loading');
  const backendReason = ragLoadError || ragUploads?.spec.reason || '';
  const lastIndexedAt = ragDateLabel(ragUploads?.metadata?.generatedAt);
  const categories = React.useMemo(
    () => ['전체', ...Array.from(new Set(knowledgeDocs.map((doc) => doc.category))), '검증 필요'],
    [knowledgeDocs],
  );
  const docs = React.useMemo(
    () => knowledgeDocs.filter((doc) => {
      const matchesCategory = category === '전체' || doc.category === category || (category === '검증 필요' && doc.status === '검증 필요');
      const text = `${doc.title} ${doc.summary} ${doc.tags.join(' ')} ${doc.keywords.join(' ')}`.toLowerCase();
      return matchesCategory && (!query.trim() || text.includes(query.trim().toLowerCase()));
    }),
    [category, knowledgeDocs, query],
  );
  const activeDoc = docs.find((doc) => doc.id === activeDocId) ?? docs[0] ?? knowledgeDocs[0] ?? sampleKnowledgeDocs[0];

  React.useEffect(() => {
    let cancelled = false;
    fetchRagUploadedDocuments()
      .then((payload) => {
        if (cancelled) {
          return;
        }
        setRagUploads(payload);
        setRagLoadError('');
        const collection = payload.spec.backend?.collection;
        if (typeof collection === 'string' && collection) {
          setRagCollection(collection);
        }
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }
        setRagLoadError(error instanceof Error ? error.message : String(error));
      });
    return () => {
      cancelled = true;
    };
  }, [refreshTick]);

  React.useEffect(() => {
    setActiveDocId((current) => (docs.some((doc) => doc.id === current) ? current : docs[0]?.id ?? knowledgeDocs[0]?.id ?? sampleKnowledgeDocs[0].id));
  }, [docs, knowledgeDocs]);

  React.useEffect(() => {
    const normalized = testQuery.trim();
    if (!normalized) {
      setRagSearchRows([]);
      setRagSearchStatus('');
      setRagSearchError('');
      return undefined;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      searchRagDocuments(normalized)
        .then((payload) => {
          if (cancelled) {
            return;
          }
          const rows = (payload.spec.results ?? []).slice(0, 3).map((result, index) => ({
            doc: ragSearchResultToKnowledgeDoc(result, index),
            reason: payload.spec.status === 'collected' ? 'Gateway RAG 검색 결과' : payload.spec.reason ?? 'Gateway RAG 검색',
            score: typeof result.score === 'number' ? result.score.toFixed(2) : '-',
          }));
          setRagSearchRows(rows);
          setRagSearchStatus(payload.spec.status ?? '');
          setRagSearchError('');
        })
        .catch((error: unknown) => {
          if (cancelled) {
            return;
          }
          setRagSearchRows([]);
          setRagSearchStatus('unavailable');
          setRagSearchError(error instanceof Error ? error.message : String(error));
        });
    }, 350);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [testQuery]);

  const handleUploadFiles = React.useCallback((fileList: FileList | null) => {
    if (!fileList?.length) {
      return;
    }
    const files = Array.from(fileList);
    const nextItems = files.map((file, index): WikiUploadItem => {
      const extension = file.name.includes('.') ? file.name.split('.').pop()?.toUpperCase() ?? 'FILE' : 'FILE';
      return {
        chunks: Math.max(1, Math.ceil(file.size / Math.max(1, Number(ragChunkSize) * 120))),
        collection: ragCollection,
        id: `${file.name}-${file.lastModified}-${index}`,
        name: file.name,
        size: formatUploadSize(file.size),
        status: '업로드 중',
        type: extension,
        updatedAt: '방금 선택',
      };
    });
    setUploadItems((current) => [...nextItems, ...current]);
    files.forEach((file, index) => {
      const itemId = `${file.name}-${file.lastModified}-${index}`;
      void uploadRagDocumentFile(file)
        .then((result) => {
          const chunkCount = result.spec.chunks?.length ?? result.spec.document.chunkCount ?? 0;
          setUploadItems((current) => current.map((item) => (
            item.id === itemId
              ? {
                  ...item,
                  chunks: Math.max(1, Number(chunkCount || item.chunks)),
                  detail: result.spec.reason,
                  status: result.spec.status === 'persisted' ? '색인됨' : '검증 필요',
                  updatedAt: 'Gateway 응답 완료',
                }
              : item
          )));
          setRefreshTick((value) => value + 1);
        })
        .catch((error: unknown) => {
          setUploadItems((current) => current.map((item) => (
            item.id === itemId
              ? {
                  ...item,
                  detail: error instanceof Error ? error.message : String(error),
                  status: '실패',
                  updatedAt: 'Gateway 오류',
                }
              : item
          )));
        });
    });
  }, [ragChunkSize, ragCollection]);

  const indexedCount = knowledgeDocs.length;
  const verifiedCount = knowledgeDocs.filter((doc) => doc.status === '검증됨').length;
  const reviewCount = knowledgeDocs.filter((doc) => doc.status === '검증 필요').length;
  const pendingUploadCount = uploadItems.length;
  const totalChunks = knowledgeDocs.reduce((total, doc) => total + doc.chunks, 0);
  const localSearchResults = buildDocSearchResults(knowledgeDocs, testQuery, activeDoc);
  const searchResults = ragSearchRows.length > 0 ? ragSearchRows : localSearchResults;
  const searchStatusLabel = ragSearchStatus || (usingSampleDocs ? 'sample-fallback' : 'local-filter');

  return (
    <section className="wiki-workbench stack-view">
      <section className="wiki-knowledge-hero">
        <div>
          <span>운영 지식베이스</span>
          <h2>RCA와 AI 추천 액션에서 참조되는 Runbook 문서를 관리합니다.</h2>
          <p>{backendCollection ?? ragCollection} · {usingSampleDocs ? 'Gateway 문서 없음, 샘플 표시' : `Gateway 색인 ${indexedCount}`} · 대기 {pendingUploadCount} · 상태 {backendStatus} · 마지막 확인 {lastIndexedAt}</p>
          {(backendReason || ragSearchError) && <small className="wiki-knowledge-hero__status">{backendReason || ragSearchError}</small>}
        </div>
        <div className="wiki-hero-actions">
          <button className="portal-button is-primary" onClick={() => setOpenDrawer('upload')} type="button">
            문서 추가
          </button>
          <button className="portal-button" onClick={() => setOpenDrawer('index')} type="button">
            인덱싱 세부 상태
          </button>
          <button className="portal-button" onClick={() => setRefreshTick((value) => value + 1)} type="button">목록 새로고침</button>
        </div>
        <div className="wiki-health-strip">
          <article><span>운영 문서</span><strong>{indexedCount}</strong></article>
          <article><span>검증 완료</span><strong>{verifiedCount}</strong></article>
          <article><span>검증 필요</span><strong>{reviewCount}</strong></article>
          <article><span>검색 chunk</span><strong>{totalChunks}</strong></article>
        </div>
      </section>

      <section className="wiki-layout wiki-layout--library">
        <Panel
          title="문서 라이브러리"
          action={
            <label className="portal-search">
              <Search />
              <input onChange={(event) => setQuery(event.target.value)} placeholder="문서, 대상, 키워드 검색" value={query} />
            </label>
          }
        >
          <div className="portal-tabs wiki-tabs">
            {categories.map((item) => (
              <button className={category === item ? 'is-active' : ''} key={item} onClick={() => setCategory(item)} type="button">
                {item}
              </button>
            ))}
          </div>
          <div className="doc-list">
            {docs.map((doc) => (
              <button
                className={doc.id === activeDoc.id ? 'is-selected' : ''}
                key={doc.id}
                onClick={() => {
                  setActiveDocId(doc.id);
                  setOpenDrawer('doc');
                }}
                type="button"
              >
                <div className="doc-list__head">
                  <strong>{doc.title}</strong>
                  <StatusBadge label={docStatusLabel(doc)} severity={doc.dataSource === 'sample' ? 'warn' : docStatusSeverity(doc.status)} />
                </div>
                <span>{doc.category} · {doc.targetScopes.slice(0, 3).join(' · ')}</span>
                <small>{doc.dataSource === 'gateway' ? 'Gateway RAG' : '샘플'} · {doc.searchStatus} · {doc.chunks} 청크 · RCA 연결 {doc.rcaLinks}건 · 검증 {doc.verifiedAt}</small>
              </button>
            ))}
            {docs.length === 0 && <EmptyState label="조건에 맞는 문서가 없습니다." />}
          </div>
        </Panel>
      </section>

      <WikiUploadDrawer
        dragActive={dragActive}
        handleUploadFiles={handleUploadFiles}
        indexedCount={indexedCount}
        onClose={() => setOpenDrawer(null)}
        open={openDrawer === 'upload'}
        ragChunkSize={ragChunkSize}
        ragCollection={ragCollection}
        setDragActive={setDragActive}
        setRagChunkSize={setRagChunkSize}
        setRagCollection={setRagCollection}
        setShowAdvancedSettings={setShowAdvancedSettings}
        showAdvancedSettings={showAdvancedSettings}
        uploadItems={uploadItems}
      />
      <WikiDocDetailDrawer
        activeDoc={activeDoc}
        onClose={() => setOpenDrawer(null)}
        open={openDrawer === 'doc'}
        searchError={ragSearchError}
        searchResults={searchResults}
        searchStatus={searchStatusLabel}
        setTestQuery={setTestQuery}
        testQuery={testQuery}
      />
      <WikiIndexDetailDrawer
        backendReason={backendReason}
        backendStatus={backendStatus}
        indexedCount={indexedCount}
        lastIndexedAt={lastIndexedAt}
        onClose={() => setOpenDrawer(null)}
        open={openDrawer === 'index'}
        pendingUploadCount={pendingUploadCount}
        ragChunkSize={ragChunkSize}
        ragCollection={ragCollection}
        totalChunks={totalChunks}
        usingSampleDocs={usingSampleDocs}
      />
    </section>
  );
};
