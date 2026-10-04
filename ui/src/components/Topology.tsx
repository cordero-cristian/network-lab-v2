import { useState } from "react";
import { Link } from "react-router-dom";
import type { TopologyGraph, TopologyNode } from "../api/types";
import { titleCase } from "../format";
import { AvailabilityBanner, EmptyState, UnavailableState } from "./AsyncSection";
import { statusTone, Status } from "./Status";

interface Position { x: number; y: number }

function positions(nodes: TopologyNode[]): Map<string, Position> {
  const result = new Map<string, Position>();
  const sorted = [...nodes].sort((a, b) => `${a.role ?? "z"}:${a.label}`.localeCompare(`${b.role ?? "z"}:${b.label}`));
  sorted.forEach((node, index) => {
    const columns = Math.min(3, sorted.length);
    result.set(node.id, { x: 24 + (index % columns) * (712 / columns), y: 28 + Math.floor(index / columns) * 150 });
  });
  return result;
}

export function Topology({ graph }: { graph: TopologyGraph }) {
  const [selectedId, setSelectedId] = useState<string | null>(graph.nodes[0]?.id ?? null);
  const selected = graph.nodes.find((node) => node.id === selectedId) ?? null;
  const placed = positions(graph.nodes);
  const rows = Math.max(1, Math.ceil(graph.nodes.length / 3));
  const height = rows * 150 + 30;

  if (!graph.nodes.length) return <><AvailabilityBanner availability={graph.availability} />{graph.availability.status === "unavailable" || graph.availability.status === "unknown" ? <UnavailableState source="Nautobot" message={graph.availability.message} /> : <EmptyState source="Nautobot">No current lab devices were returned, so topology cannot be drawn.</EmptyState>}</>;
  return (
    <div className="topology-wrap">
      <AvailabilityBanner availability={graph.availability} />
      <svg className="topology" viewBox={`0 0 760 ${height}`} role="group" aria-labelledby="topology-title topology-description">
        <title id="topology-title">Current lab topology</title>
        <desc id="topology-description">Selectable device plates with authoritative physical or logical BGP links.</desc>
        <g aria-hidden="true">
          {graph.links.map((link) => {
            const source = placed.get(link.source_device); const target = placed.get(link.target_device);
            if (!source || !target) return null;
            const kind = link.kind === "bgp" ? "Logical BGP" : "Physical";
            return <line key={link.id} x1={source.x + 108} y1={source.y + 53} x2={target.x + 108} y2={target.y + 53} className={`topology__link topology__link--${link.kind}`}><title>{`${kind} link: ${link.source_device} to ${link.target_device}; status ${link.status}`}</title></line>;
          })}
        </g>
        <g aria-label="Devices">
          {graph.nodes.map((node) => {
            const point = placed.get(node.id)!;
            return (
              <Link key={node.id} to={`/devices/${encodeURIComponent(node.id)}`} aria-label={`Open ${node.label}, status ${node.status}`} onFocus={() => setSelectedId(node.id)} onMouseEnter={() => setSelectedId(node.id)}>
                <g className={`topology__node topology__node--${statusTone(node.status)}${selected?.id === node.id ? " is-selected" : ""}`} transform={`translate(${point.x} ${point.y})`}>
                  <title>{`${node.label}, ${node.role ?? "role unknown"}, ${node.platform ?? "platform unknown"}, ${node.status}`}</title>
                  <rect className="topology__plate" width="216" height="106" rx="5" />
                  <rect className="topology__stripe" width="6" height="106" rx="3" />
                  <text className="topology__role" x="20" y="23">{(node.role ?? "ROLE UNKNOWN").toUpperCase()}</text>
                  <text className="topology__status" x="202" y="23" textAnchor="end">{node.status === "healthy" ? "+" : node.status === "unknown" ? "?" : "!"} {titleCase(node.status)}</text>
                  <text className="topology__name" x="20" y="55">{node.label}</text>
                  <text className="topology__platform" x="20" y="82">{node.platform ?? "Platform unavailable"}</text>
                </g>
              </Link>
            );
          })}
        </g>
      </svg>
      <div className="topology__legend" aria-label="Topology legend"><span><i />Physical endpoint</span><span><i className="is-logical" />Logical BGP intent</span><span>Link state is not inferred</span></div>
      {!graph.links.length && <div className="topology__incomplete" role="status"><strong>Relationship data incomplete</strong><span>Known devices are shown, but Nautobot returned no authoritative physical or logical links.</span></div>}
      {selected && <div className="selection-strip"><div><span className="eyebrow">Selected device</span><strong className="mono" title={selected.label}>{selected.label}</strong></div><Status value={selected.status} compact /><span className="muted">Source: {selected.status_source ?? "not available"}</span><Link className="text-link" to={`/devices/${encodeURIComponent(selected.id)}`}>Open device detail <span aria-hidden="true">→</span></Link></div>}
    </div>
  );
}
