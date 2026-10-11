import { Fragment } from "react";

export function Evidence({
  text,
  spans,
}: {
  text: string;
  spans: { start: number; end: number }[];
}) {
  // API offsets use Python Unicode codepoints, not UTF-16 code units.
  const chars = Array.from(text);
  const merged: { start: number; end: number }[] = [];
  for (const span of [...spans].sort((a, b) => a.start - b.start)) {
    const start = Math.max(0, span.start),
      end = Math.min(chars.length, span.end);
    if (start >= end) continue;
    const last = merged.at(-1);
    if (last && start <= last.end) last.end = Math.max(last.end, end);
    else merged.push({ start, end });
  }
  let cursor = 0;
  const nodes = merged.map((s, i) => {
    const prefix = chars.slice(cursor, s.start).join("");
    cursor = s.end;
    return (
      <Fragment key={i}>
        {prefix}
        <mark>{chars.slice(s.start, s.end).join("")}</mark>
      </Fragment>
    );
  });
  return (
    <pre className="evidence">
      {nodes}
      {chars.slice(cursor).join("")}
    </pre>
  );
}
