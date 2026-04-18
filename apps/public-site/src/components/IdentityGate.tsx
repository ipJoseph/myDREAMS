"use client";

import { useState, useEffect, useCallback, type ReactNode } from "react";
import { createClient } from "@/lib/supabase";
import AuthModal from "./AuthModal";
import type { User } from "@supabase/supabase-js";

interface IdentityGateProps {
  children: ReactNode;
  requireAuth?: boolean;
  onAuthenticated?: () => void;
  defaultTab?: "login" | "register";
  fallback?: ReactNode;
}

/**
 * Wraps any action that requires a user account (Tier B).
 * Uses Supabase Auth instead of NextAuth.
 */
export default function IdentityGate({
  children,
  requireAuth = true,
  onAuthenticated,
  defaultTab = "register",
  fallback,
}: IdentityGateProps) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);

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

  const handleClick = useCallback(
    (e: React.MouseEvent) => {
      if (!requireAuth || user) return;
      e.preventDefault();
      e.stopPropagation();
      setShowModal(true);
    },
    [requireAuth, user],
  );

  const handleClose = useCallback(() => {
    setShowModal(false);
    if (onAuthenticated && user) {
      onAuthenticated();
    }
  }, [onAuthenticated, user]);

  if (loading) return <>{children}</>;
  if (!requireAuth || user) return <>{children}</>;

  return (
    <>
      <div onClick={handleClick} style={{ cursor: "pointer" }}>
        {fallback || children}
      </div>
      <AuthModal
        isOpen={showModal}
        onClose={handleClose}
        defaultTab={defaultTab}
      />
    </>
  );
}
