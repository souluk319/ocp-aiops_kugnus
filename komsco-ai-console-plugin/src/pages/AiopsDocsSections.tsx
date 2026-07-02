import * as React from 'react';
import { Button } from '@patternfly/react-core';
import {
  ClipboardCheckIcon,
  LockIcon,
  ProjectDiagramIcon,
  ServerIcon,
  ShieldAltIcon,
} from '@patternfly/react-icons';

import type {
  AiopsRuntimeStatus,
  RagSearchResultItem,
  RagUploadedDocument,
} from '../services/aiGateway';
import { safeEvidenceText } from '../utils/evidenceDisplay';

type Tone = 'danger' | 'info' | 'success' | 'warning';
type RagBackendStatus = NonNullable<AiopsRuntimeStatus['spec']['capabilities']['rag']>;

export const DOCS_UPLOAD_ACCEPT = [
  '.pdf',
  '.docx',
  '.pptx',
  '.xlsx',
  '.txt',
  '.md',
  '.markdown',
  '.json',
  '.yaml',
  '.yml',
  '.log',
].join(',');

export const formatBytes = (value?: number): string => {
  const size = typeof value === 'number' && Number.isFinite(value) ? value : 0;
  if (size < 1024) {
    return `${size} B`;
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
};

export const uploadedDocumentQuery = (document: RagUploadedDocument): string =>
  [document.title, document.sourceUri, document.documentId].filter(Boolean).join(' ');

const ragBackendTone = (status?: string): Tone => {
  if (status === 'configured') {
    return 'success';
  }
  if (status === 'unavailable') {
    return 'danger';
  }
  return 'warning';
};

const probeStatusLabel = (status?: string): string => {
  if (status === 'succeeded' || status === 'available') {
    return '정상';
  }
  if (status === 'failed' || status === 'error') {
    return '확인 필요';
  }
  if (status === 'partial') {
    return '일부 제한';
  }
  if (status === 'probe pending' || status === 'checking') {
    return '확인 중';
  }
  return status || '확인 중';
};

const compactDigest = (value?: string): string => {
  if (!value) {
    return '';
  }

  return value.length > 28 ? `${value.slice(0, 24)}...` : value;
};

const formatTime = (value?: string): string => {
  if (!value) {
    return '-';
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString('ko-KR', {
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    month: '2-digit',
  });
};

const EmptyState: React.FC<{ label: string }> = ({ label }) => (
  <div className="komsco-ai-page__empty">{label}</div>
);

const MetricTile: React.FC<{
  detail?: string;
  icon: React.ReactNode;
  label: string;
  tone: Tone;
  value: string | number;
}> = ({ detail, icon, label, tone, value }) => (
  <div className={`komsco-ai-page__metric komsco-ai-page__metric--${tone}`}>
    <span className="komsco-ai-page__metric-icon">{icon}</span>
    <span className="komsco-ai-page__metric-label">{label}</span>
    <strong>{value}</strong>
    {detail && <span className="komsco-ai-page__metric-detail">{detail}</span>}
  </div>
);

export const DocsHero: React.FC<{
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  loading: boolean;
  onRefresh: () => void;
  onUploadChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
  uploading: boolean;
}> = ({ fileInputRef, loading, onRefresh, onUploadChange, uploading }) => (
  <section className="komsco-ai-page__docs-hero">
    <div>
      <span className="komsco-ai-page__section-kicker">고객 문서</span>
      <h2>고객 문서 저장소</h2>
      <p>고객 문서를 등록하고 검색 가능한 근거 조각과 권한 범위를 확인합니다.</p>
    </div>
    <div className="komsco-ai-page__docs-actions">
      <input
        accept={DOCS_UPLOAD_ACCEPT}
        className="komsco-ai-page__docs-file-input"
        multiple
        onChange={onUploadChange}
        ref={fileInputRef as React.LegacyRef<HTMLInputElement>}
        type="file"
      />
      <Button
        isDisabled={uploading}
        onClick={() => fileInputRef.current?.click()}
        variant="primary"
      >
        {uploading ? '업로드 중' : '문서 업로드'}
      </Button>
      <Button isDisabled={loading} onClick={onRefresh} variant="secondary">
        목록 새로고침
      </Button>
    </div>
  </section>
);

export const DocsMetrics: React.FC<{
  activeRagBackend: RagBackendStatus | null;
  documents: RagUploadedDocument[];
  documentsLoading: boolean;
  ragStatus: string;
  totalBytes: number;
  totalChunks: number;
}> = ({ activeRagBackend, documents, documentsLoading, ragStatus, totalBytes, totalChunks }) => (
  <div className="komsco-ai-page__metrics">
    <MetricTile
      detail={activeRagBackend?.collection || activeRagBackend?.backendType || 'gateway-only'}
      icon={<ServerIcon />}
      label="검색 저장소"
      tone={ragBackendTone(activeRagBackend?.status)}
      value={probeStatusLabel(ragStatus)}
    />
    <MetricTile
      detail="현재 사용자 권한 기준"
      icon={<ClipboardCheckIcon />}
      label="등록 문서"
      tone={documents.length > 0 ? 'success' : 'warning'}
      value={documentsLoading ? '...' : documents.length}
    />
    <MetricTile
      detail="검색 가능한 근거 조각"
      icon={<ProjectDiagramIcon />}
      label="검색 조각"
      tone={totalChunks > 0 ? 'success' : 'warning'}
      value={documentsLoading ? '...' : totalChunks}
    />
    <MetricTile
      detail={activeRagBackend?.accessPath || 'Gateway 권한 확인'}
      icon={<LockIcon />}
      label="권한 제한"
      tone={activeRagBackend?.aclRequired === false ? 'warning' : 'success'}
      value={activeRagBackend?.aclRequired === false ? '꺼짐' : '켜짐'}
    />
    <MetricTile
      detail="요약 미리보기만 표시"
      icon={<ShieldAltIcon />}
      label="원문 보호"
      tone="success"
      value="숨김"
    />
    <MetricTile
      detail="저장된 문서 크기"
      icon={<ServerIcon />}
      label="저장 용량"
      tone={totalBytes > 0 ? 'info' : 'warning'}
      value={formatBytes(totalBytes)}
    />
  </div>
);

export const DocsLayout: React.FC<{
  documents: RagUploadedDocument[];
  documentsLoading: boolean;
  onSelectDocument: (documentId: string) => void;
  previewError: string;
  previewLoading: boolean;
  previewReason: string;
  previewResults: RagSearchResultItem[];
  previewStatus: string;
  selectedDocument: RagUploadedDocument | null;
}> = ({
  documents,
  documentsLoading,
  onSelectDocument,
  previewError,
  previewLoading,
  previewReason,
  previewResults,
  previewStatus,
  selectedDocument,
}) => (
  <section className="komsco-ai-page__docs-layout">
    <div className="komsco-ai-page__panel komsco-ai-page__docs-list-panel">
      <div className="komsco-ai-page__panel-heading">
        <ClipboardCheckIcon />
        <h2>업로드 목록</h2>
      </div>
      {documentsLoading && documents.length === 0 ? (
        <EmptyState label="업로드 문서를 확인하는 중입니다." />
      ) : documents.length === 0 ? (
        <EmptyState label="아직 업로드된 문서가 없습니다." />
      ) : (
        <div className="komsco-ai-page__docs-list">
          {documents.map((document) => (
            <button
              className={`komsco-ai-page__docs-item${
                selectedDocument?.documentId === document.documentId
                  ? ' komsco-ai-page__docs-item--active'
                  : ''
              }`}
              key={document.documentId}
              onClick={() => onSelectDocument(document.documentId)}
              type="button"
            >
              <strong>{document.title}</strong>
              <span>{document.sourceUri || document.documentId}</span>
              <small>
                {document.chunkCount ?? 0} chunks · {formatBytes(document.contentBytes)} ·{' '}
                {formatTime(document.updatedAt || document.ingestedAt)}
              </small>
            </button>
          ))}
        </div>
      )}
    </div>

    <div className="komsco-ai-page__panel komsco-ai-page__docs-viewer">
      <div className="komsco-ai-page__panel-heading">
        <ProjectDiagramIcon />
        <h2>적재 문서 뷰어</h2>
      </div>
      {!selectedDocument ? (
        <EmptyState label="문서를 선택하면 RAG 적재 상태가 표시됩니다." />
      ) : (
        <>
          <div className="komsco-ai-page__docs-detail">
            <div>
              <span>문서명</span>
              <strong>{selectedDocument.title}</strong>
            </div>
            <div>
              <span>문서 ID</span>
              <strong>{selectedDocument.documentId}</strong>
            </div>
            <div>
              <span>형식</span>
              <strong>{selectedDocument.mimeType || selectedDocument.sourceType || '-'}</strong>
            </div>
            <div>
              <span>무결성</span>
              <strong>{compactDigest(selectedDocument.checksum)}</strong>
            </div>
            <div>
              <span>권한</span>
              <strong>
                {(selectedDocument.aclGroups ?? []).slice(0, 3).join(', ') || '현재 사용자 범위'}
              </strong>
            </div>
            <div>
              <span>상태</span>
              <strong>{previewLoading ? '확인 중' : probeStatusLabel(previewStatus)}</strong>
            </div>
          </div>

          <div className="komsco-ai-page__docs-safety">
            원본 전체 파일을 그대로 노출하지 않고, Gateway가 반환한 근거 미리보기만 표시합니다.
          </div>

          {previewLoading ? (
            <EmptyState label="적재 chunk를 확인하는 중입니다." />
          ) : previewError ? (
            <div className="komsco-ai-page__error">{previewError}</div>
          ) : previewResults.length === 0 ? (
            <EmptyState
              label={previewReason || '검색 가능한 적재 chunk가 아직 확인되지 않았습니다.'}
            />
          ) : (
            <div className="komsco-ai-page__docs-preview-list">
              {previewResults.map((result, index) => (
                <article
                  className="komsco-ai-page__docs-preview"
                  key={result.id || `${result.documentId}-${index}`}
                >
                  <div className="komsco-ai-page__docs-preview-head">
                    <strong>{result.title || selectedDocument.title}</strong>
                    <span>
                      유사도 {typeof result.score === 'number' ? result.score.toFixed(3) : '-'}
                    </span>
                  </div>
                  <p>
                    {safeEvidenceText(result.content || result.contentPreview || 'preview 없음')}
                  </p>
                  <small>{result.sourceUri || result.id || result.documentId}</small>
                </article>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  </section>
);
