import { formatValue, humanize } from "@/lib/format";
import type { Evidence, LoanDocument } from "@/lib/api/types";

/**
 * Every AI-extracted value is shown next to the document text it came from. A value with no
 * source snippet is flagged for manual checking: it may be right, but nobody can see why.
 */
export function ExtractedFields({ fields }: { fields: NonNullable<LoanDocument["fields"]> }) {
  const evidence: Evidence[] = fields.evidence ?? [];
  const byField = new Map(evidence.map((e) => [e.field, e.snippet]));
  const rows = Object.entries(fields).filter(([k]) => k !== "evidence");

  return (
    <table className="w-full text-left text-sm">
      <caption className="sr-only">Extracted fields with source evidence</caption>
      <thead>
        <tr className="border-b border-slate-100 text-xs uppercase tracking-wide text-slate-500">
          <th scope="col" className="py-2 pr-4 font-medium">
            Field
          </th>
          <th scope="col" className="py-2 pr-4 font-medium">
            Value
          </th>
          <th scope="col" className="py-2 font-medium">
            Source in document
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.map(([key, value]) => {
          const snippet = byField.get(key);
          return (
            <tr key={key} className="border-b border-slate-50 align-top last:border-0">
              <td className="py-2 pr-4 text-slate-600">{humanize(key)}</td>
              <td className="py-2 pr-4 font-medium tabular-nums text-slate-900">
                {formatValue(value)}
              </td>
              <td className="py-2">
                {snippet ? (
                  <code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-700">
                    {snippet}
                  </code>
                ) : (
                  <span className="text-xs text-amber-700">No source snippet: verify manually</span>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
