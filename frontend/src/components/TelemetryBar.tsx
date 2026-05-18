/* ============================================================
 * PhysioAI Pro V2 — TelemetryBar
 * ============================================================
 * Compact mono strip showing live pipeline numbers. Lives at
 * the top of the ScannerScreen so the user can verify the
 * stream is healthy without leaving the camera.
 *
 * The values are dim by default — this is not a primary UI
 * element, just a reassurance the machine is working.
 * ============================================================ */

import "./TelemetryBar.css";

type Props = {
  connected: boolean;
  clientFps: number;
  serverFps: number;
  framesSent: number;
  detected: boolean;
};

export function TelemetryBar({ connected, clientFps, serverFps, framesSent, detected }: Props) {
  return (
    <div className="telem">
      <Item label="LINK" value={
        connected ? <span className="telem__ok">CONNECTED</span> : <span className="telem__bad">DISCONNECTED</span>
      } />
      <Item label="DET" value={
        detected ? <span className="telem__ok">LOCKED</span> : <span className="telem__warn">SEARCHING</span>
      } />
      <Item label="CLIENT FPS" value={clientFps.toString()} />
      <Item label="SERVER FPS" value={serverFps.toFixed(1)} />
      <Item label="SENT" value={framesSent.toString()} />
    </div>
  );
}

function Item({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="telem__item">
      <span className="label telem__label">{label}</span>
      <span className="mono telem__value">{value}</span>
    </div>
  );
}
