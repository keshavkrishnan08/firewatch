import { useEffect, useRef, useState } from 'react';
import { fmtClockFromMs } from '../lib/format';

interface Props {
  ignitionMs: number;
  issuedMs: number;
  horizons: number[];
  value: number;
  onChange: (ms: number) => void;
  obsCount: number;
}

export default function TimeScrubber({ ignitionMs, issuedMs, horizons, value, onChange, obsCount }: Props) {
  const maxH = horizons.length ? Math.max(...horizons) : 180;
  const maxMs = issuedMs + maxH * 60000;
  const span = Math.max(1, maxMs - ignitionMs);
  const issuePct = ((issuedMs - ignitionMs) / span) * 100;
  const valuePct = ((Math.min(maxMs, Math.max(ignitionMs, value)) - ignitionMs) / span) * 100;

  const [playing, setPlaying] = useState(false);
  const valueRef = useRef(value);
  valueRef.current = value;

  useEffect(() => {
    if (!playing) return;
    const step = span / 260;
    const id = window.setInterval(() => {
      const next = valueRef.current + step;
      if (next >= maxMs) {
        onChange(ignitionMs); // loop
      } else {
        onChange(next);
      }
    }, 45);
    return () => window.clearInterval(id);
  }, [playing, span, maxMs, ignitionMs, onChange]);

  const inFuture = value > issuedMs + 1;
  const futureMin = Math.round((value - issuedMs) / 60000);

  return (
    <div className="scrubber">
      <button className="play" onClick={() => setPlaying((p) => !p)} title={playing ? 'Pause' : 'Play timeline'}>
        {playing ? '❚❚' : '▶'}
      </button>

      <div className="clock">
        <div className="t">{fmtClockFromMs(value)}</div>
        <div className="p">
          {inFuture ? (
            <>
              Forecast <b>+{futureMin} min</b>
            </>
          ) : value >= issuedMs - 1 ? (
            <>Issued · now</>
          ) : (
            <>Assimilation window</>
          )}
        </div>
      </div>

      <div className="track-wrap" style={{ ['--issue-pct' as string]: `${issuePct}%` }}>
        <div className="track-line" />
        <div className="track-fill" style={{ width: `${valuePct}%` }} />

        <div className="track-tick" style={{ left: '0%' }}>
          <div className="tk" />
          <div className="tl">IGNITION</div>
        </div>

        <div className="track-tick issue" style={{ left: `${issuePct}%` }}>
          <div className="tk" />
          <div className="tl">ISSUED</div>
        </div>

        {horizons.map((h) => {
          const pct = ((issuedMs + h * 60000 - ignitionMs) / span) * 100;
          return (
            <div className="track-tick" style={{ left: `${pct}%` }} key={h}>
              <div className="tk" />
              <div className="tl">+{h}</div>
            </div>
          );
        })}

        <input
          type="range"
          min={ignitionMs}
          max={maxMs}
          step={1000}
          value={Math.min(maxMs, Math.max(ignitionMs, value))}
          onChange={(e) => {
            if (playing) setPlaying(false);
            onChange(Number(e.target.value));
          }}
          aria-label="Timeline scrubber"
        />
      </div>

      <div className="obs-count">
        <div className="n">{obsCount}</div>
        <div className="l">obs shown</div>
      </div>
    </div>
  );
}
