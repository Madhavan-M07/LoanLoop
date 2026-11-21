// DEV ONLY. The demo identities from backend/demo/demo_data.json (synthetic people, dev tokens
// that only exist in the demo file; the backend refuses demo data in prod). Real sign-in
// replaces this picker when auth lands.

export interface DemoUser {
  token: string;
  name: string;
  role: string;
  note: string;
  home: string;
}

export const DEMO_USERS: DemoUser[] = [
  {
    token: "dev-processor-acme",
    name: "Anita",
    role: "Processor · Acme Mortgage (admin)",
    note: "Sees Acme's loan files and approves borrower messages.",
    home: "/loans",
  },
  {
    token: "dev-processor-beta",
    name: "Ravi",
    role: "Processor · Beta Lending",
    note: "Different brokerage: must never see Acme's files.",
    home: "/loans",
  },
  {
    token: "dev-borrower-priya",
    name: "Priya Sharma",
    role: "Borrower · loan L-1001",
    note: "Uploads her documents and sees only her own loan.",
    home: "/upload",
  },
  {
    token: "dev-borrower-john",
    name: "John Carter",
    role: "Borrower · loan L-1002",
    note: "A second borrower at Acme.",
    home: "/upload",
  },
  {
    token: "dev-hermes-acme",
    name: "Hermes (AI agent)",
    role: "Processor agent · Acme",
    note: "Can read and draft, but can never approve or send.",
    home: "/loans",
  },
];

export function demoUser(token: string | null): DemoUser | undefined {
  return DEMO_USERS.find((u) => u.token === token);
}
