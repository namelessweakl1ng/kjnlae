import { expect, test } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import App, { withinInputLimit } from "./App";

test("scanner exposes model inspection without demo tabs", () => {
  const markup = renderToStaticMarkup(<App />);
  expect(markup).toContain("/assets/logo.svg");
  expect(markup).toContain("Run inspection");
  expect(markup).toContain("Untrusted content");
  expect(markup).not.toContain("Attack lab");
  expect(markup).not.toContain("Rule engine");
  expect(markup).not.toContain("Combined");
});

test("input limit counts Unicode codepoints like the API", () => {
  expect(withinInputLimit("😀".repeat(32768))).toBe(true);
  expect(withinInputLimit("😀".repeat(32769))).toBe(false);
});
