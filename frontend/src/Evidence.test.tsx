import { expect, test } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { Evidence } from "./Evidence";

test("untrusted HTML is escaped even when highlighted", () => {
  const input = "<img src=x onerror=alert(1)>";
  const rendered = renderToStaticMarkup(
    <Evidence text={input} spans={[{ start: 0, end: input.length }]} />,
  );
  expect(rendered).not.toContain("<img");
  expect(rendered).toContain("&lt;img");
  expect(rendered).toContain("<mark>");
});

test("overlapping evidence is merged and original text retained", () => {
  const rendered = renderToStaticMarkup(
    <Evidence
      text="abcdef"
      spans={[
        { start: 1, end: 4 },
        { start: 2, end: 5 },
      ]}
    />,
  );
  expect(rendered).toContain("a<mark>bcde</mark>f");
});

test("Python codepoint spans handle supplementary Unicode", () => {
  const rendered = renderToStaticMarkup(
    <Evidence text="😀attack" spans={[{ start: 1, end: 7 }]} />,
  );
  expect(rendered).toContain("😀<mark>attack</mark>");
});
