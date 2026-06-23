import * as React from 'react';
import { useOverlay } from '@openshift-console/dynamic-plugin-sdk';
import AssistantLauncher from '../components/AssistantLauncher';

const OVERLAY_ID = 'plugin__komsco-ai-console-plugin-kugnus__assistant-overlay';

type AssistantOverlayProps = {
  overlayId: string;
  closeOverlay: () => void;
};

const AssistantOverlay: React.FC<AssistantOverlayProps> = (props) => (
  <AssistantLauncher {...props} />
);

const useAssistantOverlay = (): null => {
  const launchOverlay = useOverlay();
  const launchedRef = React.useRef(false);

  React.useEffect(() => {
    const path = typeof window !== 'undefined' ? window.location.pathname : '';
    if (path.includes('/aiops-kugnus')) {
      return;
    }

    if (!launchedRef.current && launchOverlay) {
      launchOverlay(AssistantOverlay, { overlayId: OVERLAY_ID });
      launchedRef.current = true;
    }
  }, [launchOverlay]);

  return null;
};

export default useAssistantOverlay;
