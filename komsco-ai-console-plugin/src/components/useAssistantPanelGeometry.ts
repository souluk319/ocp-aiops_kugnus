import * as React from 'react';

import { HISTORY_DRAWER_WIDTH } from './assistant.constants';
import type { PanelResizeDirection } from './assistant.types';

type UseAssistantPanelGeometryOptions = {
  embedded: boolean;
  fullScreen: boolean;
  historySidebarOpen: boolean;
  surfaceRef: React.RefObject<HTMLDivElement>;
};

type PanelGeometryStyle = React.CSSProperties & Record<string, string | number | undefined>;

export type AssistantPanelGeometry = {
  historySidebarStyle: React.CSSProperties;
  panelDragActive: boolean;
  panelResizeUnlocked: boolean;
  resetPanelGeometry: () => void;
  startPanelDrag: (event: React.MouseEvent<HTMLElement>) => void;
  startPanelResize: (event: React.MouseEvent<HTMLElement>, direction: PanelResizeDirection) => void;
  surfaceStyle: React.CSSProperties;
  togglePanelResizeLock: () => void;
};

export const useAssistantPanelGeometry = ({
  embedded,
  fullScreen,
  historySidebarOpen,
  surfaceRef,
}: UseAssistantPanelGeometryOptions): AssistantPanelGeometry => {
  const [panelResizeUnlocked, setPanelResizeUnlocked] = React.useState(false);
  const [panelSize, setPanelSize] = React.useState<{ height?: number; width?: number }>({});
  const [panelOffset, setPanelOffset] = React.useState({ x: 0, y: 0 });
  const [panelDragActive, setPanelDragActive] = React.useState(false);
  const [historyDrawerBounds, setHistoryDrawerBounds] = React.useState<{
    height?: number;
    left?: number;
    top?: number;
  }>({});
  const panelDragFrameRef = React.useRef<number | undefined>();
  const panelDragNextOffsetRef = React.useRef<{ x: number; y: number } | null>(null);

  React.useEffect(
    () => () => {
      if (panelDragFrameRef.current !== undefined) {
        window.cancelAnimationFrame(panelDragFrameRef.current);
        panelDragFrameRef.current = undefined;
      }
      panelDragNextOffsetRef.current = null;
    },
    [],
  );

  const surfaceStyle = React.useMemo<React.CSSProperties>(() => {
    if (fullScreen) {
      return {};
    }

    const style: PanelGeometryStyle = {};
    if (panelSize.height) {
      style.height = `${panelSize.height}px`;
      style['--komsco-panel-height'] = `${panelSize.height}px`;
    }
    if (panelSize.width) {
      style.width = `${panelSize.width}px`;
    }
    if (panelOffset.x || panelOffset.y) {
      style.transform = `translate(${panelOffset.x}px, ${panelOffset.y}px)`;
    }
    if (
      historySidebarOpen &&
      historyDrawerBounds.height &&
      historyDrawerBounds.left !== undefined &&
      historyDrawerBounds.top !== undefined
    ) {
      style['--komsco-history-height'] = `${historyDrawerBounds.height}px`;
      style['--komsco-history-left'] = `${historyDrawerBounds.left}px`;
      style['--komsco-history-top'] = `${historyDrawerBounds.top}px`;
    }
    return style;
  }, [
    fullScreen,
    historyDrawerBounds.height,
    historyDrawerBounds.left,
    historyDrawerBounds.top,
    historySidebarOpen,
    panelOffset.x,
    panelOffset.y,
    panelSize.height,
    panelSize.width,
  ]);

  const historySidebarStyle = React.useMemo<React.CSSProperties>(() => {
    if (
      fullScreen ||
      !historySidebarOpen ||
      !historyDrawerBounds.height ||
      historyDrawerBounds.left === undefined ||
      historyDrawerBounds.top === undefined
    ) {
      return {};
    }

    const style: PanelGeometryStyle = {};
    style['--komsco-history-height'] = `${historyDrawerBounds.height}px`;
    style['--komsco-history-left'] = `${historyDrawerBounds.left}px`;
    style['--komsco-history-top'] = `${historyDrawerBounds.top}px`;
    return style;
  }, [
    fullScreen,
    historyDrawerBounds.height,
    historyDrawerBounds.left,
    historyDrawerBounds.top,
    historySidebarOpen,
  ]);

  const captureCurrentPanelSize = React.useCallback(() => {
    const surface = surfaceRef.current;
    if (!surface || fullScreen) {
      return;
    }

    const rect = surface.getBoundingClientRect();
    setPanelSize({
      height: Math.round(rect.height),
      width: Math.round(rect.width),
    });
  }, [fullScreen, surfaceRef]);

  const togglePanelResizeLock = React.useCallback(() => {
    if (!panelResizeUnlocked) {
      captureCurrentPanelSize();
    }

    setPanelResizeUnlocked((value) => !value);
  }, [captureCurrentPanelSize, panelResizeUnlocked]);

  const startPanelDrag = React.useCallback(
    (event: React.MouseEvent<HTMLElement>) => {
      if (!panelResizeUnlocked || fullScreen || event.button !== 0) {
        return;
      }

      const target = event.target as HTMLElement | null;
      if (
        target?.closest(
          'button, a, input, textarea, select, [role="button"], .komsco-ai__header-status',
        )
      ) {
        return;
      }

      const surface = surfaceRef.current;
      if (!surface) {
        return;
      }

      event.preventDefault();
      event.stopPropagation();

      const rect = surface.getBoundingClientRect();
      const startX = event.clientX;
      const startY = event.clientY;
      const startOffset = panelOffset;
      const baseLeft = rect.left - startOffset.x;
      const baseTop = rect.top - startOffset.y;
      const minLeft = 8;
      const maxLeft = Math.max(minLeft, window.innerWidth - Math.min(rect.width, 180));
      const minTop = 8;
      const maxTop = Math.max(minTop, window.innerHeight - 120);
      const clamp = (value: number, min: number, max: number) =>
        Math.min(Math.max(value, min), max);
      const previousUserSelect = document.body.style.userSelect;
      const previousCursor = document.body.style.cursor;

      setPanelDragActive(true);
      document.body.style.userSelect = 'none';
      document.body.style.cursor = 'grabbing';

      const applyPanelOffset = (nextOffset: { x: number; y: number }) => {
        panelDragNextOffsetRef.current = nextOffset;
        if (panelDragFrameRef.current !== undefined) {
          return;
        }

        panelDragFrameRef.current = window.requestAnimationFrame(() => {
          panelDragFrameRef.current = undefined;
          const pendingOffset = panelDragNextOffsetRef.current;
          panelDragNextOffsetRef.current = null;
          if (!pendingOffset) {
            return;
          }

          setPanelOffset({
            x: Number(pendingOffset.x.toFixed(1)),
            y: Number(pendingOffset.y.toFixed(1)),
          });
        });
      };

      const handleMouseMove = (moveEvent: MouseEvent) => {
        const rawX = startOffset.x + moveEvent.clientX - startX;
        const rawY = startOffset.y + moveEvent.clientY - startY;
        applyPanelOffset({
          x: clamp(rawX, minLeft - baseLeft, maxLeft - baseLeft),
          y: clamp(rawY, minTop - baseTop, maxTop - baseTop),
        });
      };

      const stopPanelDrag = () => {
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', stopPanelDrag);
        if (panelDragFrameRef.current !== undefined) {
          window.cancelAnimationFrame(panelDragFrameRef.current);
          panelDragFrameRef.current = undefined;
        }
        const finalOffset = panelDragNextOffsetRef.current;
        panelDragNextOffsetRef.current = null;
        if (finalOffset) {
          setPanelOffset({
            x: Number(finalOffset.x.toFixed(1)),
            y: Number(finalOffset.y.toFixed(1)),
          });
        }
        document.body.style.userSelect = previousUserSelect;
        document.body.style.cursor = previousCursor;
        setPanelDragActive(false);
      };

      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', stopPanelDrag);
    },
    [fullScreen, panelOffset, panelResizeUnlocked, surfaceRef],
  );

  const updateHistoryDrawerBounds = React.useCallback(() => {
    const surface = surfaceRef.current;
    if (!surface || !historySidebarOpen || fullScreen) {
      return;
    }

    const rect = surface.getBoundingClientRect();
    const next = {
      height: Math.round(rect.height),
      left: Math.max(8, Math.round(rect.left - HISTORY_DRAWER_WIDTH)),
      top: Math.round(rect.top),
    };

    setHistoryDrawerBounds((prev) =>
      prev.height === next.height && prev.left === next.left && prev.top === next.top ? prev : next,
    );
  }, [fullScreen, historySidebarOpen, surfaceRef]);

  const startPanelResize = React.useCallback(
    (event: React.MouseEvent<HTMLElement>, direction: PanelResizeDirection) => {
      if (!panelResizeUnlocked || fullScreen) {
        return;
      }

      const surface = event.currentTarget.closest('.komsco-ai__surface') as HTMLElement | null;
      if (!surface) {
        return;
      }

      event.preventDefault();
      event.stopPropagation();

      const initialRect = surface.getBoundingClientRect();
      const parentRect = surface.parentElement?.getBoundingClientRect();
      const startX = event.clientX;
      const startY = event.clientY;
      const startOffset = panelOffset;
      const minHeight = 420;
      const viewportPadding = 8;
      const maxHeight = Math.max(minHeight, window.innerHeight - viewportPadding * 2);
      const minWidth = Math.min(460, Math.max(320, window.innerWidth - 32));
      const maxWidth = Math.max(
        minWidth,
        embedded
          ? Math.min(parentRect?.width || window.innerWidth - 32, window.innerWidth - 32)
          : window.innerWidth - viewportPadding * 2,
      );
      const clamp = (value: number, min: number, max: number) =>
        Math.min(Math.max(value, min), max);
      const previousUserSelect = document.body.style.userSelect;
      const previousCursor = document.body.style.cursor;
      const resizeCursor =
        direction.includes('n') && direction.includes('e')
          ? 'nesw-resize'
          : direction.includes('s') && direction.includes('w')
            ? 'nesw-resize'
            : direction.includes('n') && direction.includes('w')
              ? 'nwse-resize'
              : direction.includes('s') && direction.includes('e')
                ? 'nwse-resize'
                : direction.includes('n') || direction.includes('s')
                  ? 'ns-resize'
                  : 'ew-resize';

      document.body.style.userSelect = 'none';
      document.body.style.cursor = resizeCursor;

      const handleMouseMove = (moveEvent: MouseEvent) => {
        const deltaX = moveEvent.clientX - startX;
        const deltaY = moveEvent.clientY - startY;
        const widthMaxForDirection = direction.includes('e')
          ? Math.min(maxWidth, window.innerWidth - initialRect.left - viewportPadding)
          : direction.includes('w')
            ? Math.min(maxWidth, initialRect.right - viewportPadding)
            : maxWidth;
        const heightMaxForDirection = direction.includes('s')
          ? Math.min(maxHeight, window.innerHeight - initialRect.top - viewportPadding)
          : direction.includes('n')
            ? Math.min(maxHeight, initialRect.bottom - viewportPadding)
            : maxHeight;
        const nextHeight = direction.includes('n')
          ? clamp(initialRect.height - deltaY, minHeight, heightMaxForDirection)
          : direction.includes('s')
            ? clamp(initialRect.height + deltaY, minHeight, heightMaxForDirection)
            : initialRect.height;
        const nextWidth = direction.includes('w')
          ? clamp(initialRect.width - deltaX, minWidth, widthMaxForDirection)
          : direction.includes('e')
            ? clamp(initialRect.width + deltaX, minWidth, widthMaxForDirection)
            : initialRect.width;
        const nextOffset = {
          x:
            !embedded && direction.includes('e')
              ? startOffset.x + nextWidth - initialRect.width
              : startOffset.x,
          y:
            !embedded && direction.includes('s')
              ? startOffset.y + nextHeight - initialRect.height
              : startOffset.y,
        };

        setPanelSize({
          height: Math.round(nextHeight),
          width: Math.round(nextWidth),
        });
        if (!embedded && (direction.includes('e') || direction.includes('s'))) {
          setPanelOffset({
            x: Number(nextOffset.x.toFixed(1)),
            y: Number(nextOffset.y.toFixed(1)),
          });
        }
      };

      const stopPanelResize = () => {
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', stopPanelResize);
        document.body.style.userSelect = previousUserSelect;
        document.body.style.cursor = previousCursor;
      };

      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', stopPanelResize);
    },
    [embedded, fullScreen, panelOffset, panelResizeUnlocked],
  );

  React.useLayoutEffect(() => {
    if (!historySidebarOpen || fullScreen) {
      setHistoryDrawerBounds({});
      return undefined;
    }

    updateHistoryDrawerBounds();
    window.addEventListener('resize', updateHistoryDrawerBounds);
    window.addEventListener('scroll', updateHistoryDrawerBounds, true);

    const observer =
      typeof ResizeObserver === 'undefined'
        ? undefined
        : new ResizeObserver(updateHistoryDrawerBounds);
    if (surfaceRef.current) {
      observer?.observe(surfaceRef.current);
    }

    return () => {
      window.removeEventListener('resize', updateHistoryDrawerBounds);
      window.removeEventListener('scroll', updateHistoryDrawerBounds, true);
      observer?.disconnect();
    };
  }, [fullScreen, historySidebarOpen, surfaceRef, updateHistoryDrawerBounds]);

  const resetPanelGeometry = React.useCallback(() => {
    setHistoryDrawerBounds({});
    setPanelResizeUnlocked(false);
    setPanelSize({});
    setPanelOffset({ x: 0, y: 0 });
    setPanelDragActive(false);
  }, []);

  return {
    historySidebarStyle,
    panelDragActive,
    panelResizeUnlocked,
    resetPanelGeometry,
    startPanelDrag,
    startPanelResize,
    surfaceStyle,
    togglePanelResizeLock,
  };
};
