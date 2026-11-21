import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Unmount between tests (automatic only when vitest globals are on, which we keep off).
afterEach(cleanup);
