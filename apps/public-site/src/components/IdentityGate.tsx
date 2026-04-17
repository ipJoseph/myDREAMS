"use client";

import { useSession } from "next-auth/react";
import { useState, useCallback, type ReactNode } from "react";
import AuthModal from "./AuthModal";

interface IdentityGateProps {
  /** What to render when the user is authenticated (or doesn't need auth). */
  children: ReactNode;
  /** If true, require a full user account (Tier B). If false, the gate is a no-op. */
  requireAuth?: boolean;
  /** Callback fired after successful authentication. */
  onAuthenticated?: () => void;
  /** Which tab to default to in the auth modal. */
  defaultTab?: "login" | "register";
  /** Custom trigger button. If provided, wraps the children in this instead. */
  fallback?: ReactNode;
}

/**
 * Wraps any action that requires a user account.
 *
 * Usage:
 *   <IdentityGate requireAuth>
 *     <button onClick={addToCollection}>Add to Collection</button>
 *   </IdentityGate>
 *
 * If the user is logged in, children render normally.
 * If not, clicking the children opens the auth modal instead.
 * After successful auth, the original action proceeds.
 */
export default function IdentityGate({
  children,
  requireAuth = true,
  onAuthenticated,
  defaultTab = "register",
  fallback,
}: IdentityGateProps) {
  const { data: session, status } = useSession();
  const [showModal, setShowModal] = useState(false);

  const handleClick = useCallback(
    (e: React.MouseEvent) => {
      if (!requireAuth || session) return; // Authenticated or no auth needed
      e.preventDefault();
      e.stopPropagation();
      setShowModal(true);
    },
    [requireAuth, session],
  );

  const handleClose = useCallback(() => {
    setShowModal(false);
    // After modal closes successfully (page reloads on auth success),
    // the onAuthenticated callback fires on next render when session exists.
    if (onAuthenticated && session) {
      onAuthenticated();
    }
  }, [onAuthenticated, session]);

  // If auth not required or user is logged in, render children directly
  if (!requireAuth || session) {
    return <>{children}</>;
  }

  // Not logged in and auth required: intercept clicks
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
