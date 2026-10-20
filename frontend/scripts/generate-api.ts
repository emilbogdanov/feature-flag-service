// Writes src/api/schema.ts from the OpenAPI document the backend's own command line produces.
// The file is committed, so the dashboard builds without Python; CI runs this script again and
// fails when the committed types no longer match the API.
import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import openapiTS, { astToString, COMMENT_HEADER } from "openapi-typescript";
import * as prettier from "prettier";

const backend = fileURLToPath(new URL("../../backend", import.meta.url));
const target = fileURLToPath(new URL("../src/api/schema.ts", import.meta.url));

const document = execFileSync("uv", ["run", "--quiet", "--locked", "flagstaff-server", "openapi"], {
  cwd: backend,
  encoding: "utf-8",
});

const ast = await openapiTS(document, {
  // Named exports such as ProjectResponse, next to the paths and components maps.
  rootTypes: true,
  rootTypesNoSchemaPrefix: true,
});
// Formatted like the rest of the code, so a regenerated file differs only where the API did.
const options = await prettier.resolveConfig(target);
const source = await prettier.format(COMMENT_HEADER + astToString(ast), {
  ...options,
  filepath: target,
});
writeFileSync(target, source);
