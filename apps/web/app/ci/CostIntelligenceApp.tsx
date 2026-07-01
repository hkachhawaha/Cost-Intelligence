"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { ApiError, apiClient } from "@/lib/api";
import {
  ACT_CATEGORIES,
  actIcon,
  byContract,
  canonVendor,
  catOf,
  cById,
  confCls,
  confLbl,
  entityOf,
  fmt,
  fmtK,
  genDoc,
  l1Of,
  nirvanaAnswer,
  oppAct,
  oppIcon,
  pct,
  stCls,
  stLbl,
  sum,
} from "@/lib/ci/compute";
import type { CiContract, CiOpportunity, CiSnapshot, CiSpend } from "@/lib/ci/types";
import { Bars, CATCOL, Donut, Ring, type Seg, VBars } from "@/lib/ci/viz";

import { SettingsView } from "./SettingsView";

const NAV: [string, [string, string, string][]][] = [
  ["Overview", [["home", "Home", "🏠"], ["opps", "Opportunities", "💡"]]],
  ["Analyze", [["analyze", "Analyze", "🔎"], ["spend", "Spend", "💸"], ["contracts", "Contracts", "📑"], ["vendors", "Vendors", "🏢"], ["indexation", "Indexation", "∿"]]],
  ["Act", [["act", "Act", "✅"], ["recovery", "Margin Recovery", "💰"], ["renewals", "Renewals", "⏰"], ["commitments", "Commitments", "🎯"], ["commitcheck", "Commitment Check", "🛡️"]]],
  ["Intelligence", [["intelligence", "Intelligence", "✦"], ["portfolio", "Portfolio", "🗂️"]]],
  ["System", [["quality", "Data Quality", "◑"], ["settings", "Settings", "⚙️"]]],
];
const TITLES: Record<string, [string, string]> = {
  home: ["Here's your cost intelligence", "A quick read on where money is leaking and what to do about it."],
  opps: ["Opportunities", "Every chance to recover or save, ranked by impact."],
  analyze: ["Analyze", "AI-generated cost insights — trends, utilisation, variance and supplier performance."],
  spend: ["Spend", "Where your money is going — and how much is under contract."],
  contracts: ["Contracts", "Your agreements, utilisation and renewals at a glance."],
  vendors: ["Vendors", "Supplier spend, concentration, performance, risk and opportunities."],
  indexation: ["Indexation & Exposure", "Index / commitment-linked contracts and the cost risk if indices rise."],
  act: ["Act", "Recommended actions from NirvanaI — go straight from insight to action."],
  recovery: ["Margin Recovery", "Recoverable cash — discrepancies, leakage and missed value, packaged to challenge."],
  renewals: ["Renewals", "What is coming up — act before auto-renewals lock in."],
  commitments: ["Commitments", "Track contractual commitments, consumption, utilisation and variance."],
  commitcheck: ["Commitment Check", "Stress-test a proposed commitment before you sign it."],
  intelligence: ["Intelligence", "AI findings, anomalies, opportunities and recommendations — powered by NirvanaI."],
  portfolio: ["Portfolio", "Your whole cost portfolio across suppliers, contracts, invoices and spend."],
  quality: ["Data Quality", "Match confidence and what still needs a human eye."],
  settings: ["Settings", "Connect your Google Sheet and tune the assumptions behind every number."],
};

const H = (s: string) => <span dangerouslySetInnerHTML={{ __html: s }} />;

// NirvanAI Q&A → memory-grounded backend; local deterministic answer is the offline fallback.
async function askNirvana(snap: CiSnapshot, q: string): Promise<string> {
  try {
    const r = await apiClient.post<{ answer: string }>("/ci/nirvana/ask", { question: q });
    return r.answer || nirvanaAnswer(snap, q);
  } catch {
    return nirvanaAnswer(snap, q);
  }
}

type Chat = { open: boolean; log: { q: string; a: string }[] };
type EnrichedOpp = CiOpportunity & { icon: string; act: string };

export function CostIntelligenceApp({
  initialSnapshot,
  initialTab,
}: { initialSnapshot?: CiSnapshot | null; initialTab?: string } = {}) {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [snap, setSnap] = useState<CiSnapshot | null>(initialSnapshot ?? null);
  const [loading, setLoading] = useState(!initialSnapshot);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [missing, setMissing] = useState(false);
  const [tab, setTab] = useState(searchParams.get("tab") ?? initialTab ?? "home");
  const [statuses, setStatuses] = useState<Record<string, string>>({});
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [oppFilter, setOppFilter] = useState("all");
  const [spendFilter] = useState({ q: "", cat: "", match: "" });
  const [indexMove, setIndexMove] = useState(5);
  const [contractView, setContractView] = useState<"cards" | "table">("cards");
  const [contractDetail, setContractDetail] = useState<string | null>(searchParams.get("contractId") ?? null);
  const [ccl, setCcl] = useState({ value: 500000, term: 3, indexShare: 40, tolerance: 25000 });
  const [chat, setChat] = useState<Chat>({ open: false, log: [] });
  const [isWakingUp, setIsWakingUp] = useState(false);

  useEffect(() => {
    const handlePopState = () => {
      const params = new URLSearchParams(window.location.search);
      const t = params.get("tab") || "home";
      const cid = params.get("contractId");
      setTab(t);
      setContractDetail(cid);
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const goTab = (t: string) => {
    setTab(t);
    setContractDetail(null);
    window.history.pushState(null, "", "/ci?tab=" + t);
  };

  const viewContract = (id: string) => {
    setContractDetail(id);
    window.history.pushState(null, "", `/ci?tab=contracts&contractId=${id}`);
  };

  const backToContracts = () => {
    setContractDetail(null);
    window.history.pushState(null, "", `/ci?tab=contracts`);
  };

  async function load() {
    setLoading(true);
    setLoadError(null);
    setIsWakingUp(false);

    const wakeUpTimer = setTimeout(() => {
      setIsWakingUp(true);
    }, 3000);

    const maxRetries = 5;
    let delay = 2000;

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        const s = await apiClient.get<CiSnapshot>("/ci/snapshot");
        setSnap(s);
        setMissing(false);
        clearTimeout(wakeUpTimer);
        setIsWakingUp(false);
        setLoading(false);
        return;
      } catch (e) {
        console.warn(`[CostIntelligence] Snapshot fetch attempt ${attempt} failed:`, e);
        const is404 = e instanceof ApiError && e.status === 404;
        if (is404) {
          setMissing(true);
          clearTimeout(wakeUpTimer);
          setIsWakingUp(false);
          setLoading(false);
          return;
        }

        if (attempt === maxRetries) {
          const msg = e instanceof ApiError ? e.detail : (e instanceof Error ? e.message : "Unknown error");
          setLoadError(msg);
          clearTimeout(wakeUpTimer);
          setIsWakingUp(false);
          setLoading(false);
        } else {
          await new Promise((resolve) => setTimeout(resolve, delay));
          delay = Math.min(delay * 1.5, 10000);
        }
      }
    }
  }
  useEffect(() => {
    if (!initialSnapshot) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const opps = useMemo<EnrichedOpp[]>(
    () => (snap ? snap.opportunities.map((o) => ({ ...o, status: statuses[o.id] || o.status, icon: oppIcon(o.type), act: oppAct(o.type) })) : []),
    [snap, statuses],
  );

  if (loading) {
    return (
      <div className="ci-loading">
        <div>Loading Cost Intelligence…</div>
        {isWakingUp && (
          <div className="ci-loading-subtext" style={{ marginTop: 12 }}>
            ⚠️ The backend is waking up from free-tier sleep on Render.
            <br />
            Please wait, this can take up to 30-40 seconds...
          </div>
        )}
      </div>
    );
  }
  if (loadError) {
    return (
      <div className="ci-shell"><div className="app">
        <Sidebar tab={tab} setTab={goTab} counts={{}} onAsk={() => setChat({ ...chat, open: true })} />
        <main className="main">
          <div className="pt">Unable to load data</div>
          <div className="psub" style={{ color: "var(--red, #e53e3e)", marginBottom: 16 }}>{loadError}</div>
          <button className="btn p" onClick={load}>Retry</button>
        </main>
      </div></div>
    );
  }
  if (missing || !snap) {
    return (
      <div className="ci-shell"><div className="app">
        <Sidebar tab={tab} setTab={goTab} counts={{}} onAsk={() => setChat({ ...chat, open: true })} />
        <main className="main">
          <div className="pt">Connect your data</div>
          <div className="psub">No spreadsheet is connected yet — add your Google Sheet to begin.</div>
          <SettingsView onChanged={load} />
        </main>
      </div></div>
    );
  }

  const s = snap;
  const k = s.kpis;
  const setStatus = (id: string, st: string) => setStatuses((m) => ({ ...m, [id]: st }));
  const toggle = (id: string) => setExpanded((m) => ({ ...m, [id]: !m[id] }));
  const recovered = opps.filter((o) => o.status === "recovered").reduce((t, o) => t + o.impact, 0);
  const oppByContract = (cid: string) => opps.filter((o) => o.contractId === cid).reduce((t, o) => t + o.impact, 0);

  function draftDoc(vendor: string, ty: "challenge" | "reneg") {
    const docType = ty === "challenge" ? "Supplier challenge letter" : "Renegotiation email";
    const a = "<pre>" + genDoc(s, docType, vendor).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c] || c)) + "</pre>";
    setChat((c) => ({ open: true, log: [...c.log, { q: (ty === "challenge" ? "Draft a supplier challenge letter for " : "Draft a renegotiation note for ") + vendor, a }] }));
  }
  async function ask(q: string) {
    const a = await askNirvana(s, q);
    setChat((c) => ({ open: true, log: [...c.log, { q, a }] }));
  }

  const OppCard = (o: EnrichedOpp) => {
    const cf = o.contractId ? cById(s, o.contractId) : null;
    const isRec = o.bucket === "recovery";
    const open = !!expanded[o.id];
    const ev = (o.evidence || []).slice(0, 6);
    return (
      <div className={`opp ${open ? "open" : ""}`} key={o.id}>
        <div className="row1">
          <div className={`icon ${isRec ? "ic-rec" : "ic-sav"}`}>{o.icon}</div>
          <div style={{ minWidth: 0 }}><div className="ttl">{o.type}</div><div className="vend">{cf ? cf.vendor : o.subject || ""}</div></div>
          <div className="amt"><div className="n">{fmtK(o.impact)}</div><div className="k">{isRec ? "recover now" : "per year"}</div></div>
        </div>
        <div className="desc">{H(o.rationale)}</div>
        <div className="foot">
          <span className={`pill ${isRec ? "p-rec" : "p-sav"}`}>{isRec ? "Recovery" : "Savings"}</span>
          <span className={`conf ${confCls(o.conf)}`}>{confLbl(o.conf)} confidence</span>
          <span className={`st ${stCls(o.status)}`}>{stLbl(o.status)}</span>
          <span className="more" style={{ marginLeft: "auto", color: "var(--purple)", fontSize: 12.5, fontWeight: 600, cursor: "pointer" }} onClick={() => toggle(o.id)}>{open ? "Hide ‹" : "Details ›"}</span>
        </div>
        {open && (
          <div className="detail" style={{ display: "block" }}>
            <div style={{ fontSize: 12.5, color: "#4a4660", marginBottom: 4 }}><b>How we got the number</b></div>
            <div className="formula">{H(o.formula)}</div>
            <div style={{ fontSize: 12.5, color: "#4a4660", margin: "8px 0 2px" }}><b>Recommended action.</b> {o.action}</div>
            {ev.length > 0 && (
              <>
                <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 8, textTransform: "uppercase", letterSpacing: ".4px" }}>Evidence ({(o.evidence || []).length})</div>
                {ev.map((sp: CiSpend) => (
                  <div className="vrow" style={{ padding: "7px 0" }} key={sp.id}>
                    <div style={{ fontSize: 12, color: "var(--muted)", width: 58 }}>{sp.id}</div>
                    <div style={{ flex: 1, fontSize: 12.5 }}>{sp.vendor}</div>
                    <div style={{ fontSize: 12.5, fontWeight: 700 }}>{fmt(sp.amount)}</div>
                    <div style={{ fontSize: 11, color: "var(--muted)", width: 78, textAlign: "right" }}>{sp.spendDate}</div>
                  </div>
                ))}
              </>
            )}
            <div className="linkrow">
              <button className={`btn sm ${o.status === "in_progress" ? "p" : ""}`} onClick={() => setStatus(o.id, "in_progress")}>Mark in progress</button>
              <button className={`btn sm ${o.status === "recovered" ? "g" : ""}`} onClick={() => setStatus(o.id, "recovered")}>Mark done</button>
              {cf && <button className="btn sm" onClick={() => draftDoc(cf.vendor, isRec ? "challenge" : "reneg")}>✦ Draft with NirvanaI</button>}
            </div>
          </div>
        )}
      </div>
    );
  };

  // ── views ─────────────────────────────────────────────────────────────────────
  const views: Record<string, () => JSX.Element> = {
    home: () => {
      const byL1: Record<string, number> = {};
      s.spend.forEach((sp) => (byL1[l1Of(catOf(s, sp))] = (byL1[l1Of(catOf(s, sp))] || 0) + sp.amount));
      const segs: Seg[] = Object.entries(byL1).sort((a, b) => b[1] - a[1]).map(([label, value], i) => ({ label, value, color: CATCOL[i % CATCOL.length] }));
      const alerts: [string, string, string, string][] = [];
      opps.filter((o) => o.type === "Silent auto-renewal").slice(0, 1).forEach((o) => alerts.push(["a", "⏰", `${o.subject} auto-renews soon`, `${fmt(o.impact)} uplift is negotiable — act before the window closes.`]));
      opps.filter((o) => o.type === "Duplicate invoice").slice(0, 1).forEach((o) => alerts.push(["b", "📑", `Possible double payment to ${o.subject}`, `${fmt(o.impact)} looks recoverable.`]));
      opps.filter((o) => o.type === "Spend after expiry").slice(0, 1).forEach((o) => alerts.push(["r", "⌛", `${o.subject} billing after expiry`, `${fmt(o.impact)} spent after the contract ended.`]));
      return (
        <>
          <div className="grid g2" style={{ gridTemplateColumns: "1.5fr 1fr", alignItems: "stretch" }}>
            <div className="hero">
              <div className="lbl">We found money across your spend</div>
              <div className="big">{fmtK(k.identified)}</div>
              <div className="sub">{pct(k.identified, k.total).toFixed(1)}% of your {fmtK(k.total)} in spend — provable against your own contracts.</div>
              <div className="chips">
                <div className="hchip">Recover now<b>{fmtK(k.recoverable)}</b></div>
                <div className="hchip">Save each year<b>{fmtK(k.savings)}</b></div>
                <div className="hchip">Recovered<b>{fmtK(recovered)}</b></div>
              </div>
              <button className="cta" onClick={() => goTab("opps")}>Review top actions →</button>
            </div>
            <div className="card">
              <div className="metric"><div><Ring p={k.spendUnderMgmtPct} size={92} stroke={11} /></div>
                <div><div className="mt">Spend under management</div><div className="mv">{fmtK(k.matched)}</div><div className="ms">of {fmtK(k.total)} on contract</div></div></div>
              <div style={{ borderTop: "1px solid var(--line)", margin: "14px 0" }} />
              <div className="metric"><div className="icon ic-rec" style={{ width: 46, height: 46, fontSize: 21, borderRadius: 14 }}>🧭</div>
                <div><div className="mt">Off-contract exposure</div><div className="mv">{fmtK(k.maverick)}</div><div className="ms">spend with no contract</div></div></div>
            </div>
          </div>
          <div className="sectlbl">🎯 Top things to act on <span className="more" onClick={() => goTab("act")}>Open Act ›</span></div>
          <div className="grid g2">{opps.slice(0, 4).map((o) => OppCard(o))}</div>
          <div className="grid g2" style={{ gridTemplateColumns: "1fr 1fr", marginTop: 18 }}>
            <div className="card"><div className="sectlbl" style={{ margin: "0 0 6px" }}>💸 Where your money goes</div>
              <div style={{ display: "flex", alignItems: "center", gap: 20, marginTop: 8 }}><div><Donut segs={segs} /></div>
                <div style={{ flex: 1 }}>{segs.map((sg) => (<div key={sg.label} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, margin: "7px 0" }}><span className="dot" style={{ background: sg.color }} />{sg.label}<b style={{ marginLeft: "auto" }}>{fmtK(sg.value)}</b></div>))}</div></div></div>
            <div className="card"><div className="sectlbl" style={{ margin: "0 0 10px" }}>🔔 Needs your attention</div>
              {alerts.length ? alerts.map((a, i) => (<div className={`alert a-${a[0]}`} style={{ marginBottom: 10 }} key={i}><div className="ai">{a[1]}</div><div><div className="at">{a[2]}</div><div style={{ color: "var(--muted)", fontSize: 12.5 }}>{a[3]}</div></div></div>)) : <div className="empty">All clear.</div>}</div>
          </div>
        </>
      );
    },

    opps: () => {
      const chips: [string, string][] = [["all", "All"], ["recovery", "Recover now"], ["savings", "Future savings"], ["open", "Still open"]];
      const filt = opps.filter((o) => oppFilter === "all" ? true : oppFilter === "open" ? o.status !== "recovered" : o.bucket === oppFilter);
      return (
        <>
          <div className="chips">
            {chips.map(([key, label]) => <div className={`fchip ${oppFilter === key ? "on" : ""}`} key={key} onClick={() => setOppFilter(key)}>{label}</div>)}
            <div style={{ marginLeft: "auto", alignSelf: "center", fontSize: 13, color: "var(--muted)" }}>{filt.length} opportunities · {fmt(filt.reduce((t, o) => t + o.impact, 0))}</div>
          </div>
          <div className="grid g2">{filt.length ? filt.map((o) => OppCard(o)) : <div className="empty">Nothing here — try another filter.</div>}</div>
        </>
      );
    },

    analyze: () => {
      const byMonth: Record<string, number> = {};
      s.spend.forEach((sp) => { const m = (sp.spendDate || "").slice(0, 7); if (m) byMonth[m] = (byMonth[m] || 0) + sp.amount; });
      const months: [string, number][] = Object.keys(byMonth).sort().map((m) => [m.slice(5), byMonth[m]]);
      const utilC = s.contracts.filter((c) => c.status !== "Expired").map((c) => ({ c, u: pct(sum(byContract(s, c.id)), c.yearlyCommit || c.acv || 1) }));
      const avgUtil = utilC.length ? utilC.reduce((t, x) => t + x.u, 0) / utilC.length : 0;
      const variance = s.contracts.map((c) => ({ v: c.vendor, d: sum(byContract(s, c.id)) - (c.acv || 0) })).filter((x) => Math.abs(x.d) > 1000).sort((a, b) => Math.abs(b.d) - Math.abs(a.d)).slice(0, 6);
      const byVen: Record<string, number> = {};
      s.spend.forEach((sp) => (byVen[canonVendor(s, sp)] = (byVen[canonVendor(s, sp)] || 0) + sp.amount));
      const topVen = Object.entries(byVen).sort((a, b) => b[1] - a[1]) as [string, number][];
      const top3 = topVen.slice(0, 3).reduce((t, x) => t + x[1], 0);
      const byCat: Record<string, number> = {};
      s.spend.forEach((sp) => (byCat[catOf(s, sp)] = (byCat[catOf(s, sp)] || 0) + sp.amount));
      const topCat = Object.entries(byCat).sort((a, b) => b[1] - a[1])[0] || ["—", 0];
      const renewalExp = opps.filter((o) => o.type === "Silent auto-renewal" || o.type === "Uplift creep").reduce((a, o) => a + o.impact, 0);
      const ins: [string, string][] = [
        ["💸", `${topCat[0]} is your biggest category at ${fmt(topCat[1])} (${pct(topCat[1], k.total).toFixed(0)}% of spend).`],
        ["🧭", `${fmt(k.maverick)} (${pct(k.maverick, k.total).toFixed(0)}%) of spend is off-contract — the single largest leakage to close.`],
        ["📉", `Average contract utilisation is ${avgUtil.toFixed(0)}%; ${utilC.filter((x) => x.u < 85).length} contracts are under-used and ${utilC.filter((x) => x.u > 100).length} are over.`],
        ["🏢", `Your top 3 suppliers are ${pct(top3, k.total).toFixed(0)}% of spend — concentration to watch when negotiating.`],
        ["📈", `Renewal exposure is ${fmt(renewalExp)} across the contract book.`],
      ];
      return (
        <>
          <div className="card" style={{ marginBottom: 16 }}><div className="sectlbl" style={{ margin: "0 0 10px" }}>✦ AI-generated insights</div>
            {ins.map((x, i) => <div className="find" key={i}><div className="fi">{x[0]}</div><div style={{ alignSelf: "center" }}><div className="fd">{x[1]}</div></div></div>)}</div>
          <div className="grid g2">
            <div className="card"><div className="sectlbl" style={{ margin: "0 0 4px" }}>📈 Spend trend</div><div className="psub" style={{ margin: 0 }}>Monthly spend across the period.</div><VBars rows={months} /></div>
            <div className="card"><div className="sectlbl" style={{ margin: "0 0 10px" }}>🏢 Supplier performance</div><div className="psub" style={{ margin: "0 0 6px" }}>Top suppliers by spend.</div><Bars rows={topVen.slice(0, 6)} /></div>
          </div>
          <div className="grid g2" style={{ marginTop: 16 }}>
            <div className="card"><div className="sectlbl" style={{ margin: "0 0 10px" }}>📊 Contract utilisation</div>
              {utilC.sort((a, b) => a.u - b.u).slice(0, 7).map((x) => (<div className="bar" key={x.c.id}><div className="nm">{x.c.vendor}</div><div className="tk"><div className={`fl ${x.u > 100 ? "r" : x.u >= 85 ? "g" : "a"}`} style={{ width: `${Math.min(100, x.u)}%` }} /></div><div className="vl">{x.u.toFixed(0)}%</div></div>))}</div>
            <div className="card"><div className="sectlbl" style={{ margin: "0 0 10px" }}>⚖️ Variance vs contract</div><div className="psub" style={{ margin: "0 0 6px" }}>Actual over (red) / under (green) the annual value.</div>
              {variance.map((x) => { const mxv = Math.max(...variance.map((v) => Math.abs(v.d)), 1); return (<div className="bar" key={x.v}><div className="nm">{x.v}</div><div className="tk"><div className={`fl ${x.d > 0 ? "r" : "g"}`} style={{ width: `${Math.min(100, Math.abs(x.d) / mxv * 100)}%` }} /></div><div className="vl" style={{ color: x.d > 0 ? "var(--red)" : "var(--green)" }}>{x.d > 0 ? "+" : ""}{fmtK(x.d)}</div></div>); })}</div>
          </div>
        </>
      );
    },

    spend: () => {
      const total = k.total, matched = k.matched, mav = k.maverick;
      const byCat: Record<string, number> = {}, byVen: Record<string, number> = {};
      s.spend.forEach((sp) => { byCat[catOf(s, sp)] = (byCat[catOf(s, sp)] || 0) + sp.amount; byVen[canonVendor(s, sp)] = (byVen[canonVendor(s, sp)] || 0) + sp.amount; });
      return (
        <>
          <div className="grid g3">
            <div className="card"><div className="metric"><div><Ring p={pct(matched, total)} size={90} stroke={11} color="var(--green)" /></div><div><div className="mt">Under contract</div><div className="mv">{fmtK(matched)}</div><div className="ms">well governed</div></div></div></div>
            <div className="card"><div className="metric"><div className="icon ic-rec" style={{ width: 52, height: 52, fontSize: 23, borderRadius: 15 }}>🧭</div><div><div className="mt">Off-contract</div><div className="mv">{fmtK(mav)}</div><div className="ms">{pct(mav, total).toFixed(0)}% maverick</div></div></div></div>
            <div className="card"><div className="metric"><div className="icon ic-sav" style={{ width: 52, height: 52, fontSize: 23, borderRadius: 15 }}>💸</div><div><div className="mt">Total spend</div><div className="mv">{fmtK(total)}</div><div className="ms">{s.spend.length} transactions</div></div></div></div>
          </div>
          <div className="grid g2" style={{ marginTop: 16 }}>
            <div className="card"><div className="sectlbl" style={{ margin: "0 0 10px" }}>By category</div><Bars rows={Object.entries(byCat).sort((a, b) => b[1] - a[1]) as [string, number][]} /></div>
            <div className="card"><div className="sectlbl" style={{ margin: "0 0 10px" }}>Top vendors</div>
              {(Object.entries(byVen).sort((a, b) => b[1] - a[1]).slice(0, 6) as [string, number][]).map(([v, a]) => (<div className="vrow" key={v}><div className="av">{v.slice(0, 1)}</div><div style={{ flex: 1 }}><div style={{ fontWeight: 650, fontSize: 13.5 }}>{v}</div><div style={{ fontSize: 12, color: "var(--muted)" }}>{s.contracts.find((c) => c.vendor === v) ? "on contract" : "no contract"}</div></div><div style={{ fontWeight: 800 }}>{fmtK(a)}</div></div>))}</div>
          </div>
        </>
      );
    },

    contracts: () => {
      if (contractDetail) return contractDetailView(contractDetail);
      const toggleEl = (
        <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 16 }}>
          <div className="vtoggle"><button className={contractView === "cards" ? "on" : ""} onClick={() => setContractView("cards")}>▦ Cards</button><button className={contractView === "table" ? "on" : ""} onClick={() => setContractView("table")}>≣ Table</button></div>
          <span style={{ fontSize: 13, color: "var(--muted)" }}>{s.contracts.length} contracts · {fmtK(sum(s.spend.filter((sp) => sp.resolvedContractId)))} under management</span>
        </div>
      );
      const badge = (c: CiContract) => c.status === "Expired" ? <span className="badge b-exp">Expired</span> : c.autoRenew ? <span className="badge b-auto">Auto-renews</span> : <span className="badge b-opt">Option</span>;
      if (contractView === "table") {
        return (
          <>{toggleEl}
            <div className="card" style={{ padding: "6px 16px" }}><table className="ltable"><thead><tr><th>Contract</th><th>Supplier</th><th>Category</th><th>Entity</th><th style={{ textAlign: "right" }}>ACV</th><th style={{ textAlign: "right" }}>Actual</th><th>Utilisation</th><th>Renewal</th><th>Ends</th><th style={{ textAlign: "right" }}>Opportunity</th><th /></tr></thead>
              <tbody>{s.contracts.map((c) => { const act = sum(byContract(s, c.id)), base = c.yearlyCommit || c.acv || 1, u = pct(act, base); const col = u > 100 ? "var(--red)" : u >= 80 ? "var(--green)" : "var(--amber)"; const op = oppByContract(c.id);
                return (<tr key={c.id} onClick={() => viewContract(c.id)}><td style={{ fontWeight: 600 }}>{c.id}</td><td style={{ fontWeight: 600 }}>{c.vendor}</td><td>{c.category}</td><td>{c.entity}</td><td style={{ textAlign: "right" }}>{fmtK(c.acv || 0)}</td><td style={{ textAlign: "right" }}>{fmtK(act)}</td><td><span className="ut"><i style={{ width: `${Math.min(100, u)}%`, background: col }} /></span>{u.toFixed(0)}%</td><td>{badge(c)}</td><td>{c.end}</td><td style={{ textAlign: "right", fontWeight: 700, color: "var(--purple-d)" }}>{op ? fmtK(op) : "—"}</td><td style={{ color: "var(--purple)", fontWeight: 700 }}>›</td></tr>);
              })}</tbody></table></div>
          </>
        );
      }
      return (
        <>{toggleEl}
          <div className="grid g2">{s.contracts.map((c) => { const act = sum(byContract(s, c.id)), base = c.yearlyCommit || c.acv || 1, u = pct(act, base); const col = u > 100 ? "var(--red)" : u >= 80 ? "var(--green)" : "var(--amber)"; const op = oppByContract(c.id);
            return (<div className="card ccard clickable" key={c.id} onClick={() => viewContract(c.id)}><div><Ring p={Math.min(u, 100)} size={76} stroke={9} color={col} /></div>
              <div style={{ flex: 1, minWidth: 0 }}><div style={{ fontWeight: 750, fontSize: 15 }}>{c.vendor}</div><div style={{ fontSize: 12.5, color: "var(--muted)", margin: "1px 0 8px" }}>{c.category} · {c.entity}</div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>{badge(c)}<span style={{ fontSize: 12.5, color: "#4a4660" }}>ACV {fmtK(c.acv || 0)}</span><span style={{ fontSize: 12.5, color: "var(--muted)" }}>ends {c.end}</span></div>
                {op ? <div style={{ marginTop: 8, fontSize: 12.5, color: "var(--purple-d)", fontWeight: 700 }}>💡 {fmtK(op)} opportunity</div> : null}
                <div style={{ marginTop: 8, color: "var(--purple)", fontSize: 12.5, fontWeight: 650 }}>View details ›</div></div></div>);
          })}</div>
        </>
      );
    },

    vendors: () => {
      const map: Record<string, { vendor: string; spend: number; recs: number; contracts: Set<string>; cat: string; opp: number; matched: number }> = {};
      s.spend.forEach((sp) => { const v = canonVendor(s, sp); const e = (map[v] = map[v] || { vendor: v, spend: 0, recs: 0, contracts: new Set(), cat: catOf(s, sp), opp: 0, matched: 0 }); e.spend += sp.amount; e.recs++; if (sp.resolvedContractId) { e.contracts.add(sp.resolvedContractId); e.matched += sp.amount; } });
      Object.values(map).forEach((v) => v.contracts.forEach((cid) => (v.opp += oppByContract(cid))));
      const rows = Object.values(map).sort((a, b) => b.spend - a.spend);
      const total = rows.reduce((t, v) => t + v.spend, 0);
      const top3 = rows.slice(0, 3).reduce((t, v) => t + v.spend, 0);
      const catVen: Record<string, Set<string>> = {};
      rows.forEach((v) => (catVen[v.cat] = catVen[v.cat] || new Set()).add(v.vendor));
      const consol = Object.entries(catVen).filter(([, x]) => x.size > 1);
      const risk = (v: { contracts: Set<string> }): [string, string] => { if (!v.contracts.size) return ["b-risk", "Off-contract"]; const cs = [...v.contracts].map((cid) => cById(s, cid)); if (cs.some((c) => c?.autoRenew)) return ["b-soon", "Auto-renew"]; if (cs.some((c) => c?.status === "Expired")) return ["b-exp", "Expired"]; return ["b-ok", "Stable"]; };
      return (
        <>
          <div className="grid g3" style={{ marginBottom: 16 }}>
            <div className="kpi"><div className="mt">Suppliers</div><div className="mv">{rows.length}</div><div className="ms">{rows.filter((v) => !v.contracts.size).length} off-contract</div></div>
            <div className="kpi pp"><div className="mt">Top-3 concentration</div><div className="mv">{pct(top3, total).toFixed(0)}%</div><div className="ms">of {fmtK(total)} spend</div></div>
            <div className="kpi"><div className="mt">Consolidation</div><div className="mv">{consol.length}</div><div className="ms">multi-vendor categories</div></div>
          </div>
          {consol.length > 0 && (<div className="card" style={{ marginBottom: 16 }}><div className="sectlbl" style={{ margin: "0 0 8px" }}>🤝 Consolidation opportunities</div>
            {consol.map(([c, x]) => (<div className="vrow" key={c}><div style={{ flex: 1 }}><b>{c}</b> <span style={{ color: "var(--muted)", fontSize: 12.5 }}>— {[...x].join(", ")}</span></div><span className="badge b-opt">{x.size} vendors</span></div>))}</div>)}
          <div className="grid g2">{rows.map((v) => { const [rc, rl] = risk(v); return (<div className="card" style={{ padding: "16px 18px" }} key={v.vendor}>
            <div style={{ display: "flex", alignItems: "center", gap: 13 }}><div className="av" style={{ width: 44, height: 44, fontSize: 17 }}>{v.vendor.slice(0, 1)}</div>
              <div style={{ flex: 1, minWidth: 0 }}><div style={{ fontWeight: 750, fontSize: 14.5 }}>{v.vendor}</div><div style={{ fontSize: 12, color: "var(--muted)" }}>{v.cat} · {v.contracts.size} contract{v.contracts.size !== 1 ? "s" : ""}</div></div>
              <div style={{ textAlign: "right" }}><div style={{ fontWeight: 800, fontSize: 17 }}>{fmtK(v.spend)}</div><span className={`badge ${rc}`}>{rl}</span></div></div>
            <div style={{ display: "flex", gap: 18, marginTop: 12, fontSize: 12.5 }}>
              <div><div style={{ color: "var(--muted)" }}>Concentration</div><b>{pct(v.spend, total).toFixed(1)}%</b></div>
              <div><div style={{ color: "var(--muted)" }}>Match</div><b>{pct(v.matched, v.spend).toFixed(0)}%</b></div>
              <div><div style={{ color: "var(--muted)" }}>Opportunity</div><b style={{ color: "var(--purple-d)" }}>{v.opp ? fmtK(v.opp) : "—"}</b></div></div></div>); })}</div>
        </>
      );
    },

    indexation: () => {
      // Nexus has no explicit index clauses; treat commitment- or auto-renew-linked contracts as
      // exposed to escalation (first-party assumption), exposure = ACV × the assumed move.
      const linked = s.contracts.filter((c) => c.status !== "Expired" && (c.yearlyCommit || c.autoRenew));
      const rows = linked.map((c) => { const iv = c.acv || 0; return { c, iv, exp: (iv * indexMove) / 100, kind: c.autoRenew ? "Auto-renew" : "Commitment" }; }).sort((a, b) => b.exp - a.exp);
      const totIv = rows.reduce((t, r) => t + r.iv, 0), totExp = rows.reduce((t, r) => t + r.exp, 0);
      return (
        <>
          <div className="grid g3" style={{ marginBottom: 16 }}>
            <div className="kpi"><div className="mt">Exposed contracts</div><div className="mv">{linked.length}</div><div className="ms">of {s.contracts.filter((c) => c.status !== "Expired").length} active</div></div>
            <div className="kpi"><div className="mt">Exposed value</div><div className="mv">{fmtK(totIv)}</div><div className="ms">ACV exposed</div></div>
            <div className="kpi pp"><div className="mt">Exposure @ +{indexMove}%</div><div className="mv">{fmtK(totExp)}</div><div className="ms">added annual cost</div></div>
          </div>
          <div className="card"><div className="formrow" style={{ marginTop: 0 }}><label>Assumed escalation move <b style={{ color: "var(--purple)" }}>+{indexMove}%</b></label><input type="range" min={1} max={15} value={indexMove} onChange={(e) => setIndexMove(+e.target.value)} /><span className="psub" style={{ margin: 0 }}>your assumption — no external feed needed</span></div>
            {rows.map((r) => (<div className="vrow" key={r.c.id}><div className="av" style={{ background: "var(--amber-bg)", color: "var(--amber)" }}>∿</div><div style={{ flex: 1 }}><div style={{ fontWeight: 700, fontSize: 13.5 }}>{r.c.vendor} <span className="badge b-soon">{r.kind}</span></div><div style={{ fontSize: 12, color: "var(--muted)" }}>ACV {fmtK(r.c.acv || 0)} · {r.c.category}</div></div><div style={{ textAlign: "right" }}><div style={{ fontWeight: 800 }}>{fmtK(r.exp)}</div><div style={{ fontSize: 11, color: "var(--muted)" }}>exposure</div></div></div>))}</div>
        </>
      );
    },

    act: () => {
      const list = opps.filter((o) => o.status !== "recovered");
      return (
        <>
          <div className="grid g3" style={{ marginBottom: 18 }}>
            <div className="kpi pp"><div className="mt">Actions to take</div><div className="mv">{list.length}</div><div className="ms">worth {fmtK(list.reduce((t, o) => t + o.impact, 0))}</div></div>
            <div className="kpi"><div className="mt">Recover now</div><div className="mv">{fmtK(k.recoverable)}</div><div className="ms">cash back</div></div>
            <div className="kpi gg"><div className="mt">Recovered</div><div className="mv">{fmtK(recovered)}</div><div className="ms">marked done</div></div>
          </div>
          {ACT_CATEGORIES.map((cat) => { const items = list.filter((o) => o.act === cat); if (!items.length) return null;
            return (<div key={cat}><div className="sectlbl">{actIcon(cat)} {cat} <span style={{ marginLeft: "auto", fontSize: 13, color: "var(--muted)", fontWeight: 600 }}>{fmtK(items.reduce((t, o) => t + o.impact, 0))}</span></div>
              <div className="grid g2">{items.map((o) => { const cf = o.contractId ? cById(s, o.contractId) : null; return (<div className="card" style={{ padding: "15px 17px", display: "flex", flexDirection: "column", gap: 9 }} key={o.id}>
                <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}><div className={`icon ${o.bucket === "recovery" ? "ic-rec" : "ic-sav"}`}>{o.icon}</div><div style={{ flex: 1, minWidth: 0 }}><div style={{ fontWeight: 750, fontSize: 14 }}>{o.type}</div><div style={{ fontSize: 12.5, color: "var(--muted)" }}>{cf ? cf.vendor : o.subject || ""}</div></div><div style={{ textAlign: "right" }}><div style={{ fontWeight: 800, fontSize: 18 }}>{fmtK(o.impact)}</div></div></div>
                <div style={{ fontSize: 12.5, color: "#4a4660" }}><b>Do this:</b> {o.action}</div>
                <div className="linkrow">{cf ? <button className="btn sm p" onClick={() => draftDoc(cf.vendor, o.bucket === "recovery" ? "challenge" : "reneg")}>✦ Draft with NirvanaI</button> : <button className="btn sm p" onClick={() => goTab("opps")}>Review in Opportunities</button>}<button className="btn sm" onClick={() => setStatus(o.id, "recovered")}>Mark done</button></div></div>); })}</div></div>);
          })}
          {!list.length && <div className="empty">All actions complete 🎉</div>}
        </>
      );
    },

    recovery: () => {
      const rec = opps.filter((o) => o.bucket === "recovery");
      const tot = rec.reduce((t, o) => t + o.impact, 0), done = rec.filter((o) => o.status === "recovered").reduce((t, o) => t + o.impact, 0);
      const grp: Record<string, { vendor: string; items: EnrichedOpp[]; total: number }> = {};
      rec.forEach((o) => { const v = o.contractId ? cById(s, o.contractId)?.vendor || o.subject || "—" : o.subject || "—"; (grp[v] = grp[v] || { vendor: v, items: [], total: 0 }).items.push(o); grp[v].total += o.impact; });
      return (
        <>
          <div className="grid g3" style={{ marginBottom: 16 }}>
            <div className="kpi pp"><div className="mt">Total recoverable</div><div className="mv">{fmtK(tot)}</div><div className="ms">{rec.length} items</div></div>
            <div className="kpi gg"><div className="mt">Recovered</div><div className="mv">{fmtK(done)}</div><div className="ms">credited</div></div>
            <div className="kpi"><div className="mt">Open recovery</div><div className="mv">{fmtK(tot - done)}</div><div className="ms">to chase</div></div>
          </div>
          {Object.values(grp).sort((a, b) => b.total - a.total).map((g) => (<div className="card" style={{ marginBottom: 14 }} key={g.vendor}>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}><div className="av" style={{ width: 42, height: 42, background: "var(--amber-bg)", color: "var(--amber)" }}>{g.vendor.slice(0, 1)}</div><div style={{ flex: 1 }}><div style={{ fontWeight: 750, fontSize: 15 }}>{g.vendor}</div><div style={{ fontSize: 12.5, color: "var(--muted)" }}>{g.items.length} discrepanc{g.items.length > 1 ? "ies" : "y"} · {fmt(g.total)} recoverable</div></div><button className="btn p" onClick={() => draftDoc(g.vendor, "challenge")}>✦ Draft challenge letter</button></div>
            {g.items.map((o) => (<div className="vrow" key={o.id}><div className="icon ic-rec" style={{ width: 34, height: 34, fontSize: 16, borderRadius: 10 }}>{o.icon}</div><div style={{ flex: 1 }}><div style={{ fontWeight: 650, fontSize: 13 }}>{o.type}</div><div style={{ fontSize: 12, color: "var(--muted)" }}>{o.rationale.replace(/<[^>]+>/g, "").slice(0, 80)}…</div></div><div style={{ fontWeight: 800 }}>{fmt(o.impact)}</div><button className={`btn sm ${o.status === "recovered" ? "g" : ""}`} onClick={() => setStatus(o.id, "recovered")}>{o.status === "recovered" ? "Recovered" : "Mark"}</button></div>))}</div>))}
          {!rec.length && <div className="empty">No recoverable items.</div>}
        </>
      );
    },

    renewals: () => {
      const now = new Date(s.syncedAt);
      const upliftBy: Record<string, number> = {};
      opps.filter((o) => o.type === "Silent auto-renewal" || o.type === "Uplift creep").forEach((o) => { if (o.contractId) upliftBy[o.contractId] = (upliftBy[o.contractId] || 0) + o.impact; });
      const rows = s.contracts.filter((c) => c.status !== "Expired" && c.end).map((c) => { const nd = new Date(new Date(c.end!).getTime() - (c.renewalNoticeDays || 0) * 86400000); const dl = Math.round((nd.getTime() - now.getTime()) / 86400000); return { c, nd, dl, upl: upliftBy[c.id] || 0, urg: dl <= 0 ? "overdue" : dl <= 90 ? "soon" : "ok" }; }).sort((a, b) => a.dl - b.dl);
      const exp = rows.filter((r) => r.urg !== "ok").reduce((t, r) => t + r.upl, 0);
      return (
        <>
          <div className="grid g3" style={{ marginBottom: 16 }}>
            <div className="kpi"><div className="mt">In the window</div><div className="mv">{rows.filter((r) => r.urg !== "ok").length}</div><div className="ms">need attention</div></div>
            <div className="kpi"><div className="mt">Auto-renewing</div><div className="mv">{rows.filter((r) => r.urg !== "ok" && r.c.autoRenew).length}</div><div className="ms">act before deadline</div></div>
            <div className="kpi pp"><div className="mt">Uplift at stake</div><div className="mv">{fmtK(exp)}</div><div className="ms">negotiable</div></div>
          </div>
          <div className="card" style={{ padding: "8px 18px" }}>{rows.map((r) => { const b = r.urg === "overdue" ? <span className="badge b-exp">Overdue</span> : r.urg === "soon" ? <span className="badge b-soon">Soon</span> : <span className="badge b-ok">Later</span>; const days = r.dl <= 0 ? `${Math.abs(r.dl)}d past notice` : `${r.dl}d to notice`;
            return (<div className="vrow" key={r.c.id}><div className="av" style={{ background: r.urg === "ok" ? "var(--purple-xl)" : "var(--amber-bg)", color: r.urg === "ok" ? "var(--purple-d)" : "var(--amber)" }}>{r.c.autoRenew ? "🔁" : "📅"}</div><div style={{ flex: 1, minWidth: 0 }}><div style={{ fontWeight: 700, fontSize: 14 }}>{r.c.vendor} {b}</div><div style={{ fontSize: 12.5, color: "var(--muted)" }}>Ends {r.c.end} · {r.c.renewalType} · {days}</div></div><div style={{ textAlign: "right" }}><div style={{ fontWeight: 800 }}>{r.upl ? fmtK(r.upl) : "—"}</div><div style={{ fontSize: 11, color: "var(--muted)" }}>uplift</div></div><button className="btn sm" onClick={() => draftDoc(r.c.vendor, "reneg")}>✦ Draft</button></div>); })}</div>
        </>
      );
    },

    commitments: () => {
      const cc = s.contracts.filter((c) => c.yearlyCommit != null && c.yearlyCommit > 0);
      const totC = cc.reduce((t, c) => t + (c.yearlyCommit || 0), 0);
      const consumed = cc.reduce((t, c) => t + Math.min(sum(byContract(s, c.id)), c.yearlyCommit || 0), 0);
      const remaining = Math.max(0, totC - consumed);
      const compliant = cc.filter((c) => { const u = pct(sum(byContract(s, c.id)), c.yearlyCommit || 1); return u >= 85 && u <= 110; }).length;
      return (
        <>
          <div className="grid g4" style={{ marginBottom: 16 }}>
            <div className="kpi"><div className="mt">Total commitments</div><div className="mv">{fmtK(totC)}</div><div className="ms">{cc.length} contracts</div></div>
            <div className="kpi"><div className="mt">Consumed</div><div className="mv">{fmtK(consumed)}</div><div className="ms">{pct(consumed, totC).toFixed(0)}% utilised</div></div>
            <div className="kpi pp"><div className="mt">Remaining</div><div className="mv">{fmtK(remaining)}</div><div className="ms">unused commitment</div></div>
            <div className="kpi gg"><div className="mt">Compliance</div><div className="mv">{cc.length ? pct(compliant, cc.length).toFixed(0) : 0}%</div><div className="ms">within 85–110%</div></div>
          </div>
          <div className="grid g2">{cc.map((c) => { const a = sum(byContract(s, c.id)), u = pct(a, c.yearlyCommit || 1), rem = (c.yearlyCommit || 0) - a, vr = a - (c.yearlyCommit || 0); const col = u > 110 ? "var(--red)" : u >= 85 ? "var(--green)" : "var(--amber)"; const badge = u > 110 ? <span className="badge b-exp">Over-utilised</span> : u >= 85 ? <span className="badge b-ok">On track</span> : <span className="badge b-soon">Under-utilised</span>;
            return (<div className="card ccard" key={c.id}><div><Ring p={Math.min(u, 100)} size={76} stroke={9} color={col} /></div><div style={{ flex: 1, minWidth: 0 }}><div style={{ fontWeight: 750, fontSize: 14.5 }}>{c.vendor} {badge}</div><div style={{ fontSize: 12, color: "var(--muted)", margin: "2px 0 8px" }}>{c.category}</div>
              <div style={{ display: "flex", gap: 16, fontSize: 12.5 }}><div><div style={{ color: "var(--muted)" }}>Commit</div><b>{fmtK(c.yearlyCommit || 0)}</b></div><div><div style={{ color: "var(--muted)" }}>Consumed</div><b>{fmtK(a)}</b></div><div><div style={{ color: "var(--muted)" }}>Remaining</div><b>{fmtK(Math.max(0, rem))}</b></div><div><div style={{ color: "var(--muted)" }}>Variance</div><b style={{ color: vr > 0 ? "var(--red)" : "var(--green)" }}>{vr > 0 ? "+" : ""}{fmtK(vr)}</b></div></div></div></div>); })}</div>
        </>
      );
    },

    commitcheck: () => {
      const c = ccl;
      const exp = (m: number) => c.value * (c.indexShare / 100) * (m / 100);
      const e5 = exp(5), e10 = exp(10), e15 = exp(15);
      let verdict = "APPROVE", vc = "v-app", vx = `Exposure stays within ${fmt(c.tolerance)} even at +15% (${fmt(e15)}). Safe to commit.`;
      if (e5 > c.tolerance) { verdict = "BLOCK"; vc = "v-blk"; vx = `Even a 5% adverse move (${fmt(e5)}) breaches the ${fmt(c.tolerance)} tolerance. Renegotiate indexation or add a cap before signing.`; }
      else if (e15 > c.tolerance) { verdict = "CONDITION"; vc = "v-con"; vx = `Resilient to small moves, but a 15% move (${fmt(e15)}) breaches tolerance. Approve only with an index cap.`; }
      return (
        <div className="grid g2">
          <div className="card"><div className="sectlbl" style={{ margin: "0 0 6px" }}>Proposed commitment</div><div className="psub" style={{ margin: "0 0 8px" }}>Model the indexed exposure before the deal is signed.</div>
            <div className="formrow"><label>Annual commitment value</label><input type="number" value={c.value} step={10000} style={{ width: 150 }} onChange={(e) => setCcl({ ...c, value: +e.target.value || 0 })} /></div>
            <div className="formrow"><label>Term (years)</label><input type="number" value={c.term} min={1} max={10} style={{ width: 90 }} onChange={(e) => setCcl({ ...c, term: +e.target.value || 1 })} /></div>
            <div className="formrow"><label>Index-linked share <b style={{ color: "var(--purple)" }}>{c.indexShare}%</b></label><input type="range" min={0} max={100} value={c.indexShare} onChange={(e) => setCcl({ ...c, indexShare: +e.target.value })} /></div>
            <div className="formrow"><label>Margin tolerance ($/yr)</label><input type="number" value={c.tolerance} step={5000} style={{ width: 130 }} onChange={(e) => setCcl({ ...c, tolerance: +e.target.value || 0 })} /></div></div>
          <div className="card"><div className="sectlbl" style={{ margin: "0 0 6px" }}>Margin exposure — stress test</div><div className="psub" style={{ margin: "0 0 6px" }}>Indexed portion = {fmt(c.value * c.indexShare / 100)} of {fmt(c.value)}.</div>
            <Bars rows={[["+5% move", e5], ["+10% move", e10], ["+15% move", e15]]} cls="a" />
            <div className={`verdict ${vc}`}>{verdict === "APPROVE" ? "✓" : verdict === "CONDITION" ? "▲" : "✕"} {verdict}</div><div className="psub" style={{ margin: 0 }}>{vx}</div></div>
        </div>
      );
    },

    intelligence: () => {
      const anomalies = opps.filter((o) => ["Duplicate invoice", "Spend after expiry"].includes(o.type));
      const sugg = ["Where can I save the most?", "What auto-renews soon?", "How much spend is off-contract?", "What's recoverable right now?", "Which suppliers should we consolidate?"];
      return (
        <>
          <div className="card hero" style={{ marginBottom: 18 }}><div className="lbl">✦ NirvanaI · your cost-intelligence copilot</div><div style={{ fontSize: 22, fontWeight: 800, margin: "8px 0 4px" }}>Ask anything about your spend &amp; contracts</div>
            <div className="sub">Grounded in your own data — every answer cites the numbers behind it.</div>
            <div className="chips">{sugg.map((q) => <div className="hchip" style={{ cursor: "pointer" }} key={q} onClick={() => ask(q)}>{q}</div>)}</div></div>
          <div className="grid g3" style={{ marginBottom: 6 }}>
            <div className="kpi pp"><div className="mt">Findings</div><div className="mv">{opps.length}</div><div className="ms">opportunities detected</div></div>
            <div className="kpi"><div className="mt">Anomalies</div><div className="mv">{anomalies.length}</div><div className="ms">duplicates &amp; post-expiry</div></div>
            <div className="kpi"><div className="mt">Recommended value</div><div className="mv">{fmtK(k.identified)}</div><div className="ms">across all findings</div></div>
          </div>
          <div className="sectlbl">🔍 AI findings &amp; anomalies</div>
          {anomalies.length ? anomalies.map((o) => (<div className="find" key={o.id}><div className="fi" style={{ background: "var(--red-bg)", color: "var(--red)" }}>{o.icon}</div><div style={{ alignSelf: "center" }}><div className="ft">{o.type} — {o.subject || ""}</div><div className="fd">{H(o.rationale)}</div></div><div style={{ alignSelf: "center", fontWeight: 800, marginLeft: "auto" }}>{fmtK(o.impact)}</div></div>)) : <div className="empty">No anomalies detected.</div>}
          <div className="sectlbl">💡 Top recommendations</div>
          {opps.slice(0, 4).map((o) => (<div className="find" key={o.id}><div className="fi">{o.icon}</div><div style={{ alignSelf: "center", flex: 1 }}><div className="ft">{o.act} — {o.subject || ""}</div><div className="fd">{o.action}</div></div><div style={{ alignSelf: "center", fontWeight: 800 }}>{fmtK(o.impact)}</div></div>))}
        </>
      );
    },

    portfolio: () => {
      const ent: Record<string, { entity: string; spend: number; matched: number; contracts: Set<string>; opp: number }> = {};
      s.spend.forEach((sp) => { const e = entityOf(s, sp); const r = (ent[e] = ent[e] || { entity: e, spend: 0, matched: 0, contracts: new Set(), opp: 0 }); r.spend += sp.amount; if (sp.resolvedContractId) { r.matched += sp.amount; r.contracts.add(sp.resolvedContractId); } });
      s.contracts.forEach((c) => { if (c.entity && ent[c.entity]) ent[c.entity].opp += oppByContract(c.id); });
      const rows = Object.values(ent).sort((a, b) => b.spend - a.spend);
      const invCount = s.invoices.length;
      const vendCount = new Set(s.spend.map((sp) => canonVendor(s, sp))).size;
      const byL1: Record<string, number> = {};
      s.spend.forEach((sp) => (byL1[l1Of(catOf(s, sp))] = (byL1[l1Of(catOf(s, sp))] || 0) + sp.amount));
      const segs: Seg[] = Object.entries(byL1).sort((a, b) => b[1] - a[1]).map(([label, value], i) => ({ label, value, color: CATCOL[i % CATCOL.length] }));
      return (
        <>
          <div className="grid g4" style={{ marginBottom: 16 }}>
            <div className="kpi"><div className="mt">Total spend</div><div className="mv">{fmtK(k.total)}</div><div className="ms">{s.spend.length} transactions</div></div>
            <div className="kpi"><div className="mt">Contracts</div><div className="mv">{s.contracts.length}</div><div className="ms">{s.contracts.filter((c) => c.status === "Active").length} active</div></div>
            <div className="kpi"><div className="mt">Invoices</div><div className="mv">{invCount}</div><div className="ms">{vendCount} vendors</div></div>
            <div className="kpi pp"><div className="mt">Identified opportunity</div><div className="mv">{fmtK(k.identified)}</div><div className="ms">{pct(k.identified, k.total).toFixed(1)}% of spend</div></div>
          </div>
          <div className="grid g2">
            <div className="card"><div className="sectlbl" style={{ margin: "0 0 10px" }}>Spend by entity</div><Bars rows={rows.map((r) => [r.entity, r.spend])} /></div>
            <div className="card"><div className="sectlbl" style={{ margin: "0 0 6px" }}>Group spend mix</div><div style={{ display: "flex", alignItems: "center", gap: 18, marginTop: 8 }}><div><Donut segs={segs} size={150} stroke={28} /></div><div style={{ flex: 1 }}>{segs.map((sg) => (<div key={sg.label} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5, margin: "6px 0" }}><span className="dot" style={{ background: sg.color }} />{sg.label}<b style={{ marginLeft: "auto" }}>{fmtK(sg.value)}</b></div>))}</div></div></div>
          </div>
          <div className="sectlbl">Entity scorecard</div>
          <div className="grid g3">{rows.map((r) => (<div className="card" key={r.entity}><div style={{ fontWeight: 750, fontSize: 15 }}>{r.entity}</div><div style={{ display: "flex", alignItems: "center", gap: 14, marginTop: 10 }}><div><Ring p={pct(r.matched, r.spend)} size={64} stroke={8} color="var(--green)" /></div><div style={{ fontSize: 12.5 }}><div style={{ color: "var(--muted)" }}>Spend</div><b style={{ fontSize: 15 }}>{fmtK(r.spend)}</b><div style={{ color: "var(--muted)", marginTop: 4 }}>Opportunity</div><b style={{ color: "var(--purple-d)" }}>{r.opp ? fmtK(r.opp) : "—"}</b></div></div><div style={{ fontSize: 12, color: "var(--muted)", marginTop: 8 }}>{r.contracts.size} contracts · {pct(r.matched, r.spend).toFixed(0)}% under management</div></div>))}</div>
        </>
      );
    },

    quality: () => {
      const po = s.spend.filter((sp) => sp.matchMethod === "PO" || sp.matchMethod === "Contract ID");
      const fz = s.spend.filter((sp) => (sp.matchMethod || "").startsWith("Vendor"));
      const un = s.spend.filter((sp) => !sp.resolvedContractId);
      const segs: Seg[] = [{ label: "PO / Contract-ID", value: sum(po), color: "#0f9d58" }, { label: "Vendor fuzzy", value: sum(fz), color: "#e07b1a" }, { label: "Unmatched", value: sum(un), color: "#e0394b" }];
      return (
        <>
          <div className="grid g2">
            <div className="card"><div className="sectlbl" style={{ margin: "0 0 10px" }}>Match coverage</div><div style={{ display: "flex", alignItems: "center", gap: 20 }}><div><Donut segs={segs} size={150} stroke={28} /></div><div style={{ flex: 1 }}>{segs.map((sg) => (<div key={sg.label} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, margin: "8px 0" }}><span className="dot" style={{ background: sg.color }} />{sg.label}<b style={{ marginLeft: "auto" }}>{fmtK(sg.value)}</b></div>))}</div></div><div className="psub" style={{ margin: "12px 0 0" }}>Every savings figure inherits the confidence of the link beneath it.</div></div>
            <div className="card"><div className="sectlbl" style={{ margin: "0 0 10px" }}>🧭 Unmatched queue</div><div className="psub" style={{ margin: "0 0 6px" }}>No contract link — surfaced, never hidden.</div>
              {un.slice(0, 40).map((sp) => (<div className="vrow" key={sp.id}><div style={{ flex: 1 }}><b style={{ fontSize: 13 }}>{sp.vendor}</b><div style={{ fontSize: 12, color: "var(--muted)" }}>{sp.id} · {sp.spendDate}</div></div><div style={{ fontWeight: 800 }}>{fmt(sp.amount)}</div></div>))}</div>
          </div>
          <div className="card" style={{ marginTop: 16 }}><div className="sectlbl" style={{ margin: "0 0 10px" }}>🟠 Fuzzy links to review</div>
            {fz.length ? fz.slice(0, 40).map((sp) => (<div className="vrow" key={sp.id}><div style={{ flex: 1 }}><b style={{ fontSize: 13 }}>{sp.vendor}</b> <span style={{ color: "var(--muted)" }}>→ {cById(s, sp.resolvedContractId)?.vendor || "—"}</span></div><span className="conf c-med">conf {(sp.matchConfidence || 0).toFixed(2)}</span><div style={{ fontWeight: 800 }}>{fmt(sp.amount)}</div></div>)) : <div className="empty">No fuzzy links.</div>}</div>
        </>
      );
    },

    settings: () => <SettingsView onChanged={load} snap={s} />,
  };

  function contractDetailView(id: string): JSX.Element {
    const c = cById(s, id);
    if (!c) return <div className="empty">Contract not found.</div>;
    const act = sum(byContract(s, id)); const base = c.yearlyCommit || c.acv || 1; const u = pct(act, base);
    const cOpps = opps.filter((o) => o.contractId === id); const rec = cOpps.filter((o) => o.bucket === "recovery"); const oppTot = cOpps.reduce((t, o) => t + o.impact, 0);
    const nd = c.renewalNoticeDays && c.end ? new Date(new Date(c.end).getTime() - c.renewalNoticeDays * 86400000).toISOString().slice(0, 10) : "—";
    const recs = byContract(s, id);
    const invMap: Record<string, { inv: string; amt: number; n: number; po?: string | null; method?: string }> = {};
    recs.forEach((sp) => { const key = sp.invoiceRef || sp.id; const m = invMap[key] = invMap[key] || { inv: key, amt: 0, n: 0, po: sp.po, method: sp.matchMethod }; m.amt += sp.amount; m.n++; });
    const invoices = Object.values(invMap);
    const col = u > 100 ? "var(--red)" : u >= 80 ? "var(--green)" : "var(--amber)";
    const consumed = Math.min(act, base); const remaining = base - act; const variance = act - (c.acv || 0);
    return (
      <>
        <div className="backlink" onClick={() => backToContracts()}>‹ Back to contracts</div>
        <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 4 }}><div className="av" style={{ width: 50, height: 50, fontSize: 20, borderRadius: 14 }}>{c.vendor.slice(0, 1)}</div>
          <div><div style={{ fontSize: 22, fontWeight: 800, letterSpacing: "-.5px" }}>{c.vendor}</div><div style={{ color: "var(--muted)", fontSize: 13 }}>{c.id} · {c.category} · {c.entity}</div></div>
          <div style={{ marginLeft: "auto" }}>{c.status === "Expired" ? <span className="badge b-exp">Expired</span> : c.autoRenew ? <span className="badge b-auto">Auto-renews</span> : <span className="badge b-opt">Option to renew</span>}</div></div>
        <div className="grid g4" style={{ margin: "14px 0 4px" }}>
          <div className="kpi"><div className="mt">Annual value</div><div className="mv">{fmtK(c.acv || 0)}</div><div className="ms">TCV {fmtK(c.contractValue || 0)}</div></div>
          <div className="kpi"><div className="mt">Actual spend</div><div className="mv">{fmtK(act)}</div><div className="ms">{recs.length} transactions</div></div>
          <div className="kpi"><div className="mt">Utilisation</div><div className="mv" style={{ color: col }}>{u.toFixed(0)}%</div><div className="ms">of {c.yearlyCommit != null ? "commitment" : "ACV"}</div></div>
          <div className={`kpi ${oppTot ? "pp" : ""}`}><div className="mt">Opportunity</div><div className="mv">{oppTot ? fmtK(oppTot) : "—"}</div><div className="ms">{cOpps.length} finding{cOpps.length !== 1 ? "s" : ""}</div></div>
        </div>
        <div className="grid g2">
          <div className="card"><div className="sectlbl" style={{ margin: "0 0 8px" }}>📋 Contract overview</div>
            <div className="kv"><span>Supplier</span><b>{c.vendor}</b></div>
            <div className="kv"><span>Category / Entity</span><b>{c.category} · {c.entity}</b></div>
            <div className="kv"><span>Department</span><b>{c.department || "—"}</b></div>
            <div className="kv"><span>Contract value (ACV / TCV)</span><b>{fmt(c.acv || 0)} / {fmt(c.contractValue || 0)}</b></div>
            <div className="kv"><span>Term</span><b>{c.start} → {c.end}</b></div>
            <div className="kv"><span>Payment terms</span><b>{c.paymentTerms || "—"}</b></div>
            <div className="kv"><span>Renewal</span><b>{c.renewalType}{c.renewalNoticeDays ? ` · ${c.renewalNoticeDays}d notice` : ""}</b></div>
            <div className="kv"><span>Notice deadline</span><b>{nd}</b></div>
            <div className="kv"><span>Rebate / SLA clause</span><b>{c.rebateClause ? "Rebate" : "—"}{c.slaPenaltyClause ? " · SLA" : ""}</b></div></div>
          <div className="card"><div className="sectlbl" style={{ margin: "0 0 8px" }}>🎯 Commitment &amp; variance</div>
            <div style={{ display: "flex", alignItems: "center", gap: 18, marginBottom: 6 }}><div><Ring p={Math.min(u, 100)} size={86} stroke={10} color={col} /></div>
              <div style={{ flex: 1 }}><div className="kv" style={{ border: "none", padding: "4px 0" }}><span>Commitment</span><b>{c.yearlyCommit != null ? fmt(c.yearlyCommit) : "— (T&M)"}</b></div><div className="kv" style={{ border: "none", padding: "4px 0" }}><span>Consumed</span><b>{fmt(consumed)}</b></div><div className="kv" style={{ border: "none", padding: "4px 0" }}><span>Remaining</span><b>{fmt(Math.max(0, remaining))}</b></div><div className="kv" style={{ border: "none", padding: "4px 0" }}><span>Variance vs ACV</span><b style={{ color: variance > 0 ? "var(--red)" : "var(--green)" }}>{variance > 0 ? "+" : ""}{fmt(variance)}</b></div></div></div>
            <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: ".4px", margin: "8px 0 2px" }}>Actual vs contract</div>
            <Bars rows={([["Actual", act], ["ACV", c.acv || 0]] as [string, number][]).concat(c.yearlyCommit != null ? [["Commitment", c.yearlyCommit]] : [])} /></div>
        </div>
        <div className="card" style={{ marginTop: 16 }}><div className="sectlbl" style={{ margin: "0 0 4px" }}>✦ AI insights &amp; recommended actions</div><div className="psub" style={{ margin: "0 0 4px" }}>From NirvanaI — grounded in this contract&rsquo;s spend.</div>
          {cOpps.length ? cOpps.map((o) => (<div className="reco" key={o.id}><div className={`ri ${o.bucket === "recovery" ? "ic-rec" : "ic-sav"}`}>{o.icon}</div><div style={{ flex: 1 }}><div style={{ fontWeight: 700, fontSize: 13 }}>{o.type} · {fmtK(o.impact)}</div><div style={{ fontSize: 12.5, color: "#4a4660", margin: "2px 0" }}>{H(o.rationale)}</div><div style={{ fontSize: 12.5, color: "var(--purple-d)" }}><b>Action:</b> {o.action}</div><div className="linkrow" style={{ marginTop: 6 }}><button className="btn sm" onClick={() => draftDoc(c.vendor, o.bucket === "recovery" ? "challenge" : "reneg")}>✦ Draft with NirvanaI</button><button className={`btn sm ${o.status === "recovered" ? "g" : ""}`} onClick={() => setStatus(o.id, "recovered")}>Mark done</button></div></div></div>)) : <div className="empty">No issues detected — utilisation and terms look healthy.</div>}</div>
        {rec.length > 0 && (<div className="card" style={{ marginTop: 16 }}><div className="sectlbl" style={{ margin: "0 0 6px" }}>💰 Margin recovery on this contract</div>{rec.map((o) => (<div className="vrow" key={o.id}><div className="icon ic-rec" style={{ width: 34, height: 34, fontSize: 16, borderRadius: 10 }}>{o.icon}</div><div style={{ flex: 1 }}><div style={{ fontWeight: 650, fontSize: 13 }}>{o.type}</div><div style={{ fontSize: 12, color: "var(--muted)" }}>{o.rationale.replace(/<[^>]+>/g, "").slice(0, 90)}…</div></div><div style={{ fontWeight: 800 }}>{fmt(o.impact)}</div></div>))}</div>)}
        <div className="grid g2" style={{ marginTop: 16 }}>
          <div className="card"><div className="sectlbl" style={{ margin: "0 0 8px" }}>🧾 Related invoices ({invoices.length})</div>{invoices.length ? invoices.map((iv) => (<div className="vrow" key={iv.inv}><div style={{ flex: 1 }}><div style={{ fontWeight: 650, fontSize: 13 }}>{iv.inv}</div><div style={{ fontSize: 12, color: "var(--muted)" }}>{iv.n} line{iv.n > 1 ? "s" : ""} · {iv.po || "no PO"} · {iv.method}</div></div><div style={{ fontWeight: 800 }}>{fmt(iv.amt)}</div></div>)) : <div className="empty">No invoices linked.</div>}</div>
          <div className="card"><div className="sectlbl" style={{ margin: "0 0 8px" }}>💸 Related spend ({recs.length})</div>{recs.length ? recs.slice(0, 30).map((sp) => (<div className="vrow" key={sp.id}><div style={{ fontSize: 12, color: "var(--muted)", width: 56 }}>{sp.id}</div><div style={{ flex: 1, fontSize: 12.5 }}>{sp.spendDate}</div><div style={{ fontSize: 11, color: "var(--muted)", width: 86 }}>{sp.po || "—"}</div><div style={{ fontWeight: 700 }}>{fmt(sp.amount)}</div></div>)) : <div className="empty">No spend linked.</div>}</div>
        </div>
      </>
    );
  }

  const counts: Record<string, number> = {
    opps: opps.filter((o) => o.status !== "recovered").length,
    recovery: opps.filter((o) => o.bucket === "recovery" && o.status !== "recovered").length,
    act: opps.filter((o) => o.status === "open").length,
  };
  const [title, subtitle] = TITLES[tab];
  const now = new Date(s.syncedAt + "");
  const hr = now.getHours();
  const greeting = tab === "home" ? `${hr < 12 ? "Good morning" : hr < 18 ? "Good afternoon" : "Good evening"}, Himalaya` : "";
  return (
    <div className="ci-shell">
      <div className="app">
        <Sidebar tab={tab} setTab={goTab} counts={counts} onAsk={() => setChat({ ...chat, open: true })} />
        <main className="main">
          <div className="hi">{greeting}</div>
          <div className="pt">{title}</div>
          <div className="psub">{subtitle}</div>
          <div>{views[tab]()}</div>
        </main>
        <Nirvana chat={chat} setChat={setChat} onAsk={ask} />
      </div>
    </div>
  );
}

// ── sidebar + nirvana ───────────────────────────────────────────────────────────────
function Sidebar({ tab, setTab, counts, onAsk }: { tab: string; setTab: (t: string) => void; counts: Record<string, number>; onAsk: () => void }) {
  return (
    <aside className="side">
      <div className="brand"><div className="logo">T</div><div><b>Terzo</b><span>Cost Intelligence</span></div></div>
      <nav>
        {NAV.map(([grp, items]) => (
          <span key={grp}>
            <div className="grp">{grp}</div>
            {items.map(([id, nm, ic]) => (
              <a key={id} href={`/ci?tab=${id}`} className={id === tab ? "active" : ""} onClick={(e) => { e.preventDefault(); setTab(id); }}><span className="ic">{ic}</span>{nm}{counts[id] ? <span className="ct">{counts[id]}</span> : null}</a>
            ))}
          </span>
        ))}
      </nav>
      <button className="askbtn" onClick={onAsk}>✦ Ask NirvanaI</button>
    </aside>
  );
}

function Nirvana({ chat, setChat, onAsk }: { chat: Chat; setChat: (c: Chat) => void; onAsk: (q: string) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const sugg = ["Where can I save the most?", "What auto-renews soon?", "How much spend is off-contract?", "What's recoverable right now?"];
  if (!chat.open) return <button className="nv-launch" title="Ask NirvanaI" onClick={() => setChat({ ...chat, open: true })}>✦</button>;
  return (
    <div className="nv-panel">
      <div className="nv-head"><div className="nv-logo">NirvanaI</div><button className="nv-x" onClick={() => setChat({ ...chat, open: false })}>✕</button></div>
      <div className="nv-body">
        {chat.log.length ? (
          <div className="nv-msgs">{chat.log.map((e, i) => (<div key={i}><div className="nv-q">{e.q}</div><div className="nv-a" dangerouslySetInnerHTML={{ __html: e.a }} /></div>))}</div>
        ) : (
          <>
            <div className="nv-hero"><div className="nv-word">NirvanaI</div><div className="nv-greet">How can I help you today?</div></div>
            {sugg.map((q) => <div className="nv-s" key={q} onClick={() => onAsk(q)}>✦ {q}</div>)}
          </>
        )}
      </div>
      <div className="nv-foot"><div className="nv-input">
        <input ref={inputRef} placeholder="Ask anything about your spend…" onKeyDown={(e) => { if (e.key === "Enter" && inputRef.current?.value.trim()) { onAsk(inputRef.current.value.trim()); inputRef.current.value = ""; } }} />
        <button className="nv-send" onClick={() => { const v = inputRef.current?.value.trim(); if (v) { onAsk(v); inputRef.current!.value = ""; } }}>➤</button>
      </div></div>
    </div>
  );
}
