import * as React from 'react';
import { useOverlay } from '@openshift-console/dynamic-plugin-sdk';
import AssistantLauncher from '../components/AssistantLauncher';

const OVERLAY_ID = 'plugin__komsco-ai-console-plugin-kugnus__assistant-overlay';
const AIOPS_ROUTE_PREFIX = '/aiops-kugnus';

type AssistantOverlayProps = {
  overlayId: string;
  closeOverlay: () => void;
};

const getCurrentPathname = (): string =>
  typeof window === 'undefined' ? '' : window.location.pathname;

const useCurrentPathname = (): string => {
  const [pathname, setPathname] = React.useState(getCurrentPathname);

  React.useEffect(() => {
    const syncPathname = (): void => {
      setPathname(getCurrentPathname());
    };
    const timer = window.setInterval(syncPathname, 250);

    window.addEventListener('popstate', syncPathname);
    window.addEventListener('hashchange', syncPathname);

    return () => {
      window.clearInterval(timer);
      window.removeEventListener('popstate', syncPathname);
      window.removeEventListener('hashchange', syncPathname);
    };
  }, []);

  return pathname;
};

const AssistantOverlay: React.FC<AssistantOverlayProps> = (props) => {
  const pathname = useCurrentPathname();

  if (pathname.includes(AIOPS_ROUTE_PREFIX)) {
    return null;
  }

  return <AssistantLauncher {...props} />;
};

const useAssistantOverlay = (): null => {
  const launchOverlay = useOverlay();
  const launchedRef = React.useRef(false);

  React.useEffect(() => {
    if (!launchedRef.current && launchOverlay) {
      launchOverlay(AssistantOverlay, { overlayId: OVERLAY_ID });
      launchedRef.current = true;
    }
  }, [launchOverlay]);

  return null;
};

export default useAssistantOverlay;
