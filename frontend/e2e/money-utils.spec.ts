/** Pure unit tests for the frontend money utility (no browser needed). */
import { expect, test } from "@playwright/test";

import { formatCompact, formatMoney, fromVnd, parseAmount, toVnd } from "../src/lib/money";

const RATE = 25869;

test("conversion rounds to 1.000 VND and round-trips within rounding", () => {
  expect(toVnd(1, "USD", RATE)).toBe(26000);
  expect(toVnd(0, "USD", RATE)).toBe(0);
  expect(toVnd(1234567, "VND", RATE)).toBe(1235000);
  for (const usd of [0.5, 12.34, 5000, 250000.75]) {
    expect(Math.abs(fromVnd(toVnd(usd, "USD", RATE), "USD", RATE) - usd)).toBeLessThanOrEqual(500 / RATE + 1e-9);
  }
  expect(toVnd(10_000_000, "USD", RATE)).toBe(258_690_000_000);
  expect(toVnd(100, "USD", 25000)).toBe(2_500_000);
  expect(toVnd(100, "USD", 26000)).toBe(2_600_000);
});

test("formatting: vi-VN full and compact (triệu, tỷ), USD compact", () => {
  const norm = (s: string) => s.replace(/\s/g, " ");
  expect(norm(formatMoney(1_250_000, "VND", RATE))).toBe("1.250.000 ₫");
  expect(norm(formatMoney(2_586_900, "USD", RATE))).toBe("$100.00");
  expect(formatMoney(null, "VND", RATE)).toBe("—");
  expect(formatCompact(350_000_000, "VND", RATE)).toBe("350 triệu");
  expect(formatCompact(1_250_000_000, "VND", RATE)).toBe("1,25 tỷ");
  expect(formatCompact(12_500_000, "VND", RATE)).toBe("12,5 triệu");
  expect(formatCompact(12_400 * RATE, "USD", RATE)).toBe("$12.4K");
  expect(norm(formatCompact(500_000, "VND", RATE))).toBe("500.000 ₫");
});

test("parseAmount handles thousands and decimals", () => {
  expect(parseAmount("1.250.000")).toBe(1_250_000);
  expect(parseAmount("5,000")).toBe(5000);
  expect(parseAmount("12,5")).toBe(12.5);
  expect(parseAmount("12.50")).toBe(12.5);
  expect(parseAmount("abc")).toBeNull();
});
