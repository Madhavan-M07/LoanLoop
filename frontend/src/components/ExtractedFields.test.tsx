import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { components } from "@/lib/api/schema";

import { ExtractedFields } from "./ExtractedFields";

const paystub: components["schemas"]["PaystubFields"] = {
  employee_name: "Priya Sharma",
  employer_name: "Acme Robotics Inc.",
  pay_date: "2026-11-14",
  pay_frequency: "biweekly",
  gross_pay: "3200.00",
  net_pay: "2450.18",
  ytd_gross: "60800.00",
  evidence: [{ field: "gross_pay", snippet: "Gross Pay: $3,200.00" }],
};

describe("ExtractedFields", () => {
  it("shows each AI value next to the document text it came from", () => {
    render(<ExtractedFields fields={paystub} />);
    const row = screen.getByText("Gross pay").closest("tr");
    expect(row).toHaveTextContent("3200.00");
    expect(row).toHaveTextContent("Gross Pay: $3,200.00");
  });

  it("flags values with no source snippet for manual checking", () => {
    render(<ExtractedFields fields={paystub} />);
    const row = screen.getByText("Net pay").closest("tr");
    expect(row).toHaveTextContent("No source snippet: verify manually");
  });

  it("never renders the evidence list itself as a field", () => {
    render(<ExtractedFields fields={paystub} />);
    expect(screen.queryByText("Evidence")).not.toBeInTheDocument();
  });
});
