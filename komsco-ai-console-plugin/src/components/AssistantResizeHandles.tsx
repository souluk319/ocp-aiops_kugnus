import * as React from 'react';

import type { AssistantCopy } from './assistant.copy';
import type { PanelResizeDirection } from './assistant.types';

type AssistantResizeHandlesProps = {
  copy: AssistantCopy;
  onResizeStart: (
    event: React.MouseEvent<HTMLButtonElement>,
    direction: PanelResizeDirection,
  ) => void;
};

const RESIZE_DIRECTIONS: PanelResizeDirection[] = ['n', 'ne', 'e', 'se', 's', 'sw', 'w', 'nw'];

const AssistantResizeHandles: React.FC<AssistantResizeHandlesProps> = ({ copy, onResizeStart }) => (
  <div className="komsco-ai__resize-handles" aria-label={copy.resizeHandles}>
    {RESIZE_DIRECTIONS.map((direction) => (
      <button
        aria-label={`${copy.resizeHandlePrefix} ${direction}`}
        className={`komsco-ai__resize-handle komsco-ai__resize-handle--${direction}${
          direction === 'se' ? ' komsco-ai__resize-grip' : ''
        }`}
        key={direction}
        onMouseDown={(event) => onResizeStart(event, direction)}
        type="button"
      />
    ))}
  </div>
);

export default AssistantResizeHandles;
