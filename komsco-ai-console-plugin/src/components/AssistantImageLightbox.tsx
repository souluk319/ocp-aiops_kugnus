import * as React from 'react';
import { Button } from '@patternfly/react-core';

import type { ImageAttachment } from '../services/aiGateway';
import { formatFileSize, getAttachmentPreviewUrl } from './assistant.attachments';
import { CoolCloseIcon } from './coolicons';

type AssistantImageLightboxProps = {
  attachment: ImageAttachment;
  onClose: () => void;
};

const AssistantImageLightbox: React.FC<AssistantImageLightboxProps> = ({ attachment, onClose }) => (
  <div
    aria-label={`${attachment.name} 크게 보기`}
    aria-modal="true"
    className="komsco-ai__image-lightbox"
    onClick={onClose}
    role="dialog"
  >
    <div
      className="komsco-ai__image-lightbox-panel"
      onClick={(event) => event.stopPropagation()}
    >
      <div className="komsco-ai__image-lightbox-head">
        <div className="komsco-ai__image-lightbox-title">
          <strong>{attachment.name}</strong>
          <span>
            {attachment.mimeType} · {formatFileSize(attachment.size)}
          </span>
        </div>
        <Button
          aria-label="이미지 크게 보기 닫기"
          className="komsco-ai__image-lightbox-close"
          onClick={onClose}
          variant="plain"
        >
          <CoolCloseIcon />
        </Button>
      </div>
      <div className="komsco-ai__image-lightbox-body">
        <img
          alt={attachment.name}
          className="komsco-ai__image-lightbox-image"
          src={getAttachmentPreviewUrl(attachment)}
        />
      </div>
    </div>
  </div>
);

export default AssistantImageLightbox;
