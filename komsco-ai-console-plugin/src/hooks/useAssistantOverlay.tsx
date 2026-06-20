import * as React from 'react';
import { useOverlay } from '@openshift-console/dynamic-plugin-sdk';
import AssistantLauncher from '../components/AssistantLauncher';

const OVERLAY_ID = 'plugin__komsco-ai-console-plugin__assistant-overlay';

const useAssistantOverlay = (): null => {
  const launchOverlay = useOverlay();
  const launchedRef = React.useRef(false);

  React.useEffect(() => {
    if (!launchedRef.current && launchOverlay) {
      launchOverlay(AssistantLauncher, { overlayId: OVERLAY_ID });
      launchedRef.current = true;
    }
  }, [launchOverlay]);

  return null;
};

export default useAssistantOverlay;
