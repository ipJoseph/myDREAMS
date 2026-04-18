/**
 * Supabase client for the public website.
 *
 * We use Supabase ONLY for Auth (not their database). Our PostgreSQL
 * stays on the VPS. Supabase handles user accounts, sessions, OAuth,
 * magic links, email verification, and password reset.
 *
 * See docs/DECISIONS.md #0 for the rationale.
 *
 * Usage:
 *   import { supabase } from "@/lib/supabase";
 *   const { data, error } = await supabase.auth.signUp({ email, password });
 */

import { createBrowserClient } from "@supabase/ssr";

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;

if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
  console.warn(
    "Supabase credentials not configured. Auth features will not work. " +
    "Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY in .env"
  );
}

/**
 * Browser-side Supabase client. Use this in "use client" components.
 * Automatically handles session cookies via @supabase/ssr.
 */
export function createClient() {
  return createBrowserClient(
    SUPABASE_URL || "",
    SUPABASE_ANON_KEY || "",
  );
}

/**
 * Convenience export for components that just need a quick client.
 */
export const supabase = typeof window !== "undefined"
  ? createClient()
  : null;
