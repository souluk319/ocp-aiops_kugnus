#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const readFile = (relativePath) => fs.readFileSync(path.join(root, relativePath), 'utf8');

const assert = (condition, message, evidence = undefined) => {
  if (!condition) {
    const detail = evidence === undefined ? '' : `\n${JSON.stringify(evidence, null, 2)}`;
    throw new Error(`${message}${detail}`);
  }
};

const portalApp = readFile('komsco-ai-console-plugin/src/portal/PortalApp.tsx');
const portalApi = readFile('komsco-ai-console-plugin/src/portal/api.ts');
const portalTypes = readFile('komsco-ai-console-plugin/src/portal/types.ts');
const portalCss = readFile('komsco-ai-console-plugin/src/portal/styles.css');
const localFixture = readFile('scripts/serve-v0281-local-aiops-gateway.cjs');

assert(portalTypes.includes('export type RagUploadedDocument'), 'Portal types must model uploaded RAG documents');
assert(portalTypes.includes('export type RagUploadedDocumentList'), 'Portal types must model RAG upload list responses');
assert(portalTypes.includes('export type RagSearchResult'), 'Portal types must model RAG search responses');
assert(portalTypes.includes('export type RagUploadIngestionResult'), 'Portal types must model RAG upload ingestion responses');

assert(portalApi.includes("fetchRagUploadedDocuments"), 'Portal API must fetch /v1/rag/uploads');
assert(portalApi.includes("'/v1/rag/uploads'"), 'Portal API must use the Gateway RAG upload list endpoint');
assert(portalApi.includes("searchRagDocuments"), 'Portal API must call /v1/rag/search');
assert(portalApi.includes('/v1/rag/search'), 'Portal API must use the Gateway RAG search endpoint');
assert(portalApi.includes("uploadRagDocumentFile"), 'Portal API must upload files through Gateway RAG ingestion');
assert(portalApi.includes('/v1/rag/uploads/file'), 'Portal API must use the Gateway multipart RAG upload endpoint');

assert(portalApp.includes('fetchRagUploadedDocuments'), 'WikiDocsView must load live Gateway RAG documents');
assert(portalApp.includes('ragUploadedDocumentToKnowledgeDoc'), 'WikiDocsView must adapt Gateway RAG documents to visible document cards');
assert(portalApp.includes('ragListDocuments(ragUploads)'), 'WikiDocsView must support Gateway document list payloads');
assert(portalApp.includes('usingSampleDocs'), 'WikiDocsView must explicitly track sample fallback state');
assert(portalApp.includes('Gateway 문서 없음, 샘플 표시'), 'Wiki hero must name the sample fallback when Gateway has no documents');
assert(portalApp.includes('searchRagDocuments(normalized)'), 'Wiki search test must call live Gateway RAG search');
assert(portalApp.includes('ragSearchResultToKnowledgeDoc'), 'Wiki search must adapt Gateway search result chunks for display');
assert(portalApp.includes('uploadRagDocumentFile(file)'), 'Wiki upload drawer must send selected files to Gateway RAG ingestion');
assert(portalApp.includes("result.spec.status === 'persisted' ? '색인됨' : '검증 필요'"), 'Wiki upload queue must distinguish persisted uploads from non-persisted validation results');
assert(portalApp.includes("doc.dataSource === 'gateway' ? 'Gateway RAG' : '샘플'"), 'Document cards must disclose Gateway vs sample source');
assert(portalApp.includes('backendStatus') && portalApp.includes('backendReason'), 'Wiki index drawer must expose Gateway backend status and reason');

assert(localFixture.includes("url.pathname === '/v1/rag/uploads'"), 'Local fixture must expose RAG upload list endpoint');
assert(localFixture.includes("url.pathname === '/v1/rag/search'"), 'Local fixture must expose RAG search endpoint');
assert(localFixture.includes("url.pathname === '/v1/rag/uploads/file'"), 'Local fixture must expose RAG file upload endpoint');
assert(localFixture.includes('Local fixture has no pgvector RAG backend'), 'Local fixture must explain not-configured RAG fallback');
assert(localFixture.includes('mockResultsAreProductionEvidence: false'), 'Local fixture RAG search must not masquerade as production evidence');

assert(portalCss.includes('.wiki-knowledge-hero .wiki-knowledge-hero__status'), 'Wiki hero status line must have overflow-safe CSS');
assert(portalCss.includes('.wiki-search-test > small'), 'Wiki search status line must have overflow-safe CSS');

console.log('PASS verify-v029-rag-wiki-live');
