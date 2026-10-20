import { describe, expect, expectTypeOf, it } from "vitest";

import { ApiError, createApiClient, unwrap } from "./client";
import type { ProjectResponse } from "./schema";

const project: ProjectResponse = {
  key: "storefront",
  name: "Storefront",
  created_at: "2026-10-20T09:00:00Z",
};

// Answers every request with one canned response and keeps the requests for inspection.
function answering(status: number, body: unknown, statusText = "") {
  const requests: Request[] = [];
  const fetch = (request: Request) => {
    requests.push(request);
    const text = body === undefined || typeof body === "string" ? body : JSON.stringify(body);
    return Promise.resolve(
      new Response(text, {
        status,
        statusText,
        headers: {
          "Content-Type": "application/json",
          "Content-Length": String(text?.length ?? 0),
        },
      }),
    );
  };
  const client = createApiClient({
    baseUrl: "http://flagstaff.test",
    adminKey: "fs_admin_x",
    fetch,
  });
  return { client, requests };
}

describe("createApiClient", () => {
  it("sends the admin key as a bearer token", async () => {
    const { client, requests } = answering(200, [project]);

    await client.GET("/projects");

    expect(requests).toHaveLength(1);
    expect(requests[0]?.url).toBe("http://flagstaff.test/projects");
    expect(requests[0]?.headers.get("Authorization")).toBe("Bearer fs_admin_x");
  });

  it("fills in path parameters", async () => {
    const { client, requests } = answering(200, project);

    await client.GET("/projects/{project_key}", {
      params: { path: { project_key: "store front" } },
    });

    expect(requests[0]?.url).toBe("http://flagstaff.test/projects/store%20front");
  });
});

describe("unwrap", () => {
  it("returns the data of a successful response, typed from the schema", async () => {
    const { client } = answering(200, [project]);

    const projects = await unwrap(client.GET("/projects"));

    expectTypeOf(projects).toEqualTypeOf<ProjectResponse[]>();
    expect(projects).toEqual([project]);
  });

  it("turns the API's error body into an ApiError", async () => {
    const { client } = answering(404, { detail: "no project 'nope'", code: "project_not_found" });

    const failure = unwrap(
      client.GET("/projects/{project_key}", { params: { path: { project_key: "nope" } } }),
    );

    await expect(failure).rejects.toThrow(ApiError);
    await expect(failure).rejects.toMatchObject({
      status: 404,
      code: "project_not_found",
      message: "no project 'nope'",
    });
  });

  it("reports a response that didn't come from the API by its status", async () => {
    const { client } = answering(502, "<html>Bad Gateway</html>", "Bad Gateway");

    await expect(unwrap(client.GET("/projects"))).rejects.toMatchObject({
      status: 502,
      code: "unexpected_response",
      message: "The server answered 502 Bad Gateway",
    });
  });

  it("reports an error response without a body by its status", async () => {
    const { client } = answering(503, undefined, "Service Unavailable");

    await expect(unwrap(client.GET("/projects"))).rejects.toMatchObject({
      status: 503,
      code: "unexpected_response",
      message: "The server answered 503 Service Unavailable",
    });
  });
});
