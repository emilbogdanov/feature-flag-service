// The engine's rule for flag, variant and rule keys: they end up in URLs, log lines and the
// "flag:user" string that bucketing hashes, so no ":" and nothing exotic.
const KEY_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const MAX_KEY_LENGTH = 128;

export const KEY_RULE =
  "Use up to 128 letters, digits, dots, underscores or hyphens, starting with a letter or digit.";

export function isValidKey(key: string): boolean {
  return KEY_PATTERN.test(key);
}

// A key suggested from a name, such as "new-checkout" for "New checkout".
export function keyFromName(name: string): string {
  return name
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, "-")
    .replace(/^[._-]+/, "")
    .slice(0, MAX_KEY_LENGTH)
    .replace(/-+$/, "");
}
