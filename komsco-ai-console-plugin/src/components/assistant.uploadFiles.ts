import {
  ACCEPTED_IMAGE_MIME_TYPES,
  ACCEPTED_RAG_DOCUMENT_EXTENSIONS,
  ACCEPTED_RAG_DOCUMENT_MIME_TYPES,
  MULTIPART_RAG_DOCUMENT_EXTENSIONS,
  MULTIPART_RAG_DOCUMENT_MIME_TYPES,
} from './assistant.constants';
import type { ImageAttachment, RagUploadedDocument } from '../services/aiGateway';

const IMAGE_EXTENSION_MIME_TYPES: Record<string, string> = {
  '.gif': 'image/gif',
  '.jpeg': 'image/jpeg',
  '.jpg': 'image/jpeg',
  '.png': 'image/png',
  '.webp': 'image/webp',
};

export const isRagDocumentFile = (file: File): boolean => {
  const loweredName = file.name.toLowerCase();
  return (
    ACCEPTED_RAG_DOCUMENT_MIME_TYPES.has(file.type) ||
    file.type.startsWith('text/') ||
    ACCEPTED_RAG_DOCUMENT_EXTENSIONS.some((extension) => loweredName.endsWith(extension))
  );
};

export const shouldUploadRagDocumentAsFile = (file: File): boolean => {
  const loweredName = file.name.toLowerCase();
  return (
    MULTIPART_RAG_DOCUMENT_MIME_TYPES.has(file.type) ||
    MULTIPART_RAG_DOCUMENT_EXTENSIONS.some((extension) => loweredName.endsWith(extension))
  );
};

const inferImageMimeType = (file: File): string => {
  if (ACCEPTED_IMAGE_MIME_TYPES.has(file.type)) {
    return file.type;
  }

  const loweredName = file.name.toLowerCase();
  const extension = Object.keys(IMAGE_EXTENSION_MIME_TYPES).find((item) =>
    loweredName.endsWith(item),
  );
  return extension ? IMAGE_EXTENSION_MIME_TYPES[extension] : '';
};

export const isAcceptedImageFile = (file: File): boolean => Boolean(inferImageMimeType(file));

const fallbackImageName = (file: File, mimeType: string): string => {
  const name = file.name.trim();
  if (name) {
    return name;
  }

  const extension =
    Object.entries(IMAGE_EXTENSION_MIME_TYPES).find(([, value]) => value === mimeType)?.[0] ||
    '.png';
  return `clipboard-image-${Date.now().toString(36)}${extension}`;
};

export const uniqueFiles = (files: File[]): File[] => {
  const seen = new Set<string>();
  return files.filter((file) => {
    const key = [file.name, file.type, file.size, file.lastModified].join('|');
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
};

export const filesFromClipboardData = (data: DataTransfer): File[] => {
  const files = Array.from(data.files ?? []);
  const itemFiles = Array.from(data.items ?? [])
    .filter((item) => item.kind === 'file')
    .map((item) => item.getAsFile())
    .filter((file): file is File => Boolean(file));
  return uniqueFiles([...files, ...itemFiles]);
};

export const readRagDocumentContent = async (file: File): Promise<string> => {
  try {
    return await file.text();
  } catch {
    throw new Error(`${file.name} 문서를 읽을 수 없습니다.`);
  }
};

export const readImageAttachment = (file: File): Promise<ImageAttachment> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();
    const mimeType = inferImageMimeType(file);
    const displayName = fallbackImageName(file, mimeType);

    reader.onerror = () => reject(new Error(`${displayName} 파일을 읽을 수 없습니다.`));
    reader.onload = () => {
      const result = typeof reader.result === 'string' ? reader.result : '';
      const [, data = ''] = result.split(',');

      if (!data) {
        reject(new Error(`${file.name} 파일 데이터가 비어 있습니다.`));
        return;
      }

      resolve({
        data,
        id: `img-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
        mimeType,
        name: displayName,
        size: file.size,
      });
    };
    reader.readAsDataURL(file);
  });

export const mergeUploadedDocuments = (
  preferred: RagUploadedDocument[],
  fallback: RagUploadedDocument[],
): RagUploadedDocument[] => {
  const merged = new Map<string, RagUploadedDocument>();

  [...preferred, ...fallback].forEach((document) => {
    if (!merged.has(document.documentId)) {
      merged.set(document.documentId, document);
    }
  });

  return Array.from(merged.values());
};
