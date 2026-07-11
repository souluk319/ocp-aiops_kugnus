import * as React from 'react';

import { filesFromClipboardData, isAcceptedImageFile } from './assistant.uploadFiles';
import type { ImageAttachment } from '../services/aiGateway';

type UseAssistantAttachmentInteractionsOptions = {
  readonly addImageFiles: (files: File[]) => void | Promise<void>;
  readonly setDragActive: React.Dispatch<React.SetStateAction<boolean>>;
};

type UseAssistantAttachmentInteractionsResult = {
  readonly closeAttachmentPreview: () => void;
  readonly fileInputRef: React.RefObject<HTMLInputElement | null>;
  readonly handleDragEnter: React.DragEventHandler<HTMLDivElement>;
  readonly handleDragLeave: React.DragEventHandler<HTMLDivElement>;
  readonly handleDragOver: React.DragEventHandler<HTMLDivElement>;
  readonly handleDrop: React.DragEventHandler<HTMLDivElement>;
  readonly handleFileInputChange: React.ChangeEventHandler<HTMLInputElement>;
  readonly handlePaste: React.ClipboardEventHandler<HTMLTextAreaElement>;
  readonly openAttachmentPreview: (attachment: ImageAttachment) => void;
  readonly previewAttachment: ImageAttachment | null;
};

export const useAssistantAttachmentInteractions = ({
  addImageFiles,
  setDragActive,
}: UseAssistantAttachmentInteractionsOptions): UseAssistantAttachmentInteractionsResult => {
  const [previewAttachment, setPreviewAttachment] = React.useState<ImageAttachment | null>(null);
  const fileInputRef = React.useRef<HTMLInputElement | null>(null);

  const closeAttachmentPreview = React.useCallback(() => {
    setPreviewAttachment(null);
  }, []);

  const openAttachmentPreview = React.useCallback((attachment: ImageAttachment) => {
    setPreviewAttachment(attachment);
  }, []);

  React.useEffect(() => {
    if (!previewAttachment) {
      return undefined;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        closeAttachmentPreview();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [closeAttachmentPreview, previewAttachment]);

  const handleFileInputChange = React.useCallback<React.ChangeEventHandler<HTMLInputElement>>(
    (event) => {
      const files = Array.from(event.currentTarget.files ?? []);

      void addImageFiles(files);
      event.currentTarget.value = '';
    },
    [addImageFiles],
  );

  const handlePaste = React.useCallback<React.ClipboardEventHandler<HTMLTextAreaElement>>(
    (event) => {
      const files = filesFromClipboardData(event.clipboardData);
      if (!files.some(isAcceptedImageFile)) {
        return;
      }

      event.preventDefault();
      void addImageFiles(files);
    },
    [addImageFiles],
  );

  const handleDragEnter = React.useCallback<React.DragEventHandler<HTMLDivElement>>(
    (event) => {
      event.preventDefault();
      setDragActive(true);
    },
    [setDragActive],
  );

  const handleDragLeave = React.useCallback<React.DragEventHandler<HTMLDivElement>>(
    (event) => {
      if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
        setDragActive(false);
      }
    },
    [setDragActive],
  );

  const handleDragOver = React.useCallback<React.DragEventHandler<HTMLDivElement>>((event) => {
    event.preventDefault();
  }, []);

  const handleDrop = React.useCallback<React.DragEventHandler<HTMLDivElement>>(
    (event) => {
      event.preventDefault();
      setDragActive(false);
      void addImageFiles(filesFromClipboardData(event.dataTransfer));
    },
    [addImageFiles, setDragActive],
  );

  return {
    closeAttachmentPreview,
    fileInputRef,
    handleDragEnter,
    handleDragLeave,
    handleDragOver,
    handleDrop,
    handleFileInputChange,
    handlePaste,
    openAttachmentPreview,
    previewAttachment,
  };
};
