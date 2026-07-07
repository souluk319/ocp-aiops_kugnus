import React from 'react';
import { FileText, RefreshCw, Upload } from 'lucide-react';
import {
  Button,
  Card,
  Drawer,
  Empty,
  SearchInput,
  Select,
  SevBadge,
  Tabs,
} from '../components/primitives';
import {
  buildDocSearchResults,
  docStatusSeverity,
  formatUploadSize,
  sampleKnowledgeDocs,
  uploadStatusSeverity,
  type KnowledgeDoc,
  type WikiUploadItem,
} from '../lib/model';

export const V2Wiki: React.FC = () => {
  const [activeDocId, setActiveDocId] = React.useState(sampleKnowledgeDocs[0].id);
  const [query, setQuery] = React.useState('');
  const [category, setCategory] = React.useState('전체');
  const [ragCollection, setRagCollection] = React.useState('ocp-runbooks');
  const [ragChunkSize, setRagChunkSize] = React.useState('900');
  const [dragActive, setDragActive] = React.useState(false);
  const [uploadItems, setUploadItems] = React.useState<WikiUploadItem[]>([]);
  const [showAdvancedSettings, setShowAdvancedSettings] = React.useState(false);
  const [openDrawer, setOpenDrawer] = React.useState<'upload' | 'doc' | 'index' | null>(null);
  const [testQuery, setTestQuery] = React.useState('CrashLoopBackOff가 발생한 Pod를 어떻게 확인해?');
  const [reindexNote, setReindexNote] = React.useState('');
  const categories = ['전체', ...Array.from(new Set(sampleKnowledgeDocs.map((doc) => doc.category))), '검증 필요'];
  const docs = sampleKnowledgeDocs.filter((doc) => {
    const matchesCategory =
      category === '전체' || doc.category === category || (category === '검증 필요' && doc.status === '검증 필요');
    const text = `${doc.title} ${doc.summary} ${doc.tags.join(' ')} ${doc.keywords.join(' ')}`.toLowerCase();
    return matchesCategory && (!query.trim() || text.includes(query.trim().toLowerCase()));
  });
  const activeDoc: KnowledgeDoc = docs.find((doc) => doc.id === activeDocId) ?? docs[0] ?? sampleKnowledgeDocs[0];

  React.useEffect(() => {
    setActiveDocId((current) =>
      docs.some((doc) => doc.id === current) ? current : (docs[0]?.id ?? sampleKnowledgeDocs[0].id),
    );
  }, [docs]);

  const handleUploadFiles = React.useCallback(
    (fileList: FileList | null) => {
      if (!fileList?.length) {
        return;
      }
      const nextItems = Array.from(fileList).map((file, index): WikiUploadItem => {
        const extension = file.name.includes('.') ? (file.name.split('.').pop()?.toUpperCase() ?? 'FILE') : 'FILE';
        return {
          chunks: Math.max(1, Math.ceil(file.size / Math.max(1, Number(ragChunkSize) * 120))),
          collection: ragCollection,
          id: `${file.name}-${file.lastModified}-${index}`,
          name: file.name,
          size: formatUploadSize(file.size),
          status: '인덱싱 준비',
          type: extension,
          updatedAt: '방금 선택',
        };
      });
      setUploadItems((current) => [...nextItems, ...current]);
    },
    [ragChunkSize, ragCollection],
  );

  const indexedCount = sampleKnowledgeDocs.length;
  const verifiedCount = sampleKnowledgeDocs.filter((doc) => doc.status === '검증됨').length;
  const reviewCount = sampleKnowledgeDocs.filter((doc) => doc.status === '검증 필요').length;
  const pendingUploadCount = uploadItems.length;
  const totalChunks = sampleKnowledgeDocs.reduce((total, doc) => total + doc.chunks, 0);
  const searchResults = buildDocSearchResults(sampleKnowledgeDocs, testQuery, activeDoc);

  return (
    <div className="v2-view v2-wiki">
      <section className="v2-wiki-hero">
        <div className="v2-wiki-hero__text">
          <span className="v2-wiki-hero__eyebrow">운영 지식베이스</span>
          <h2>RCA와 AI 추천 액션에서 참조되는 Runbook 문서를 관리합니다.</h2>
          <p>
            {ragCollection} · 색인 {indexedCount} · 대기 {pendingUploadCount} · 이슈 0 · 마지막 색인 07. 03. 오전 09:20
            {reindexNote && <em className="v2-wiki-hero__note"> · {reindexNote}</em>}
          </p>
        </div>
        <div className="v2-wiki-hero__actions">
          <Button icon={<Upload size={13} />} onClick={() => setOpenDrawer('upload')} variant="primary">
            문서 추가
          </Button>
          <Button onClick={() => setOpenDrawer('index')}>인덱싱 세부 상태</Button>
          <Button icon={<RefreshCw size={13} />} onClick={() => setReindexNote('색인 재실행을 요청했습니다.')}>
            색인 재실행
          </Button>
        </div>
        <div className="v2-wiki-health">
          <article>
            <span>운영 문서</span>
            <strong>{indexedCount}</strong>
          </article>
          <article>
            <span>검증 완료</span>
            <strong>{verifiedCount}</strong>
          </article>
          <article>
            <span>검증 필요</span>
            <strong>{reviewCount}</strong>
          </article>
          <article>
            <span>검색 chunk</span>
            <strong>{totalChunks}</strong>
          </article>
        </div>
      </section>

      <Card
        actions={<SearchInput onChange={setQuery} placeholder="문서, 대상, 키워드 검색" value={query} />}
        className="v2-wiki-library"
        title="문서 라이브러리"
      >
        <Tabs active={category} items={categories.map((item) => ({ id: item, label: item }))} onChange={setCategory} />
        <div className="v2-doc-list">
          {docs.map((doc) => (
            <button
              className={`v2-doc${doc.id === activeDoc.id ? ' is-selected' : ''}`}
              key={doc.id}
              onClick={() => {
                setActiveDocId(doc.id);
                setOpenDrawer('doc');
              }}
              type="button"
            >
              <div className="v2-doc__head">
                <strong>{doc.title}</strong>
                <SevBadge label={doc.status} severity={docStatusSeverity(doc.status)} />
              </div>
              <span>
                {doc.category} · {doc.targetScopes.slice(0, 3).join(' · ')}
              </span>
              <small>
                {doc.searchStatus} · {doc.chunks} 청크 · RCA 연결 {doc.rcaLinks}건 · 검증 {doc.verifiedAt}
              </small>
            </button>
          ))}
          {docs.length === 0 && <Empty label="조건에 맞는 문서가 없습니다." />}
        </div>
      </Card>

      {/* 업로드 드로어 */}
      <Drawer
        onClose={() => setOpenDrawer(null)}
        open={openDrawer === 'upload'}
        sub="Runbook 문서 업로드"
        title="문서 추가"
      >
        <div
          className={`v2-dropzone${dragActive ? ' is-active' : ''}`}
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
          <Upload size={22} />
          <div>
            <strong>운영 지식으로 색인할 문서 선택</strong>
            <p>PDF, DOCX, MD, TXT, YAML, 로그 파일을 업로드할 수 있습니다.</p>
          </div>
          <label className="v2-button is-outline is-md" htmlFor="v2-wiki-upload-input">
            파일 선택
          </label>
          <input
            accept=".pdf,.doc,.docx,.md,.txt,.yaml,.yml,.json,.log"
            hidden
            id="v2-wiki-upload-input"
            multiple
            onChange={(event) => {
              handleUploadFiles(event.target.files);
              event.target.value = '';
            }}
            type="file"
          />
        </div>
        <button className="v2-link-toggle" onClick={() => setShowAdvancedSettings((value) => !value)} type="button">
          고급 설정 {showAdvancedSettings ? '접기' : '보기'}
        </button>
        {showAdvancedSettings && (
          <div className="v2-rag-settings">
            <label>
              <span>컬렉션</span>
              <Select
                onChange={setRagCollection}
                options={[
                  { label: 'ocp-runbooks', value: 'ocp-runbooks' },
                  { label: 'incident-rca', value: 'incident-rca' },
                  { label: 'platform-policy', value: 'platform-policy' },
                ]}
                value={ragCollection}
              />
            </label>
            <label>
              <span>Chunk 크기</span>
              <Select
                onChange={setRagChunkSize}
                options={[
                  { label: '600 tokens', value: '600' },
                  { label: '900 tokens', value: '900' },
                  { label: '1200 tokens', value: '1200' },
                ]}
                value={ragChunkSize}
              />
            </label>
            <label>
              <span>검색 범위</span>
              <Select
                onChange={() => undefined}
                options={[
                  { label: '운영팀 공개', value: 'ops' },
                  { label: '업로드 사용자만', value: 'private' },
                  { label: '전체 포털', value: 'all' },
                ]}
                value="ops"
              />
            </label>
          </div>
        )}
        <section className="v2-drawer-section">
          <h3>업로드 대기열</h3>
          {uploadItems.length === 0 ? (
            <div className="v2-index-compact">
              <article>
                <span>최근 인덱싱 작업</span>
                <strong>성공 {indexedCount} · 실패 0 · 대기 0</strong>
                <small>마지막 성공 07. 03. 오전 09:20</small>
              </article>
            </div>
          ) : (
            <div className="v2-upload-list">
              {uploadItems.map((item) => (
                <article key={item.id}>
                  <FileText size={16} />
                  <div>
                    <strong>{item.name}</strong>
                    <span>
                      {item.type} · {item.size} · {item.collection} · 예상 chunk {item.chunks}
                    </span>
                  </div>
                  <SevBadge label={item.status} severity={uploadStatusSeverity(item.status)} />
                </article>
              ))}
            </div>
          )}
        </section>
      </Drawer>

      {/* 문서 상세 드로어 */}
      <Drawer onClose={() => setOpenDrawer(null)} open={openDrawer === 'doc'} sub="문서 상세" title={activeDoc.title} wide>
        <article className="v2-doc-preview">
          <div className="v2-doc-preview__top">
            <SevBadge label={activeDoc.status} severity={docStatusSeverity(activeDoc.status)} />
            <span>{activeDoc.category}</span>
          </div>
          <p className="v2-doc-preview__summary">{activeDoc.summary}</p>
          <div className="v2-doc-readiness">
            <article>
              <span>검색 준비 상태</span>
              <strong>{activeDoc.searchStatus}</strong>
            </article>
            <article>
              <span>RCA 연결</span>
              <strong>{activeDoc.rcaLinks}건</strong>
            </article>
            <article>
              <span>마지막 검증일</span>
              <strong>{activeDoc.verifiedAt}</strong>
            </article>
            <article>
              <span>문서 버전</span>
              <strong>{activeDoc.version}</strong>
            </article>
          </div>
          <div className="v2-doc-section">
            <h3>적용 대상</h3>
            <div className="v2-doc-tags">
              {activeDoc.targetScopes.map((tag) => (
                <b key={tag}>{tag}</b>
              ))}
            </div>
          </div>
          <div className="v2-doc-section">
            <h3>연결 이슈</h3>
            <ul className="v2-doc-issues">
              {activeDoc.linkedIssues.map((issue) => (
                <li key={issue}>{issue}</li>
              ))}
            </ul>
          </div>
          <div className="v2-doc-section">
            <h3>검색 키워드</h3>
            <div className="v2-doc-tags is-muted">
              {activeDoc.keywords.map((tag) => (
                <b key={tag}>{tag}</b>
              ))}
            </div>
          </div>
          <ol className="v2-doc-steps">
            {activeDoc.steps.map((step, index) => (
              <li key={step}>
                <span>{String(index + 1).padStart(2, '0')}</span>
                <p>{step}</p>
              </li>
            ))}
          </ol>
          <footer className="v2-doc-preview__footer">
            소유자 {activeDoc.owner} · 업데이트 {activeDoc.updatedAt}
          </footer>
        </article>
        <section className="v2-drawer-section">
          <h3>검색 테스트 (RAG)</h3>
          <div className="v2-search-test">
            <SearchInput onChange={setTestQuery} placeholder="테스트 질의 입력" value={testQuery} />
            <div className="v2-search-results">
              {searchResults.map((result, index) => (
                <article key={result.doc.id}>
                  <strong>
                    {index + 1}. {result.doc.title}
                  </strong>
                  <span>
                    점수 {result.score} · chunk {Math.min(result.doc.chunks, index + 3)} · {result.reason}
                  </span>
                </article>
              ))}
            </div>
          </div>
        </section>
      </Drawer>

      {/* 인덱싱 상태 드로어 */}
      <Drawer onClose={() => setOpenDrawer(null)} open={openDrawer === 'index'} sub="인덱싱 세부 상태" title={ragCollection}>
        <div className="v2-index-compact">
          <article>
            <span>컬렉션</span>
            <strong>{ragCollection}</strong>
            <small>운영 Runbook 기본 컬렉션</small>
          </article>
          <article>
            <span>문서</span>
            <strong>{indexedCount}개 색인</strong>
            <small>{pendingUploadCount}개 대기</small>
          </article>
          <article>
            <span>청크</span>
            <strong>{totalChunks}개</strong>
            <small>{ragChunkSize} token 기준</small>
          </article>
          <article>
            <span>검색 상태</span>
            <strong>검색 가능</strong>
            <small>오류 0 · 마지막 색인 07. 03. 오전 09:20</small>
          </article>
        </div>
        <section className="v2-drawer-section">
          <h3>파이프라인</h3>
          <div className="v2-rag-pipeline">
            {['업로드', '텍스트 추출', '청크 분리', '임베딩', '벡터 색인'].map((step, index) => (
              <article key={step}>
                <span>{String(index + 1).padStart(2, '0')}</span>
                <strong>{step}</strong>
              </article>
            ))}
          </div>
        </section>
      </Drawer>
    </div>
  );
};
