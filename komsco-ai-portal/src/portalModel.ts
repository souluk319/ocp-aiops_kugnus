import type { AiopsEventFeed } from './types';

export const aiopsAlarmCount = (events: AiopsEventFeed): number =>
  events.spec.items.filter((item) => item.severity === 'risk' || item.severity === 'warn').length;

export const compactCount = (value: number): string => (value > 99 ? '99+' : String(value));

export const formatTime = (value?: string): string => {
  if (!value) {
    return '-';
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString('ko-KR', {
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    month: '2-digit',
  });
};

export const isOpenShiftAuthError = (error: string): boolean =>
  /Unauthorized|Missing OpenShift bearer token|openshift_user_auth_failed|사용자 인증|인증이 만료/.test(
    error,
  );

export const portalConnectionLabel = (isLive: boolean, error: string): string => {
  if (isLive) {
    return '게이트웨이 연결됨';
  }
  if (isOpenShiftAuthError(error)) {
    return 'OpenShift 인증 필요';
  }
  return '게이트웨이 연결 확인 필요';
};
