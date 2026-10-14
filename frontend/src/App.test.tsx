import { expect, test } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import App, { isModelReady, withinInputLimit } from "./App";
import type { Capabilities, Scan } from "./types";

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


test("model readiness is never green for a failed or timed-out worker", () => {
  const online = { model_status: "AVAILABLE" } as Capabilities;
  const missing = { model_status: "MISSING" } as Capabilities;
  expect(isModelReady(online, null)).toBe(true);
  expect(isModelReady(online, { model_status: "AVAILABLE" } as Scan)).toBe(true);
  expect(isModelReady(online, { model_status: "TIMED_OUT" } as Scan)).toBe(false);
  expect(isModelReady(online, { model_status: "ERROR" } as Scan)).toBe(false);
  expect(isModelReady(missing, null)).toBe(false);
  expect(isModelReady(null, null)).toBe(false);
});
