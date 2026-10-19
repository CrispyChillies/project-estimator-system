/** Every role/category tag token pair meets WCAG AA text contrast (4.5:1) in light and dark. */
import { expect, test } from "@playwright/test";

import { contrast, PALETTE, TAG_TOKENS } from "../src/lib/tags";

test("all tag tokens have >= 4.5:1 text contrast in both themes", () => {
  const failures: string[] = [];
  for (const token of PALETTE) {
    for (const theme of ["l", "d"] as const) {
      const { bg, fg } = TAG_TOKENS[token][theme];
      const c = contrast(bg, fg);
      if (c < 4.5) failures.push(`${token}/${theme}: ${c.toFixed(2)}`);
    }
  }
  expect(failures).toEqual([]);
  expect(PALETTE.length).toBeGreaterThanOrEqual(16);
});

test("contrast helper sanity", () => {
  expect(contrast("#000000", "#ffffff")).toBeCloseTo(21, 0);
  expect(contrast("#777777", "#777777")).toBeCloseTo(1, 5);
});
