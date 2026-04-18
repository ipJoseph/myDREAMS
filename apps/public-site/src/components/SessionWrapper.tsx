"use client";

/**
 * Session wrapper for the public site.
 *
 * Previously used NextAuth's SessionProvider. Now a passthrough since
 * Supabase Auth manages sessions via its own SDK (cookies + JWT).
 * The component is kept to avoid changing every layout import.
 */
export default function SessionWrapper({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
