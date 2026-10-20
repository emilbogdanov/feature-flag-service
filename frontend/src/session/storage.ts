const STORAGE_KEY = "flagstaff.adminKey";

// Session storage, not local storage: an admin key can change anything, so it is kept for as long
// as the tab is open rather than for as long as the browser profile exists. Storage can be
// unavailable (a locked-down browser, a private window), in which case the key lasts until reload.

export function readStoredKey(): string | null {
  try {
    return sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function storeKey(adminKey: string): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, adminKey);
  } catch {
    // Kept in memory only.
  }
}

export function forgetStoredKey(): void {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Nothing was stored.
  }
}
