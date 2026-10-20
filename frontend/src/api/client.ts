import createClient, { type Client } from "openapi-fetch";

import type { ErrorResponse, paths } from "./schema";

export type ApiClient = Client<paths>;

export interface ApiClientOptions {
  baseUrl: string;
  adminKey: string;
  fetch?: (request: Request) => Promise<Response>;
}

export function createApiClient({ baseUrl, adminKey, fetch }: ApiClientOptions): ApiClient {
  return createClient<paths>({
    baseUrl,
    headers: { Authorization: `Bearer ${adminKey}` },
    ...(fetch && { fetch }),
  });
}

// Every error the API itself sends has a stable code to branch on and a message meant for people.
export class ApiError extends Error {
  override readonly name = "ApiError";
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }

  static fromResponse(response: Response, body: unknown): ApiError {
    if (isErrorResponse(body)) {
      return new ApiError(response.status, body.code, body.detail);
    }
    // Not the API's own answer: a proxy in front of it failed, or the body was cut short.
    return new ApiError(
      response.status,
      "unexpected_response",
      `The server answered ${String(response.status)} ${response.statusText}`.trimEnd(),
    );
  }
}

interface Outcome {
  data?: unknown;
  error?: unknown;
  response: Response;
}

// openapi-fetch resolves with either data or an error body. Components want the data or an
// exception, so a failed request reaches the nearest error boundary or query error state.
export async function unwrap<R extends Outcome>(
  pending: Promise<R>,
): Promise<Exclude<R["data"], undefined>> {
  const { data, error, response } = await pending;
  // The status decides, not the error: an error response without a body leaves it undefined.
  if (!response.ok) {
    throw ApiError.fromResponse(response, error);
  }
  // Every endpoint the dashboard calls answers success with a body.
  return data as Exclude<R["data"], undefined>;
}

function isErrorResponse(body: unknown): body is ErrorResponse {
  return (
    typeof body === "object" &&
    body !== null &&
    "code" in body &&
    typeof body.code === "string" &&
    "detail" in body &&
    typeof body.detail === "string"
  );
}
