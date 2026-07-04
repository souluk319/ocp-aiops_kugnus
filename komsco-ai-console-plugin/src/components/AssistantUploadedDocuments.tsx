import * as React from 'react';

import type { RagUploadedDocument } from '../services/aiGateway';
import { formatFileSize } from './assistant.attachments';

type AssistantUploadedDocumentsProps = {
  documents: RagUploadedDocument[];
  emptyText: string;
};

const AssistantUploadedDocuments: React.FC<AssistantUploadedDocumentsProps> = ({
  documents,
  emptyText,
}) => {
  if (documents.length === 0) {
    return <div className="komsco-ai__history-empty">{emptyText}</div>;
  }

  return (
    <>
      {documents.map((document) => (
        <div
          className="komsco-ai__uploaded-doc-item"
          key={document.documentId}
          title={document.sourceUri || document.title}
        >
          <div className="komsco-ai__uploaded-doc-title">{document.title}</div>
          <div className="komsco-ai__uploaded-doc-meta">
            <span>{document.chunkCount ?? 0} chunks</span>
            <span>{formatFileSize(document.contentBytes ?? 0)}</span>
          </div>
          <div className="komsco-ai__uploaded-doc-source">
            {document.sourceUri || document.documentId}
          </div>
        </div>
      ))}
    </>
  );
};

export default AssistantUploadedDocuments;
