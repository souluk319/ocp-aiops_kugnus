// v2 내부 라우팅: 반드시 '#v2/' 프리픽스 해시만 사용한다.
// 프리픽스 없는 해시(#alerts 등)는 App.tsx의 hashchange 리스너가
// v1 최상위 네비게이션으로 해석해 v2 밖으로 이탈시키기 때문.
export type V2View =
  | 'dashboard'
  | 'executions'
  | 'rca'
  | 'service-map'
  | 'resources'
  | 'alerts'
  | 'wiki'
  | 'reports'
  | 'settings';

const v2Views: V2View[] = [
  'dashboard',
  'executions',
  'rca',
  'service-map',
  'resources',
  'alerts',
  'wiki',
  'reports',
  'settings',
];

export const v2ViewFromHash = (): V2View => {
  if (typeof window === 'undefined') {
    return 'dashboard';
  }
  const hash = decodeURIComponent(window.location.hash.replace(/^#\/?/, ''));
  if (hash.startsWith('v2/')) {
    const candidate = hash.slice(3);
    if ((v2Views as string[]).includes(candidate)) {
      return candidate as V2View;
    }
  }
  return 'dashboard';
};

// replaceState라 hashchange가 발생하지 않고 히스토리 스택도 오염되지 않는다.
export const writeV2Hash = (view: V2View): void => {
  const url = `${window.location.pathname}#v2/${view}`;
  window.history.replaceState(window.history.state, '', url);
};
