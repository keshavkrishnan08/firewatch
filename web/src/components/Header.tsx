import type { Meta, Evaluation } from '../api/types';
import { fmtClock, fmtWindSpeed, bearingToCompass } from '../lib/format';

function WindArrow({ dirToDeg, size = 16 }: { dirToDeg: number; size?: number }) {
  // dir_to_deg = bearing the wind blows TOWARD (0 = N, clockwise).
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" style={{ transform: `rotate(${dirToDeg}deg)` }}>
      <path d="M12 2 L12 22 M12 2 L6.5 9 M12 2 L17.5 9" fill="none" stroke="#79b8ff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function statusPill(status: string) {
  const s = (status || '').toLowerCase();
  if (s === 'contained' || s === 'out' || s === 'inactive') {
    return <span className="pill pill-contained"><span className="led" />{status}</span>;
  }
  return <span className="pill pill-active"><span className="led" />{status || 'active'}</span>;
}

export default function Header({ meta, evaluation }: { meta: Meta; evaluation?: Evaluation }) {
  const w = meta.wind;

  // Ablation delta at 60m (assimilation ON vs OFF baseline).
  let delta: { iou: number } | null = null;
  const abl = evaluation?.ablation;
  if (abl) {
    const at = abl['60'] ?? abl[Object.keys(abl)[0]];
    if (at && typeof at.iou_on === 'number' && typeof at.iou_off === 'number') {
      delta = { iou: at.iou_on - at.iou_off };
    }
  }

  return (
    <header className="header">
      <div className="brand">
        <div className="mark">△</div>
        <div>
          <div className="name">FIREWATCH</div>
          <div className="sub">Common Operating Picture</div>
        </div>
      </div>

      <div className="fire-block">
        <div className="fire-name">{meta.fire.name}</div>
        <div className="fire-meta">
          {statusPill(meta.fire.status)}
          <span>·</span>
          <span style={{ fontFamily: 'var(--mono)' }}>{meta.fire.id}</span>
        </div>
      </div>

      <div className="spacer" />

      <div className="stat-cluster">
        <div className="stat">
          <div className="lbl">Wind</div>
          <div className="val">
            <span className="wind-mini">
              <span className="arrow"><WindArrow dirToDeg={w.dir_to_deg} /></span>
            </span>
            <span>{fmtWindSpeed(w.speed_ms)}</span>
            <small>→ {bearingToCompass(w.dir_to_deg)}</small>
          </div>
        </div>

        <div className="stat">
          <div className="lbl">RH / Temp</div>
          <div className="val">
            {Math.round(w.rh_pct)}% <small>RH</small> · {Math.round(w.temp_c)}°C
          </div>
        </div>

        <div className="stat">
          <div className="lbl">Issued</div>
          <div className="val">{fmtClock(meta.issued_at)}</div>
        </div>

        <div className="stat">
          <div className="lbl">Data assimilation</div>
          <div className="val" style={{ gap: 8 }}>
            {meta.assimilation ? (
              <span className="pill pill-assim"><span className="led" />ON</span>
            ) : (
              <span className="pill" style={{ color: 'var(--text-faint)', borderColor: 'var(--border-strong)' }}>OFF</span>
            )}
            {delta && (
              <span className="pill pill-delta" title="IoU improvement vs no-assimilation baseline at +60 min">
                {delta.iou >= 0 ? '+' : ''}
                {delta.iou.toFixed(2)} ΔIoU vs baseline
              </span>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
