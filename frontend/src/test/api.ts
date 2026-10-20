import { HttpResponse, http } from "msw";

import type { FlagResponse } from "../api/schema";
import { newCheckout, storefront, storefrontEnvironments } from "./fixtures";
import { server } from "./server";

// The storefront project as the API would answer for it, with these flags in it.
export function serveStorefront(flags: FlagResponse[] = [newCheckout]) {
  server.use(
    http.get("*/projects/storefront", () => HttpResponse.json(storefront)),
    http.get("*/projects/storefront/environments", () => HttpResponse.json(storefrontEnvironments)),
    http.get("*/projects/storefront/flags", () => HttpResponse.json(flags)),
    ...flags.map((flag) =>
      http.get(`*/projects/storefront/flags/${flag.key}`, () => HttpResponse.json(flag)),
    ),
  );
}

export const versionMismatch = {
  detail: "flag 'new-checkout' is at version 8, not 7",
  code: "version_mismatch",
};
