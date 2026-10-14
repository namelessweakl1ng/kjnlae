import { expect, test } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { WindowScores } from "./WindowScores";

test("renders measured windows, threshold relation, and escaped source text", () => {
  const markup = renderToStaticMarkup(<WindowScores text={'<img src=x onerror="alert(1)">'}
    threshold={0.5} selected={0} onSelect={() => undefined} windows={[
      { view: "original", start: 0, end: 30, score: 0.9, model_hash: "a" },
      { view: "normalized", start: 0, end: 4, score: 0.1, model_hash: "a" },
    ]} />);
  expect(markup).toContain("Window 1 · highest");
  expect(markup).toContain("above threshold");
  expect(markup).toContain("below threshold");
  expect(markup).toContain("90.0%");
  expect(markup).not.toContain("<img");
});
