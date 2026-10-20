const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium" });

export function formatDate(timestamp: string): string {
  return dateFormat.format(new Date(timestamp));
}
