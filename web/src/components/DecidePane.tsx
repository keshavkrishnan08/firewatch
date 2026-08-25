import { useState } from 'react';
import type { Cop, Decision } from '../api/types';
import { queryNL } from '../api/client';
import { urgencyRGB, urgencyCss, urgencyLabel } from '../lib/colors';
import { fmtPct, fmtLeadBand, fmtNumber } from '../lib/format';

interface Props {
  cop: Cop;
  eventId: string;
  horizon: number;
  selectedDecisionId: string | null;
  onSelectDecision: (d: Decision) => void;
}

function DecisionCard({
  d,
  rank,
  selected,
  onClick,
  showLead = true,
}: {
  d: Decision;
  rank: number;
  selected: boolean;
  onClick: () => void;
  showLead?: boolean;
}) {
  const [r, g, b] = urgencyRGB(d.urgency);
  const urgCss = urgencyCss(d.urgency);
  return (
    <div className={`card clickable dec-card${selected ? ' selected' : ''}`} onClick={onClick}>
      <span className="urg-strip" style={{ background: urgCss }} />
      <div className="dec-head">
        <span className="rank">#{rank}</span>
        <span className="dec-target">{d.target_name}</span>
        <span className="urg-tag" style={{ color: urgCss, background: `rgba(${r},${g},${b},0.14)` }}>
          {urgencyLabel(d.urgency)}
        </span>
      </div>

      <div className="urg-meter">
        <i style={{ width: `${Math.max(4, Math.min(100, d.urgency * 100))}%`, background: urgCss }} />
      </div>

      <div className="dec-metrics">
        {showLead && (
          <div className="dec-metric" style={{ flex: 1 }}>
            <span className="k">Lead time</span>
            <span className="v">{fmtLeadBand(d)}</span>
          </div>
        )}
        <div className="dec-metric">
          <span className="k">Confidence</span>
          <span className="v">{fmtPct(d.confidence)}</span>
        </div>
      </div>

      <div className="dec-rationale">{d.rationale}</div>

      <div className="dec-foot">
        <div className="conf-bar">
          <i style={{ width: `${Math.round(d.confidence * 100)}%`, background: urgCss }} />
        </div>
        <span className="chip">{d.evidence?.length ?? 0} evidence</span>
      </div>
    </div>
  );
}

function NLQuery({ eventId }: { eventId: string }) {
  const [q, setQ] = useState('');
  const [busy, setBusy] = useState(false);
  const [answer, setAnswer] = useState<string | null>(null);
  const [cites, setCites] = useState<string[]>([]);
  const [err, setErr] = useState<string | null>(null);

  const run = async () => {
    const query = q.trim();
    if (!query || busy) return;
    setBusy(true);
    setErr(null);
    setAnswer(null);
    setCites([]);
    try {
      const res = await queryNL(eventId, query);
      setAnswer(res.answer ?? '(no answer returned)');
      const c = res.cited ?? res.citations ?? res.ids ?? [];
      setCites(Array.isArray(c) ? c.map(String) : []);
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Query failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="nlq">
      <div className="section-label" style={{ marginTop: 0 }}>Ask the picture</div>
      <div className="nlq-row">
        <input
          value={q}
          placeholder="e.g. which zones must evacuate first?"
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') run();
          }}
        />
        <button onClick={run} disabled={busy || !q.trim()}>
          {busy ? '…' : 'Ask'}
        </button>
      </div>
      {err && <div className="answer err">{err}</div>}
      {answer && !err && (
        <div className="answer">
          {answer}
          {cites.length > 0 && (
            <div className="cites">
              {cites.map((c) => (
                <span className="chip" key={c}>{c}</span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function DecidePane({ cop, eventId, horizon, selectedDecisionId, onSelectDecision }: Props) {
  const dec = cop.decisions;
  const evac = [...(dec.evacuations ?? [])].sort((a, b) => b.urgency - a.urgency);
  const egress = [...(dec.egress ?? [])].sort((a, b) => b.urgency - a.urgency);
  const staging = [...(dec.staging ?? [])].sort((a, b) => b.urgency - a.urgency);

  const hKey = String(horizon);
  const horizons = cop.meta.horizons ?? [15, 30, 60, 180];
  const agg = dec.risk?.aggregate_expected_people ?? {};
  const structAtH = dec.structures?.[hKey];

  return (
    <div className="pane pane-right">
      <div className="pane-head">
        <span className="kicker">
          <span className="dot" style={{ background: 'var(--red)' }} />
          Decide
        </span>
        <span className="count">{evac.length + egress.length + staging.length} recs</span>
      </div>

      <div className="pane-body">
        <div className="section-label">Evacuation priority</div>
        {evac.length === 0 && <div className="empty-hint">No evacuation recommendations.</div>}
        {evac.map((d, i) => (
          <DecisionCard
            key={d.id}
            d={d}
            rank={i + 1}
            selected={d.id === selectedDecisionId}
            onClick={() => onSelectDecision(d)}
          />
        ))}

        <div className="section-label">Egress routes</div>
        {egress.length === 0 && <div className="empty-hint">No egress actions.</div>}
        {egress.map((d, i) => (
          <DecisionCard
            key={d.id}
            d={d}
            rank={i + 1}
            selected={d.id === selectedDecisionId}
            onClick={() => onSelectDecision(d)}
          />
        ))}

        <div className="section-label">Staging candidates</div>
        {staging.length === 0 && <div className="empty-hint">No staging suggestions.</div>}
        {staging.map((d, i) => (
          <DecisionCard
            key={d.id}
            d={d}
            rank={i + 1}
            selected={d.id === selectedDecisionId}
            onClick={() => onSelectDecision(d)}
            showLead={false}
          />
        ))}

        <div className="section-label">Exposure · people at risk</div>
        <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div className="risk-grid">
            {horizons.map((h) => {
              const v = agg[String(h)] ?? 0;
              const active = h === horizon;
              return (
                <div
                  className="risk-cell"
                  key={h}
                  style={active ? { borderColor: 'var(--accent)', background: 'rgba(76,157,255,0.08)' } : undefined}
                >
                  <div className="h">+{h}m</div>
                  <div className="n" style={{ color: v > 0 ? 'var(--amber-soft)' : 'var(--text-faint)' }}>
                    {fmtNumber(v)}
                  </div>
                  <div className="u">people</div>
                </div>
              );
            })}
          </div>

          <div>
            {(dec.risk?.zones ?? []).map((z) => {
              const pb = z.prob_burned?.[hKey] ?? 0;
              return (
                <div className="risk-zone-row" key={z.zone_id}>
                  <span className="zn">{z.name}</span>
                  <span className="track">
                    <i style={{ width: `${Math.round(pb * 100)}%`, background: urgencyCss(pb) }} />
                  </span>
                  <span className="pn">{fmtPct(pb)}</span>
                </div>
              );
            })}
          </div>

          {structAtH && (
            <div style={{ fontSize: 11, color: 'var(--text-dim)', borderTop: '1px solid var(--border)', paddingTop: 8 }}>
              Structures at +{horizon}m:{' '}
              <b style={{ color: 'var(--text)', fontFamily: 'var(--mono)' }}>{structAtH.expected.toFixed(1)}</b> expected loss ·{' '}
              {structAtH.high_conf} high-confidence of {structAtH.n_total}.
            </div>
          )}
        </div>
      </div>

      <NLQuery eventId={eventId} />
    </div>
  );
}
