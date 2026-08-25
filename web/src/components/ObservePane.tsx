import { useState } from 'react';
import type { Cop, CameraProps, ObsProps } from '../api/types';
import { frameUrl } from '../api/client';
import { fmtClock } from '../lib/format';

interface Props {
  cop: Cop;
  eventId: string;
  selectedCameraId: string | null;
  onSelectCamera: (id: string) => void;
}

function FrameImg({ eventId, frame }: { eventId: string; frame: string }) {
  const [err, setErr] = useState(false);
  return (
    <div className="cam-frame">
      <span className="frame-badge">● LIVE · detector overlay</span>
      {err ? (
        <div className="frame-err">Frame unavailable<br />{frame}</div>
      ) : (
        <img src={frameUrl(eventId, frame)} alt="camera frame" onError={() => setErr(true)} loading="lazy" />
      )}
    </div>
  );
}

export default function ObservePane({ cop, eventId, selectedCameraId, onSelectCamera }: Props) {
  const cameras = cop.layers.cameras?.features ?? [];

  const hasCameraFront = (cop.layers.observations?.features ?? []).some(
    (f) => (f.properties as ObsProps | null)?.kind === 'camera_front',
  );

  const satCounts: Record<string, number> = {};
  for (const f of cop.layers.observations?.features ?? []) {
    const k = (f.properties as ObsProps | null)?.kind ?? 'unknown';
    satCounts[k] = (satCounts[k] ?? 0) + 1;
  }

  return (
    <div className="pane pane-left">
      <div className="pane-head">
        <span className="kicker">
          <span className="dot" style={{ background: 'var(--cyan)' }} />
          Observe
        </span>
        <span className="count">{cameras.length} cams · {cop.layers.observations?.features.length ?? 0} obs</span>
      </div>

      <div className="pane-body">
        <div className="section-label">Ground cameras</div>
        {cameras.length === 0 && <div className="empty-hint">No cameras in this event.</div>}

        {cameras.map((f) => {
          const p = f.properties as CameraProps;
          const selected = p.id === selectedCameraId;
          return (
            <div
              key={p.id}
              className={`card clickable cam-card${selected ? ' selected' : ''}`}
              onClick={() => onSelectCamera(p.id)}
            >
              <div className="cam-top">
                <span className="dotmk" style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--accent)', boxShadow: '0 0 6px var(--accent)' }} />
                <span className="cam-name">{p.name}</span>
                <span className="cam-net">{p.network}</span>
              </div>

              {selected && (
                <>
                  {p.frame && <FrameImg eventId={eventId} frame={p.frame} />}
                  <div className="cam-pose">
                    <div className="pose-cell">
                      <div className="k">Pan</div>
                      <div className="v">{p.pan.toFixed(0)}°</div>
                    </div>
                    <div className="pose-cell">
                      <div className="k">Tilt</div>
                      <div className="v">{p.tilt.toFixed(1)}°</div>
                    </div>
                    <div className="pose-cell">
                      <div className="k">FOV</div>
                      <div className="v">{p.fov.toFixed(0)}°</div>
                    </div>
                  </div>
                  {hasCameraFront && (
                    <div className="cam-note">
                      <span>◈</span>
                      <span>A georeferenced fire front was produced from camera imagery and fused into the forecast (see the cyan front on the map).</span>
                    </div>
                  )}
                </>
              )}
            </div>
          );
        })}

        <div className="section-label">Observation feed</div>
        <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {Object.entries(satCounts).map(([k, n]) => (
            <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11.5, color: 'var(--text-dim)' }}>
              <span style={{ textTransform: 'uppercase', letterSpacing: '0.06em', fontFamily: 'var(--mono)', fontSize: 10.5 }}>{k}</span>
              <span style={{ marginLeft: 'auto', fontFamily: 'var(--mono)', color: 'var(--text)' }}>{n}</span>
            </div>
          ))}
          <div style={{ fontSize: 10.5, color: 'var(--text-faint)', marginTop: 2 }}>
            Latest at {fmtClock(cop.meta.issued_at)}. Use the timeline to replay the assimilation window.
          </div>
        </div>
      </div>
    </div>
  );
}
