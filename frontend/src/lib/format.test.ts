import { describe, expect, it } from "vitest";

import { daysAgo, describeChange, formatValue, humanize, percent } from "./format";

describe("describeChange", () => {
  it("shows what changed in an audit row", () => {
    expect(
      describeChange({ stage: "collecting_documents" }, { stage: "file_complete" }),
    ).toEqual(["Stage: collecting_documents → file_complete"]);
  });

  it("ignores unchanged keys and handles missing sides", () => {
    expect(describeChange({ a: 1, b: 2 }, { a: 1, b: 3 })).toEqual(["B: 2 → 3"]);
    expect(describeChange(null, { status: "sent" })).toEqual(["Status: — → sent"]);
    expect(describeChange(null, null)).toEqual([]);
  });
});

describe("formatValue", () => {
  it("keeps money exactly as the API sent it (no float rounding)", () => {
    expect(formatValue("3200.10")).toBe("3200.10");
  });

  it("shows an em dash for empty values", () => {
    expect(formatValue(null)).toBe("—");
    expect(formatValue("")).toBe("—");
    expect(formatValue([])).toBe("—");
  });
});

describe("small helpers", () => {
  it("humanizes snake_case field names", () => {
    expect(humanize("gross_pay")).toBe("Gross pay");
  });

  it("describes idle days", () => {
    expect(daysAgo(0)).toBe("today");
    expect(daysAgo(1)).toBe("1 day ago");
    expect(daysAgo(5)).toBe("5 days ago");
  });

  it("formats confidence as a percent", () => {
    expect(percent(0.857)).toBe("86%");
  });
});
