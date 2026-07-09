import * as React from 'react';

type AssistantTableWrapProps = {
  children: React.ReactNode;
  scrollKey?: string;
};

const tableScrollPositions = new Map<string, number>();
let generatedTableWrapId = 0;

const clampScrollLeft = (element: HTMLDivElement, value: number): number => {
  const maxScrollLeft = Math.max(element.scrollWidth - element.clientWidth, 0);
  return Math.min(Math.max(value, 0), maxScrollLeft);
};

export const AssistantTableWrap = ({
  children,
  scrollKey,
}: AssistantTableWrapProps): React.ReactElement => {
  const generatedScrollKeyRef = React.useRef<string | null>(null);
  if (!generatedScrollKeyRef.current) {
    generatedTableWrapId += 1;
    generatedScrollKeyRef.current = `assistant-table-${generatedTableWrapId}`;
  }
  const effectiveScrollKey = scrollKey ?? generatedScrollKeyRef.current;
  const wrapRef = React.useRef<HTMLDivElement | null>(null);
  const scrollLeftRef = React.useRef(tableScrollPositions.get(effectiveScrollKey) ?? 0);
  const userScrollingRef = React.useRef(false);

  React.useLayoutEffect(() => {
    const element = wrapRef.current;
    if (!element || userScrollingRef.current) {
      return;
    }
    const restoredScrollLeft = clampScrollLeft(
      element,
      tableScrollPositions.get(effectiveScrollKey) ?? scrollLeftRef.current,
    );
    if (element.scrollLeft !== restoredScrollLeft) {
      element.scrollLeft = restoredScrollLeft;
    }
  }, [effectiveScrollKey]);

  const handleScroll = React.useCallback(
    (event: React.UIEvent<HTMLDivElement>) => {
      const nextScrollLeft = event.currentTarget.scrollLeft;
      scrollLeftRef.current = nextScrollLeft;
      tableScrollPositions.set(effectiveScrollKey, nextScrollLeft);
    },
    [effectiveScrollKey],
  );

  const handlePointerDown = React.useCallback(() => {
    userScrollingRef.current = true;
  }, []);

  const handlePointerUp = React.useCallback(() => {
    const element = wrapRef.current;
    userScrollingRef.current = false;
    if (!element) {
      return;
    }
    scrollLeftRef.current = element.scrollLeft;
    tableScrollPositions.set(effectiveScrollKey, element.scrollLeft);
  }, [effectiveScrollKey]);

  return (
    <div
      className="komsco-ai__table-wrap"
      data-komsco-table-scroll="stable"
      onPointerDown={handlePointerDown}
      onPointerUp={handlePointerUp}
      onScroll={handleScroll}
      ref={wrapRef}
    >
      {children}
    </div>
  );
};
