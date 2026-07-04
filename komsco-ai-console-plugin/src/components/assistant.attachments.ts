import type { ImageAttachment } from '../services/aiGateway';

export const formatFileSize = (size: number): string => {
  if (size < 1024) {
    return `${size} B`;
  }

  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }

  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
};

export const getAttachmentPreviewUrl = (attachment: ImageAttachment): string =>
  `data:${attachment.mimeType};base64,${attachment.data}`;
