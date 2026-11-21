import { describe, expect, it } from "vitest";

import { SAMPLE_LABELS, buildSample, todayIso, type SampleKind } from "./samples";

const opts = { name: "Priya Sharma", date: "2026-11-14", taxYear: 2025 };

describe("synthetic samples", () => {
  it.each(Object.keys(SAMPLE_LABELS) as SampleKind[])("%s uses the chosen name", (kind) => {
    expect(buildSample(kind, opts)).toContain("Priya Sharma");
  });

  it("puts the chosen date on paystubs and bank statements", () => {
    expect(buildSample("paystub", opts)).toContain("Pay Date: 2026-11-14");
    expect(buildSample("bank_statement", opts)).toContain("Statement End: 2026-11-14");
  });

  it("only ever uses the reserved example SSN (synthetic data only)", () => {
    for (const kind of Object.keys(SAMPLE_LABELS) as SampleKind[]) {
      const ssns = buildSample(kind, opts).match(/\d{3}-\d{2}-\d{4}/g) ?? [];
      expect(ssns.every((s) => s === "123-45-6789")).toBe(true);
    }
  });

  it("formats today as YYYY-MM-DD", () => {
    expect(todayIso(new Date(2026, 0, 5))).toBe("2026-01-05");
  });
});
