import { setupServer } from "msw/node";

// Each test installs the API answers it needs; a request nobody planned for fails the test.
export const server = setupServer();
