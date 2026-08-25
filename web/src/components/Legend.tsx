import { rampCss, OBS_COLORS } from '../lib/colors';

export default function Legend({ arm, horizon }: { arm: 'on' | 'off'; horizon: number }) {
  const rampGradient = `linear-gradient(90deg, ${rampCss(0.1, 0.5)}, ${rampCss(0.3, 0.7)}, ${rampCss(0.5, 0.85)}, ${rampCss(0.7, 0.95)}, ${rampCss(0.9, 1)})`;

  return (
    <div className="map-overlay legend">
      <div className="ctrl-card">
        <div className="ctrl-title">
          Burn probability · +{horizon}m · assim {arm.toUpperCase()}
        </div>
        <div className="ramp-bar" style={{ background: rampGradient }} />
        <div className="ramp-scale">
          <span>10%</span>
          <span>30%</span>
          <span>50%</span>
          <span>70%</span>
          <span>90%</span>
        </div>

        <div className="legend-items">
          <div className="li">
            <span className="mk"><span className="linemk" style={{ borderColor: '#ffffff' }} /></span>
            Expected front
          </div>
          <div className="li">
            <span className="mk"><span className="linemk" style={{ borderColor: 'rgba(210,225,240,0.8)', borderTopStyle: 'dashed' }} /></span>
            90% region
          </div>
          <div className="li">
            <span className="mk"><span className="dotmk" style={{ background: `rgb(${OBS_COLORS.goes[0]},${OBS_COLORS.goes[1]},${OBS_COLORS.goes[2]})` }} /></span>
            Sat hotspot
          </div>
          <div className="li">
            <span className="mk"><span className="linemk" style={{ borderColor: `rgb(${OBS_COLORS.camera_front[0]},${OBS_COLORS.camera_front[1]},${OBS_COLORS.camera_front[2]})` }} /></span>
            Camera front
          </div>
          <div className="li">
            <span className="mk"><span className="linemk" style={{ borderColor: `rgb(${OBS_COLORS.official_perimeter[0]},${OBS_COLORS.official_perimeter[1]},${OBS_COLORS.official_perimeter[2]})` }} /></span>
            Official perim.
          </div>
          <div className="li">
            <span className="mk">★</span>
            Ignition
          </div>
          <div className="li">
            <span className="mk"><span className="dotmk" style={{ background: 'var(--accent)' }} /></span>
            Camera
          </div>
          <div className="li">
            <span className="mk"><span className="dotmk" style={{ width: 5, height: 5, background: 'var(--text-faint)' }} /></span>
            Structure
          </div>
        </div>
      </div>
    </div>
  );
}
