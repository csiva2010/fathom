import { describe, expect, it } from "vitest";

import { direction, formatChange, formatPrice } from "./number";
import { timeAgo } from "./time";

describe("number formatting", () => {
  it("formats prices and signed changes", () => {
    expect(formatPrice(5800.1)).toBe("5,800.10");
    expect(formatChange(12.5, 0.216)).toBe("+12.50 (+0.22%)");
    expect(formatChange(-3, null)).toBe("-3.00");
    expect(formatChange(null, null)).toBe("—");
  });

  it("derives direction", () => {
    expect(direction(1)).toBe("up");
    expect(direction(-1)).toBe("down");
    expect(direction(0)).toBe("flat");
    expect(direction(null)).toBe("flat");
  });
});

describe("timeAgo", () => {
  const now = new Date("2026-10-30T12:00:00Z");
  it.each([
    ["2026-10-30T11:59:30Z", "just now"],
    ["2026-10-30T11:55:00Z", "5 min ago"],
    ["2026-10-30T09:00:00Z", "3 h ago"],
  ])("%s -> %s", (iso, expected) => {
    expect(timeAgo(iso, now)).toBe(expected);
  });

  it("falls back to a date after a day", () => {
    expect(timeAgo("2026-10-20T12:00:00Z", now)).toMatch(/Oct 20/);
  });
});
