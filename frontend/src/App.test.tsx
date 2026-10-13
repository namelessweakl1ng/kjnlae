import { expect, test } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import App from "./App";

test("model-only dashboard exposes real workflow entry points", () => {
  const markup = renderToStaticMarkup(<App />);
  expect(markup).toContain("/assets/logo.svg");
  expect(markup).toContain("Fine-tuned NLP");
  expect(markup).toContain("Attack lab");
  expect(markup).not.toContain("Rule engine");
  expect(markup).not.toContain("Combined");
});
