"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase";
import AuthModal from "./AuthModal";
import type { User } from "@supabase/supabase-js";

export default function UserMenu() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);

  useEffect(() => {
    const supabase = createClient();

    // Get initial session
    supabase.auth.getSession().then(({ data: { session } }) => {
      setUser(session?.user ?? null);
      setLoading(false);
    });

    // Listen for auth changes (login, logout, token refresh)
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (_event, session) => {
        setUser(session?.user ?? null);
      }
    );

    return () => subscription.unsubscribe();
  }, []);

  if (loading) return null;

  if (!user) {
    return (
      <>
        <button
          onClick={() => setShowModal(true)}
          className="text-white/80 hover:text-[var(--color-accent)] text-sm uppercase tracking-wide transition"
        >
          Sign In
        </button>
        <AuthModal isOpen={showModal} onClose={() => setShowModal(false)} />
      </>
    );
  }

  const displayName = user.user_metadata?.name || user.email || "Account";
  const initials = displayName
    .split(" ")
    .map((w: string) => w[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);

  const handleSignOut = async () => {
    const supabase = createClient();
    await supabase.auth.signOut();
    window.location.href = "/";
  };

  return (
    <div className="relative">
      <button
        onClick={() => setShowDropdown(!showDropdown)}
        className="flex items-center gap-2 text-white/80 hover:text-[var(--color-accent)] transition"
      >
        {user.user_metadata?.avatar_url ? (
          <img
            src={user.user_metadata.avatar_url}
            alt=""
            className="w-8 h-8 rounded-full border border-white/20"
          />
        ) : (
          <div className="w-8 h-8 rounded-full bg-[var(--color-accent)] text-[var(--color-primary)] flex items-center justify-center text-xs font-bold">
            {initials}
          </div>
        )}
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {showDropdown && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setShowDropdown(false)} />
          <div className="absolute right-0 top-full mt-2 w-56 bg-[var(--color-primary)] border border-white/10 shadow-2xl z-50">
            <div className="px-4 py-3 border-b border-white/10">
              <p className="text-white text-sm font-medium truncate">
                {displayName}
              </p>
              <p className="text-white/50 text-xs truncate">
                {user.email}
              </p>
            </div>
            <Link
              href="/account/favorites"
              className="block px-4 py-3 text-white/70 hover:text-[var(--color-accent)] text-sm transition"
              onClick={() => setShowDropdown(false)}
            >
              My Favorites
            </Link>
            <Link
              href="/account/searches"
              className="block px-4 py-3 text-white/70 hover:text-[var(--color-accent)] text-sm transition"
              onClick={() => setShowDropdown(false)}
            >
              Saved Searches
            </Link>
            <Link
              href="/account/collections"
              className="block px-4 py-3 text-white/70 hover:text-[var(--color-accent)] text-sm transition"
              onClick={() => setShowDropdown(false)}
            >
              My Collections
            </Link>
            <button
              onClick={handleSignOut}
              className="w-full text-left px-4 py-3 text-white/50 hover:text-red-400 text-sm border-t border-white/10 transition"
            >
              Sign Out
            </button>
          </div>
        </>
      )}
    </div>
  );
}
