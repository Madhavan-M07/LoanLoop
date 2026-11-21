// Friendly names for the GENERATED API types (schema.d.ts, from backend OpenAPI via
// `npm run gen:api`). Never hand-write API shapes: change the backend, regenerate.
import type { components } from "./schema";

type S = components["schemas"];

export type Principal = S["Principal"];
export type LoanSummary = S["LoanSummary"];
export type LoanFile = S["LoanFile"];
export type Loan = S["Loan"];
export type LoanDocument = S["Document"];
export type Evidence = S["Evidence"];
export type RuleResult = S["RuleResult"];
export type MessageDraft = S["MessageDraft"];
export type AuditEvent = S["AuditEvent"];
export type LoanStatus = S["LoanStatus"];
export type LoanStage = S["LoanStage"];
export type DocStatus = S["DocStatus"];
export type DocType = S["DocType"];
export type Severity = S["Severity"];
export type DraftStatus = S["DraftStatus"];
