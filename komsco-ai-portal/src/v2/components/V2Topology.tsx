import React from 'react';
import { Boxes, Database, Globe, Layers, Server, Share2 } from 'lucide-react';
import type { AiopsEventFeed, ClusterSummary, Severity } from '../../types';
import {
  buildPodRcaSummary,
  clusterLabel,
  eventSeverityRank,
  formatTime,
  resourceNameLabel,
  resourceNodeDetail,
  resourceNodeSeverity,
  topologyNodeSummary,
  topologySeverityHints,
  type TopologyEdgeMode,
  type TopologyNodeKey,
} from '../lib/model';

/*
 * 순수 SVG 네트워크 다이어그램.
 * 노드 좌표에서 엣지 경로를 계산해 그리고, 트래픽 엣지에는 animateMotion 파티클을 흘린다.
 */

type Box = { h: number; w: number; x: number; y: number };
type Side = 'top' | 'bottom' | 'left' | 'right';

const VIEW_W = 1000;
const VIEW_H = 560;

const layout: Record<TopologyNodeKey, Box> = {
  routes: { x: 36, y: 104, w: 204, h: 66 },
  services: { x: 36, y: 330, w: 204, h: 66 },
  deployments: { x: 312, y: 64, w: 212, h: 66 },
  statefulsets: { x: 312, y: 222, w: 212, h: 66 },
  daemonsets: { x: 312, y: 380, w: 212, h: 66 },
  replicasets: { x: 584, y: 64, w: 190, h: 62 },
  pods: { x: 726, y: 226, w: 238, h: 78 },
  nodes: { x: 596, y: 442, w: 184, h: 66 },
  persistentvolumeclaims: { x: 806, y: 442, w: 170, h: 66 },
};

type EdgeDef = {
  from: TopologyNodeKey;
  fromSide: Side;
  fromT?: number; // 0~1, 변 위 접속 위치 (기본 0.5) — 같은 변에 여러 엣지가 몰리지 않게 분산
  kind: 'traffic' | 'owner' | 'runtime';
  label?: string;
  labelAt?: number; // 0~1, 경로상 라벨 위치
  to: TopologyNodeKey;
  toSide: Side;
  toT?: number;
};

const edges: EdgeDef[] = [
  { from: 'routes', fromSide: 'bottom', to: 'services', toSide: 'top', kind: 'traffic', label: '노출', labelAt: 0.5 },
  { from: 'services', fromSide: 'right', fromT: 0.5, to: 'pods', toSide: 'left', toT: 0.62, kind: 'traffic', label: '선택', labelAt: 0.4 },
  { from: 'deployments', fromSide: 'right', to: 'replicasets', toSide: 'left', kind: 'owner', label: '소유', labelAt: 0.45 },
  { from: 'replicasets', fromSide: 'bottom', fromT: 0.6, to: 'pods', toSide: 'top', toT: 0.55, kind: 'owner' },
  { from: 'statefulsets', fromSide: 'right', fromT: 0.4, to: 'pods', toSide: 'left', toT: 0.3, kind: 'owner' },
  { from: 'daemonsets', fromSide: 'right', fromT: 0.4, to: 'pods', toSide: 'left', toT: 0.88, kind: 'owner' },
  { from: 'nodes', fromSide: 'top', to: 'pods', toSide: 'bottom', toT: 0.32, kind: 'runtime', label: '스케줄', labelAt: 0.5 },
  { from: 'persistentvolumeclaims', fromSide: 'top', to: 'pods', toSide: 'bottom', toT: 0.74, kind: 'runtime', label: '마운트', labelAt: 0.5 },
];

const anchor = (box: Box, side: Side, t = 0.5): [number, number] => {
  if (side === 'top') return [box.x + box.w * t, box.y];
  if (side === 'bottom') return [box.x + box.w * t, box.y + box.h];
  if (side === 'left') return [box.x, box.y + box.h * t];
  return [box.x + box.w, box.y + box.h * t];
};

const edgePath = (edge: EdgeDef): string => {
  const [x0, y0] = anchor(layout[edge.from], edge.fromSide, edge.fromT);
  const [x1, y1] = anchor(layout[edge.to], edge.toSide, edge.toT);
  const horizontal = edge.fromSide === 'left' || edge.fromSide === 'right';
  if (horizontal) {
    const cx = (x0 + x1) / 2;
    return `M${x0},${y0} C${cx},${y0} ${cx},${y1} ${x1},${y1}`;
  }
  const cy = (y0 + y1) / 2;
  return `M${x0},${y0} C${x0},${cy} ${x1},${cy} ${x1},${y1}`;
};

const pointAt = (edge: EdgeDef, t: number): [number, number] => {
  // 3차 베지어 근사 좌표 (라벨 배치용)
  const [x0, y0] = anchor(layout[edge.from], edge.fromSide, edge.fromT);
  const [x3, y3] = anchor(layout[edge.to], edge.toSide, edge.toT);
  const horizontal = edge.fromSide === 'left' || edge.fromSide === 'right';
  const [x1, y1] = horizontal ? [(x0 + x3) / 2, y0] : [x0, (y0 + y3) / 2];
  const [x2, y2] = horizontal ? [(x0 + x3) / 2, y3] : [x3, (y0 + y3) / 2];
  const u = 1 - t;
  return [
    u * u * u * x0 + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t * t * t * x3,
    u * u * u * y0 + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t * t * t * y3,
  ];
};

const nodeIcons: Record<TopologyNodeKey, React.ReactNode> = {
  routes: <Globe size={15} />,
  services: <Share2 size={15} />,
  deployments: <Boxes size={15} />,
  statefulsets: <Layers size={15} />,
  daemonsets: <Layers size={15} />,
  replicasets: <Boxes size={15} />,
  pods: <Boxes size={16} />,
  nodes: <Server size={15} />,
  persistentvolumeclaims: <Database size={15} />,
};

export const V2Topology: React.FC<{
  affectedOnly?: boolean;
  compact?: boolean;
  edgeMode?: TopologyEdgeMode;
  events?: AiopsEventFeed;
  onSelectNode?: (node: TopologyNodeKey) => void;
  selectedNode?: TopologyNodeKey;
  showEdgeLabels?: boolean;
  summary: ClusterSummary;
}> = ({
  affectedOnly = false,
  compact = false,
  edgeMode = 'all',
  events,
  onSelectNode,
  selectedNode,
  showEdgeLabels = true,
  summary,
}) => {
  const nodeState: Severity =
    summary.nodes.notReady > 0 ? 'risk' : summary.nodes.pressureCount > 0 ? 'warn' : 'ok';
  const resources = summary.resources?.items ?? [];
  const byId = (id: string) => resources.find((resource) => resource.id === id);
  const issueCount = summary.resources?.issues ?? 0;
  const podSummary = buildPodRcaSummary(summary);
  // 게이트웨이 종류별 집계(summary.resources)와 별도 API인 이벤트 피드를 여기서 합류시킨다 —
  // 종류별 집계가 'ok'라도 실제 이벤트(CrashLoopBackOff 등)가 있으면 해당 노드를 끌어올린다.
  const eventHints = React.useMemo(() => (events ? topologySeverityHints(events) : {}), [events]);

  const nodeModel = (key: TopologyNodeKey): { detail: string; label: string; severity: Severity } => {
    const hint = eventHints[key];
    if (key === 'nodes') {
      const base = { detail: topologyNodeSummary(summary, 'nodes').detail, label: '노드', severity: nodeState };
      if (hint && eventSeverityRank[hint.severity] > eventSeverityRank[base.severity]) {
        return { ...base, detail: hint.detail, severity: hint.severity };
      }
      return base;
    }
    const resource = byId(key);
    const fallback: Record<TopologyNodeKey, string> = {
      routes: '라우트',
      services: '서비스',
      deployments: '디플로이먼트',
      statefulsets: '스테이트풀셋',
      daemonsets: '데몬셋',
      replicasets: '레플리카셋',
      pods: '파드',
      nodes: '노드',
      persistentvolumeclaims: 'PVC',
    };
    const label = resource ? resourceNameLabel(resource.id, resource.name, resource.kind) : fallback[key];
    const baseSeverity = resourceNodeSeverity(resource);
    if (hint && eventSeverityRank[hint.severity] > eventSeverityRank[baseSeverity]) {
      return { detail: hint.detail, label, severity: hint.severity };
    }
    return {
      detail: resourceNodeDetail(resource, `${fallback[key]} 신호 없음`),
      label,
      severity: baseSeverity,
    };
  };

  const severityOf: Record<TopologyNodeKey, Severity> = Object.fromEntries(
    (Object.keys(layout) as TopologyNodeKey[]).map((key) => [key, nodeModel(key).severity]),
  ) as Record<TopologyNodeKey, Severity>;

  const edgeSeverity = (edge: EdgeDef): Severity => {
    const pair = [severityOf[edge.from], severityOf[edge.to]];
    if (pair.includes('risk')) return 'risk';
    if (pair.includes('warn')) return 'warn';
    return 'ok';
  };

  const edgeVisible = (edge: EdgeDef): boolean => {
    if (edgeMode === 'all') return true;
    if (edgeMode === 'traffic') return edge.kind === 'traffic';
    if (edgeMode === 'ownership') return edge.kind === 'owner';
    return edge.kind === 'runtime';
  };

  return (
    <div className={`v2-net${compact ? ' is-compact' : ''}`} role="img" aria-label="클러스터 리소스 관계도">
      {!compact && (
        <div className="v2-net__top">
          <div>
            <span className="v2-kicker">Service Impact Graph</span>
            <strong>{clusterLabel(summary)}</strong>
          </div>
          <div className="v2-net__snapshot">
            <span>스냅샷</span>
            <strong>{formatTime(summary.updatedAt)}</strong>
          </div>
        </div>
      )}

      <div className="v2-net__stage">
        <svg viewBox={`0 0 ${VIEW_W} ${VIEW_H}`} preserveAspectRatio="xMidYMid meet">
          <defs>
            <radialGradient id="v2net-glow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="currentColor" stopOpacity="0.25" />
              <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
            </radialGradient>
            <linearGradient id="v2net-focal" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="#6366f1" />
              <stop offset="100%" stopColor="#22d3ee" />
            </linearGradient>
            <pattern id="v2net-dots" width="26" height="26" patternUnits="userSpaceOnUse">
              <circle className="v2-net__dot" cx="1.2" cy="1.2" r="1.2" />
            </pattern>
          </defs>

          {/* 배경 */}
          <rect className="v2-net__bg" x="0" y="0" width={VIEW_W} height={VIEW_H} rx="14" />
          <rect x="0" y="0" width={VIEW_W} height={VIEW_H} fill="url(#v2net-dots)" rx="14" />

          {/* 레이어 밴드 */}
          <g className="v2-net__bands">
            <rect x="22" y="34" width="232" height="392" rx="14" />
            <rect x="296" y="34" width="244" height="440" rx="14" />
            <rect x="566" y="34" width="412" height="300" rx="14" />
            <rect x="566" y="410" width="412" height="126" rx="14" />
            <text x="38" y="60">트래픽 진입</text>
            <text x="312" y="60">워크로드 컨트롤러</text>
            <text x="582" y="60">파드 런타임</text>
            <text x="582" y="436">런타임 기반</text>
          </g>

          {/* 엣지 */}
          <g className="v2-net__edges">
            {edges.map((edge) => {
              const d = edgePath(edge);
              const severity = edgeSeverity(edge);
              const visible = edgeVisible(edge);
              const related = selectedNode ? edge.from === selectedNode || edge.to === selectedNode : undefined;
              const relationClass =
                visible && related !== undefined ? (related ? ' is-related' : ' is-unrelated') : '';
              const [lx, ly] = pointAt(edge, edge.labelAt ?? 0.5);
              return (
                <g
                  className={`v2-net-edge is-${edge.kind} is-${severity}${visible ? '' : ' is-muted'}${relationClass}`}
                  key={`${edge.from}-${edge.to}`}
                >
                  <path className="v2-net-edge__halo" d={d} />
                  <path className="v2-net-edge__line" d={d} />
                  {edge.kind === 'traffic' && visible && (
                    <>
                      <circle className="v2-net-edge__particle" r="3">
                        <animateMotion dur="2.8s" path={d} repeatCount="indefinite" />
                      </circle>
                      <circle className="v2-net-edge__particle" r="2.2">
                        <animateMotion begin="1.4s" dur="2.8s" path={d} repeatCount="indefinite" />
                      </circle>
                    </>
                  )}
                  {edge.label && showEdgeLabels && visible && (
                    <g className="v2-net-edge__label" transform={`translate(${lx}, ${ly})`}>
                      {/* 실제 엔드포인트/마운트 라이브 상태가 아니라, 연결된 두 노드의 심각도로 추정한 상태다 */}
                      <title>{`${edge.label} · ${severity === 'ok' ? '정상' : '확인 필요'} (연결 노드 상태 기반 추정)`}</title>
                      <rect x="-23" y="-10" width="46" height="20" rx="10" />
                      <text textAnchor="middle" dominantBaseline="central" dy="0.5">
                        {edge.label}
                      </text>
                      {severity !== 'ok' && <circle className="v2-net-edge__label-dot" cx="19" cy="-6" r="3" />}
                    </g>
                  )}
                </g>
              );
            })}
          </g>

          {/* 노드 */}
          <g className="v2-net__nodes">
            {(Object.keys(layout) as TopologyNodeKey[]).map((key) => {
              const box = layout[key];
              const model = nodeModel(key);
              const interactive = Boolean(onSelectNode);
              const dimmed = affectedOnly && model.severity === 'ok';
              const selected = selectedNode === key;
              return (
                <g
                  className={`v2-net-node is-${model.severity}${selected ? ' is-selected' : ''}${dimmed ? ' is-dimmed' : ''}${key === 'pods' ? ' is-focal' : ''}`}
                  key={key}
                  transform={`translate(${box.x}, ${box.y})`}
                >
                  {model.severity !== 'ok' && (
                    <circle
                      className="v2-net-node__aura"
                      cx={box.w / 2}
                      cy={box.h / 2}
                      fill="url(#v2net-glow)"
                      r={box.w * 0.62}
                    />
                  )}
                  <rect className="v2-net-node__box" height={box.h} rx="15" width={box.w} />
                  <foreignObject height={box.h} width={box.w} x="0" y="0">
                    <div
                      className="v2-net-node__body"
                      onClick={interactive ? () => onSelectNode?.(key) : undefined}
                      onKeyDown={
                        interactive
                          ? (event) => {
                              if (event.key === 'Enter' || event.key === ' ') {
                                event.preventDefault();
                                onSelectNode?.(key);
                              }
                            }
                          : undefined
                      }
                      role={interactive ? 'button' : undefined}
                      tabIndex={interactive ? 0 : undefined}
                    >
                      <span className="v2-net-node__icon">{nodeIcons[key]}</span>
                      <span className="v2-net-node__text">
                        <strong>{model.label}</strong>
                        <small>{model.detail}</small>
                      </span>
                      <span className="v2-net-node__pulse" aria-hidden="true" />
                    </div>
                  </foreignObject>
                </g>
              );
            })}
          </g>
        </svg>
      </div>

      <div className="v2-net__legend">
        <span>
          <i className="is-traffic" /> 트래픽/선택
        </span>
        <span>
          <i className="is-owner" /> 소유 관계
        </span>
        <span>
          <i className="is-runtime" /> 스케줄/마운트
        </span>
        <span>
          <i className="is-warn" /> 이상 신호
        </span>
        <em>
          영향 후보 {issueCount}건 · 활성 파드 이슈 후보 {podSummary.issueCandidates}건
        </em>
      </div>
    </div>
  );
};
