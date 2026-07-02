import * as React from 'react';
import { useOverlay } from '@openshift-console/dynamic-plugin-sdk';
import {
  AssistantOverlay,
  type AssistantOverlayLaunchProps,
  OVERLAY_ID,
} from './useAssistantOverlay';

export type OpenAIOpsHandler = (
  query?: string,
  attachments?: unknown[],
  autoSubmit?: boolean,
  hidePrompt?: boolean,
) => void;

const queryToDraftPrompt = (query?: string) => {
  const prompt = query?.trim();

  if (!prompt) {
    return undefined;
  }

  return {
    id: `ols-open-${Date.now().toString(36)}`,
    prompt,
  };
};

const useOpenAIOps = (): OpenAIOpsHandler => {
  const launchOverlay = useOverlay();

  return React.useCallback(
    (query?: string): void => {
      const overlayProps: AssistantOverlayLaunchProps = {
        defaultOpen: true,
        draftPrompt: queryToDraftPrompt(query),
        overlayId: OVERLAY_ID,
      };

      launchOverlay(AssistantOverlay, overlayProps);
    },
    [launchOverlay],
  );
};

export default useOpenAIOps;
