import type { Scan } from "./types";

type Window = Scan["windows"][number];

/** Render measured model-window scores; these bars are not token attribution. */
export function WindowScores({ windows, threshold, text, selected, onSelect }: {
  windows: Window[];
  threshold: number;
  text: string;
  selected: number;
  onSelect: (index: number) => void;
}) {
  const chars = Array.from(text);
  const highest = windows.reduce((best, window, index) =>
    window.score > (windows[best]?.score ?? -1) ? index : best, 0);
  return <div className="window-list">
    {windows.map((window, index) => <button type="button" key={`${index}-${window.view}-${window.start}`}
      className={`window-row ${selected === index ? "is-selected" : ""}`}
      aria-pressed={selected === index} onClick={() => onSelect(index)}>
      <span className="window-header"><strong>Window {index + 1}{index === highest ? " · highest" : ""}</strong>
        <span>{(window.score * 100).toFixed(1)}%</span></span>
      <span className="bar-track" aria-hidden="true"><span className={window.score >= threshold ? "bar-fill above" : "bar-fill"}
        style={{ width: `${window.score * 100}%` }} /></span>
      <span className="window-meta">{window.view} · chars {window.start}–{window.end} · {window.score >= threshold ? "above threshold" : "below threshold"}</span>
      <span className="window-snippet">{chars.slice(window.start, window.end).join("").slice(0, 150) || "Transformed view"}</span>
    </button>)}
  </div>;
}
