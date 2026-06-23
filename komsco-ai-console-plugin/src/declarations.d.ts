declare module '*.png' {
  const src: string;
  export default src;
}

declare module '*.svg' {
  const src: string;
  export default src;
}

declare module 'react-dom' {
  import type * as React from 'react';

  export function createPortal(
    children: React.ReactNode,
    container: Element | DocumentFragment,
  ): React.ReactPortal;
}
