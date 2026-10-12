import { setupServer } from "msw/node";

import { handlers } from "./handlers";

/** MSW server shared by every test; started and reset in setup.ts. */
export const server = setupServer(...handlers);
