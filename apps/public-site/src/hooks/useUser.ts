"use client";

/**
 * Supabase-based user hook. Drop-in replacement for NextAuth's useSession().
 *
 * Usage:
 *   const { user, loading } = useUser();
 *   if (loading) return null;
 *   if (!user) return <SignInPrompt />;
 *   return <p>Hello {user.email}</p>;
 */

import { useState, useEffect } from "react";
import { createClient } from "@/lib/supabase";
import type { User } from "@supabase/supabase-js";

export function useUser() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const supabase = createClient();

    supabase.auth.getSession().then(({ data: { session } }) => {
      setUser(session?.user ?? null);
      setLoading(false);
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (_event, session) => {
        setUser(session?.user ?? null);
      }
    );

    return () => subscription.unsubscribe();
  }, []);

  // Return a shape similar to NextAuth's useSession for easy migration
  return {
    user,
    loading,
    // Convenience accessors matching the old session.user shape
    session: user ? {
      user: {
        id: user.id,
        email: user.email,
        name: user.user_metadata?.name,
        image: user.user_metadata?.avatar_url,
      }
    } : null,
  };
}
