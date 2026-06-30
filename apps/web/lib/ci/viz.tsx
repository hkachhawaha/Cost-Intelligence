// SVG chart primitives ported from the dashboard prototype (ring, donut, horizontal + vertical
// bars). Pure presentational components.
import { fmtK } from "./compute";

export function Ring({ p, size = 86, stroke = 10, color = "var(--purple)" }: {
  p: number; size?: number; stroke?: number; color?: string;
}) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const off = c * (1 - Math.min(p, 100) / 100);
  const m = size / 2;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <circle cx={m} cy={m} r={r} fill="none" stroke="#eee7f7" strokeWidth={stroke} />
      <circle cx={m} cy={m} r={r} fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round"
        strokeDasharray={c} strokeDashoffset={off} transform={`rotate(-90 ${m} ${m})`} />
      <text x="50%" y="50%" textAnchor="middle" dy="0.35em" fontSize={size * 0.25} fontWeight={800} fill="var(--ink)">
        {Math.round(p)}%
      </text>
    </svg>
  );
}

export interface Seg { label: string; value: number; color: string }

export function Donut({ segs, size = 160, stroke = 30 }: { segs: Seg[]; size?: number; stroke?: number }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const m = size / 2;
  const total = segs.reduce((t, s) => t + s.value, 0) || 1;
  let acc = 0;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <circle cx={m} cy={m} r={r} fill="none" stroke="#f1eef9" strokeWidth={stroke} />
      {segs.map((s, i) => {
        const dash = c * (s.value / total);
        const el = (
          <circle key={i} cx={m} cy={m} r={r} fill="none" stroke={s.color} strokeWidth={stroke}
            strokeDasharray={`${dash} ${c - dash}`} strokeDashoffset={-acc} transform={`rotate(-90 ${m} ${m})`} />
        );
        acc += dash;
        return el;
      })}
    </svg>
  );
}

export const CATCOL = ["#6d28d9", "#8b5cf6", "#a78bfa", "#e07b1a", "#2563eb", "#0f9d58", "#d946ef", "#c4b5fd"];

export function Bars({ rows, cls }: { rows: [string, number][]; cls?: string }) {
  const mx = Math.max(...rows.map((r) => r[1]), 1);
  return (
    <>
      {rows.map(([n, v]) => (
        <div className="bar" key={n}>
          <div className="nm" title={n}>{n}</div>
          <div className="tk"><div className={`fl ${cls || ""}`} style={{ width: `${Math.max(4, (v / mx) * 100)}%` }} /></div>
          <div className="vl">{fmtK(v)}</div>
        </div>
      ))}
    </>
  );
}

export function VBars({ rows, h = 130 }: { rows: [string, number][]; h?: number }) {
  const mx = Math.max(...rows.map((r) => r[1]), 1);
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 9, height: h, paddingTop: 14 }}>
      {rows.map(([n, v]) => (
        <div key={n} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-end", height: "100%" }}>
          <div style={{ fontSize: 9.5, color: "var(--muted)", marginBottom: 3 }}>{fmtK(v)}</div>
          <div style={{ width: "78%", background: "linear-gradient(180deg,#a78bfa,#6d28d9)", borderRadius: "6px 6px 0 0", height: `${Math.max(3, (v / mx) * 100)}%` }} />
          <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 6 }}>{n}</div>
        </div>
      ))}
    </div>
  );
}
