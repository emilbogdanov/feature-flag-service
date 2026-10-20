// Joins class names, skipping the ones a condition left out. CSS module lookups are typed as
// possibly undefined, so they can be passed straight in.
export function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}
