import * as React from 'react';
import * as ReactDOM from 'react-dom';

type AssistantSurfacePortalProps = {
  active: boolean;
  children: React.ReactNode;
  wrapperClassName: string;
};

const AssistantSurfacePortal: React.FC<AssistantSurfacePortalProps> = ({
  active,
  children,
  wrapperClassName,
}) => {
  if (active && typeof document !== 'undefined') {
    return ReactDOM.createPortal(<div className={wrapperClassName}>{children}</div>, document.body);
  }

  return <>{children}</>;
};

export default AssistantSurfacePortal;
