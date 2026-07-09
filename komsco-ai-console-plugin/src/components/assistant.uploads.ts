import * as React from 'react';
import {
  MAX_IMAGE_ATTACHMENT_BYTES,
  MAX_IMAGE_ATTACHMENT_TOTAL_BYTES,
  MAX_IMAGE_ATTACHMENTS,
  MAX_RAG_DOCUMENT_UPLOAD_BYTES,
} from './assistant.constants';
import { formatFileSize } from './assistant.attachments';
import {
  isAcceptedImageFile,
  isRagDocumentFile,
  mergeUploadedDocuments,
  readImageAttachment,
  readRagDocumentContent,
  shouldUploadRagDocumentAsFile,
  uniqueFiles,
} from './assistant.uploadFiles';
import type { HistoryPanelView } from './assistant.types';
import type { ImageAttachment, RagUploadedDocument } from '../services/aiGateway';
import {
  fetchUploadedRagDocuments,
  uploadRagDocument,
  uploadRagDocumentFile,
} from '../services/aiGateway';

type UseAssistantUploadsOptions = {
  readonly activeSessionId: string;
  readonly historyPanelView: HistoryPanelView;
  readonly historySidebarOpen: boolean;
  readonly open: boolean;
  readonly setHistoryPanelView: React.Dispatch<React.SetStateAction<HistoryPanelView>>;
  readonly setHistorySidebarOpen: React.Dispatch<React.SetStateAction<boolean>>;
  readonly uploadedDocsErrorLabel: string;
};

export const useAssistantUploads = ({
  activeSessionId,
  historyPanelView,
  historySidebarOpen,
  open,
  setHistoryPanelView,
  setHistorySidebarOpen,
  uploadedDocsErrorLabel,
}: UseAssistantUploadsOptions) => {
  const [pendingAttachments, setPendingAttachments] = React.useState<ImageAttachment[]>([]);
  const [attachmentError, setAttachmentError] = React.useState('');
  const [uploadedDocuments, setUploadedDocuments] = React.useState<RagUploadedDocument[]>([]);
  const [uploadedDocumentsError, setUploadedDocumentsError] = React.useState('');
  const [uploadedDocumentsLoading, setUploadedDocumentsLoading] = React.useState(false);
  const [dragActive, setDragActive] = React.useState(false);

  React.useEffect(() => {
    if (!open || !historySidebarOpen || historyPanelView !== 'uploads') {
      return undefined;
    }

    let disposed = false;

    const loadUploadedDocuments = async () => {
      setUploadedDocumentsLoading(true);
      try {
        const payload = await fetchUploadedRagDocuments();
        if (disposed) {
          return;
        }
        const uploadStatus = payload.spec.status;
        const serverDocuments = payload.spec.documents ?? [];
        setUploadedDocuments((prev) => mergeUploadedDocuments(serverDocuments, prev));
        setUploadedDocumentsError(
          uploadStatus === 'collected' || uploadStatus === 'empty'
            ? ''
            : (payload.spec.reason ?? uploadedDocsErrorLabel),
        );
      } catch (error) {
        if (!disposed) {
          setUploadedDocumentsError(
            error instanceof Error ? error.message : uploadedDocsErrorLabel,
          );
        }
      } finally {
        if (!disposed) {
          setUploadedDocumentsLoading(false);
        }
      }
    };

    void loadUploadedDocuments();
    return () => {
      disposed = true;
    };
  }, [historyPanelView, historySidebarOpen, open, uploadedDocsErrorLabel]);

  const addImageFiles = React.useCallback(
    async (files: File[]) => {
      const normalizedFiles = uniqueFiles(files);
      const imageFiles = normalizedFiles.filter(isAcceptedImageFile);
      const documentFiles = normalizedFiles.filter(
        (file) => !isAcceptedImageFile(file) && isRagDocumentFile(file),
      );

      if (imageFiles.length === 0 && documentFiles.length === 0) {
        setAttachmentError(
          '지원 형식: PNG/JPEG/WebP/GIF 이미지 또는 PDF/DOCX/PPTX/XLSX/TXT/MD/JSON/YAML/log 문서입니다.',
        );
        return;
      }

      const unsupportedCount = normalizedFiles.length - imageFiles.length - documentFiles.length;
      if (unsupportedCount > 0) {
        setAttachmentError('일부 파일은 지원 형식이 아니라 제외했습니다.');
      }

      if (imageFiles.length > 0) {
        const nextCount = pendingAttachments.length + imageFiles.length;
        if (nextCount > MAX_IMAGE_ATTACHMENTS) {
          setAttachmentError(`이미지는 최대 ${MAX_IMAGE_ATTACHMENTS}개까지 첨부할 수 있습니다.`);
          return;
        }

        const tooLarge = imageFiles.find((file) => file.size > MAX_IMAGE_ATTACHMENT_BYTES);
        if (tooLarge) {
          setAttachmentError(
            `${tooLarge.name} 파일이 너무 큽니다. 이미지당 최대 ${formatFileSize(
              MAX_IMAGE_ATTACHMENT_BYTES,
            )}까지 가능합니다.`,
          );
          return;
        }

        const currentTotal = pendingAttachments.reduce((total, item) => total + item.size, 0);
        const nextTotal = imageFiles.reduce((total, file) => total + file.size, currentTotal);
        if (nextTotal > MAX_IMAGE_ATTACHMENT_TOTAL_BYTES) {
          setAttachmentError(
            `첨부 이미지 합계는 최대 ${formatFileSize(MAX_IMAGE_ATTACHMENT_TOTAL_BYTES)}까지 가능합니다.`,
          );
          return;
        }
      }

      const tooLargeDocument = documentFiles.find(
        (file) => file.size > MAX_RAG_DOCUMENT_UPLOAD_BYTES,
      );
      if (tooLargeDocument) {
        setAttachmentError(
          `${tooLargeDocument.name} 문서가 너무 큽니다. 문서당 최대 ${formatFileSize(
            MAX_RAG_DOCUMENT_UPLOAD_BYTES,
          )}까지 가능합니다.`,
        );
        return;
      }

      try {
        if (imageFiles.length > 0) {
          const attachments = await Promise.all(imageFiles.map(readImageAttachment));
          setPendingAttachments((prev) => [...prev, ...attachments]);
        }

        if (documentFiles.length > 0) {
          const uploaded = await Promise.all(
            documentFiles.map(async (file) => {
              const commonMetadata = {
                labels: { source: 'chat-attachment', version: 'v0.1.5' },
                namespace: 'cywell-aiops',
                runId: activeSessionId,
                sourceType: 'user-upload',
                version: 'v0.1.5',
              };
              const result = shouldUploadRagDocumentAsFile(file)
                ? await uploadRagDocumentFile(file, commonMetadata)
                : await uploadRagDocument({
                    ...commonMetadata,
                    content: await readRagDocumentContent(file),
                    mimeType: file.type || 'text/plain',
                    name: file.name,
                  });
              if (result.spec.status !== 'persisted') {
                throw new Error(
                  result.spec.reason || `${file.name} 문서를 RAG 저장소에 등록하지 못했습니다.`,
                );
              }
              return result.spec.document;
            }),
          );
          setUploadedDocuments((prev) => mergeUploadedDocuments(uploaded, prev));
          setHistoryPanelView('uploads');
          setHistorySidebarOpen(true);
        }

        setAttachmentError('');
      } catch (error) {
        setAttachmentError(error instanceof Error ? error.message : '파일을 처리하지 못했습니다.');
      }
    },
    [
      activeSessionId,
      pendingAttachments,
      setHistoryPanelView,
      setHistorySidebarOpen,
    ],
  );

  const removeAttachment = React.useCallback((id: string) => {
    setPendingAttachments((prev) => prev.filter((item) => item.id !== id));
    setAttachmentError('');
  }, []);

  return {
    addImageFiles,
    attachmentError,
    dragActive,
    pendingAttachments,
    removeAttachment,
    setAttachmentError,
    setDragActive,
    setPendingAttachments,
    uploadedDocuments,
    uploadedDocumentsError,
    uploadedDocumentsLoading,
  };
};
