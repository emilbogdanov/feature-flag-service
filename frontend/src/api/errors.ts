import { ApiError } from "./client";

// A sentence for people, for any error a request can end in.
export function describeError(error: unknown): string {
  if (error instanceof ApiError && error.status === 412) {
    return "Someone changed this flag after it was loaded here. The page now shows their change; check it, then try again.";
  }
  if (error instanceof ApiError) {
    return sentence(error.message);
  }
  // fetch rejects with a TypeError when no response arrives at all.
  if (error instanceof TypeError) {
    return "The API can't be reached. Check that it's running, then try again.";
  }
  return error instanceof Error ? sentence(error.message) : "Something unexpected went wrong.";
}

export function isUnauthorized(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}

// The flag changed after the version the edit was based on was read.
export function isConflict(error: unknown): boolean {
  return error instanceof ApiError && error.status === 412;
}

export function hasCode(error: unknown, code: string): boolean {
  return error instanceof ApiError && error.code === code;
}

// The API's messages are phrases, such as "project 'shop' does not exist".
function sentence(message: string): string {
  const capitalized = message.charAt(0).toUpperCase() + message.slice(1);
  return /[.!?]$/.test(capitalized) ? capitalized : `${capitalized}.`;
}
