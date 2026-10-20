import type { AuditAction, AuditEntryResponse } from "../api/schema";

const VERBS: Record<AuditAction, string> = {
  "project.created": "created the project",
  "environment.created": "added the environment",
  "flag.created": "created the flag",
  "flag.details_changed": "changed the name or description of",
  "flag.variants_changed": "changed the variants of",
  "flag.targeting_changed": "changed the targeting of",
  "flag.enabled": "turned on",
  "flag.disabled": "turned off",
  "flag.archived": "archived",
  "api_key.issued": "issued the API key",
  "api_key.revoked": "revoked the API key",
};

export interface DescribedAction {
  verb: string;
  subject: string;
  // Where it happened, as "storefront/prod", and the word that leads into it.
  place: { preposition: "in" | "for"; path: string } | null;
}

// What happened, without who did it. A log already filtered to one project leaves that project
// out of every line.
export function describeAction(
  entry: AuditEntryResponse,
  shownProject: string | null = null,
): DescribedAction {
  const verb = VERBS[entry.action];
  if (entry.action === "project.created") {
    return { verb, subject: entry.subject, place: null };
  }
  const project = entry.project === shownProject ? null : entry.project;
  const environment = entry.action === "environment.created" ? null : entry.environment;
  const path = [project, environment].filter((part) => part !== null).join("/");
  return {
    verb,
    subject: entry.subject,
    place:
      path === ""
        ? null
        : { preposition: entry.action.startsWith("api_key.") ? "for" : "in", path },
  };
}

const timeFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

export function formatTime(timestamp: string): string {
  return timeFormat.format(new Date(timestamp));
}
