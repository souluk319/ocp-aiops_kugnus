import * as React from 'react';
import { useOverlay } from '@openshift-console/dynamic-plugin-sdk';
import type { OverlayComponent } from '@openshift-console/dynamic-plugin-sdk/lib/app/modal-support/OverlayProvider';
import AssistantLauncher from '../components/AssistantLauncher';
import type { AssistantLauncherProps } from '../components/assistant.types';

export const OVERLAY_ID = 'plugin__cywell-aiops-console-plugin__assistant-overlay';
const AIOPS_ROUTE_PREFIX = '/dashboards/aiops';

export type AssistantOverlayLaunchProps = AssistantLauncherProps & {
  overlayId: string;
};

type AssistantOverlayProps = AssistantOverlayLaunchProps & {
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

export const AssistantOverlay: OverlayComponent<AssistantOverlayLaunchProps> = (
  props: AssistantOverlayProps,
) => {
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
