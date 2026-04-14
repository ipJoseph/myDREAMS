/**
 * Client-side event tracker for wncmountain.homes.
 *
 * Fires behavioral events to POST /api/public/events. These events flow
 * into dreams.db locally AND to FUB via the adapter — replacing the Real
 * Geeks IDX activity feed that JonTharpHomes.com used to provide.
 *
 * Usage:
 *   import { trackPropertyView, trackSearch, trackPageView } from "@/lib/track";
 *   trackPropertyView("lst_abc123", "jane@example.com");
 *
 * Events are fire-and-forget: failures are logged but never block the UI.
 * Anonymous users (no email) get a silent 200 from the API but no local
 * storage — the FUB pixel handles anonymous visitor tracking separately.
 */

const TRACK_ENDPOINT = "/api/public/events";

// Dedupe: don't fire the same event twice in one session
const _fired = new Set<string>();

function dedupeKey(event: string, listingId?: string): string {
  return `${event}:${listingId || "none"}`;
}

async function sendEvent(payload: Record<string, string | undefined>): Promise<void> {
  try {
    await fetch(TRACK_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      keepalive: true, // survive page navigation
    });
  } catch {
    // Fire-and-forget: never block the UI
  }
}

/**
 * Get the current user's email from the session, if available.
 * Returns undefined for anonymous visitors.
 */
function getSessionEmail(): string | undefined {
  // Next.js stores session in a cookie that's httpOnly, so we can't read it
  // directly. Instead, the email is passed as a prop from the server component
  // to the tracker component. This function is a fallback for cases where the
  // email is stored in localStorage (e.g., after form submission).
  if (typeof window === "undefined") return undefined;
  try {
    return localStorage.getItem("dreams_track_email") || undefined;
  } catch {
    return undefined;
  }
}

/**
 * Store email for tracking (called after form submission or login).
 * This lets us track behavioral events for users who gave us their email
 * via the contact form but aren't "logged in" per NextAuth.
 */
export function setTrackingEmail(email: string): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem("dreams_track_email", email.toLowerCase());
  } catch {
    // localStorage unavailable
  }
}

// ---------------------------------------------------------------------------
// Public tracking functions
// ---------------------------------------------------------------------------

/**
 * Track a property detail page view.
 * Called on mount of /listings/[id].
 */
export function trackPropertyView(
  listingId: string,
  email?: string,
): void {
  const key = dedupeKey("viewed_property", listingId);
  if (_fired.has(key)) return;
  _fired.add(key);

  const resolvedEmail = email || getSessionEmail();
  sendEvent({
    event: "viewed_property",
    email: resolvedEmail,
    listing_id: listingId,
    page_url: typeof window !== "undefined" ? window.location.pathname : undefined,
    page_title: typeof document !== "undefined" ? document.title : undefined,
  });
}

/**
 * Track a property save/favorite action.
 */
export function trackPropertySave(
  listingId: string,
  email?: string,
): void {
  const resolvedEmail = email || getSessionEmail();
  sendEvent({
    event: "saved_property",
    email: resolvedEmail,
    listing_id: listingId,
    page_url: typeof window !== "undefined" ? window.location.pathname : undefined,
  });
}

/**
 * Track a property search submission.
 * Called when the user submits search filters on /listings.
 */
export function trackSearch(email?: string): void {
  const key = dedupeKey("property_search", typeof window !== "undefined" ? window.location.search : "");
  if (_fired.has(key)) return;
  _fired.add(key);

  const resolvedEmail = email || getSessionEmail();
  sendEvent({
    event: "property_search",
    email: resolvedEmail,
    page_url: typeof window !== "undefined" ? window.location.pathname + window.location.search : undefined,
  });
}

/**
 * Track first visit to the website in this session.
 * Should be called once per session (e.g., in the layout).
 */
export function trackVisit(email?: string): void {
  const key = dedupeKey("visited_website", "session");
  if (_fired.has(key)) return;
  _fired.add(key);

  const resolvedEmail = email || getSessionEmail();
  if (!resolvedEmail) return; // Anonymous first visits are handled by FUB pixel

  sendEvent({
    event: "visited_website",
    email: resolvedEmail,
    page_url: typeof window !== "undefined" ? window.location.pathname : undefined,
    page_title: typeof document !== "undefined" ? document.title : undefined,
  });
}

/**
 * Track a generic page view (non-listing pages).
 */
export function trackPageView(email?: string): void {
  const resolvedEmail = email || getSessionEmail();
  if (!resolvedEmail) return; // Anonymous page views handled by FUB pixel

  sendEvent({
    event: "viewed_page",
    email: resolvedEmail,
    page_url: typeof window !== "undefined" ? window.location.pathname : undefined,
    page_title: typeof document !== "undefined" ? document.title : undefined,
  });
}
