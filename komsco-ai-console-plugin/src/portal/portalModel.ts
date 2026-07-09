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
