import * as React from 'react';

import type { PanelResizeDirection } from './assistant.types';

type AssistantResizeHandlesProps = {
  onResizeStart: (
    event: React.MouseEvent<HTMLButtonElement>,
    direction: PanelResizeDirection,
  ) => void;
};

const RESIZE_DIRECTIONS: PanelResizeDirection[] = ['n', 'ne', 'e', 'se', 's', 'sw', 'w', 'nw'];

const AssistantResizeHandles: React.FC<AssistantResizeHandlesProps> = ({ onResizeStart }) => (
  <div className="komsco-ai__resize-handles" aria-label="채팅창 크기 조절 핸들">
    {RESIZE_DIRECTIONS.map((direction) => (
      <button
        aria-label={`채팅창 ${direction} 방향 크기 조절`}
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
