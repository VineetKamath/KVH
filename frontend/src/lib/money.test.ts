import { describe, expect, it } from "vitest";
import { addDays, daysBetween } from "./dates";
import { diff, formatMoney, sumMoney } from "./money";

describe("money formatting (R3: strings in, strings out)", () => {
  it("formats INR with Indian grouping", () => {
    expect(formatMoney("123456.70", "INR", "en-IN")).toMatch(/1,23,456\.70/);
  });
  it("uses native digits for Hindi and Kannada without changing the value", () => {
    const hi = formatMoney("5200.00", "INR", "hi");
    const kn = formatMoney("5200.00", "INR", "kn");
    expect(hi).toMatch(/[०-९]/);
    expect(kn).toMatch(/[೦-೯]/);
    const back = (s: string) => s.replace(/[०-९]/g, (c) => String("०१२३४५६७८९".indexOf(c)))
      .replace(/[೦-೯]/g, (c) => String("೦೧೨೩೪೫೬೭೮೯".indexOf(c))).replace(/[^\d.]/g, "");
    expect(back(hi)).toBe("5200.00");
    expect(back(kn)).toBe("5200.00");
  });
  it("respects zero-decimal currencies", () => {
    expect(formatMoney("1500.00", "JPY", "en-IN")).not.toMatch(/\.00/);
  });
  it("adds money exactly (no float drift)", () => {
    expect(sumMoney(["0.10", "0.20"])).toBe("0.30");
    expect(diff("5200.00", "4887.60")).toBe("+312.40");
  });
});

describe("zoneless dates", () => {
  it("adds days across month ends and measures spans", () => {
    expect(addDays("2026-10-31", 1)).toBe("2026-11-01");
    expect(daysBetween("2026-08-31", "2026-11-29")).toBe(90);
  });
});
