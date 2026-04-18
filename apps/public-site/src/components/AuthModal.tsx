"use client";

import { useState, useEffect } from "react";
import { createClient } from "@/lib/supabase";
import { setTrackingEmail } from "@/lib/track";

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  defaultTab?: "login" | "register";
}

/**
 * Authentication modal using Supabase Auth.
 *
 * Replaces the old NextAuth + Flask dual-auth system. Supabase handles
 * registration, login, OAuth, password reset, and email verification.
 *
 * See docs/DECISIONS.md #0.
 */
export default function AuthModal({ isOpen, onClose, defaultTab = "login" }: AuthModalProps) {
  const [tab, setTab] = useState<"login" | "register" | "reset">(defaultTab);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  // Pre-fill email from contact form submission (Tier A → Tier B upgrade)
  useEffect(() => {
    if (isOpen && !email) {
      try {
        const savedEmail = localStorage.getItem("dreams_track_email");
        if (savedEmail) {
          setEmail(savedEmail);
          setTab("register");
        }
      } catch {
        // localStorage unavailable
      }
    }
  }, [isOpen]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!isOpen) return null;

  const supabase = createClient();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setMessage("");
    setLoading(true);

    try {
      if (tab === "register") {
        const { data, error: signUpError } = await supabase.auth.signUp({
          email,
          password,
          options: {
            data: {
              name,
              phone: phone || undefined,
            },
          },
        });

        if (signUpError) {
          setError(signUpError.message);
          setLoading(false);
          return;
        }

        // Store email for tracking (Tier A → Tier B path)
        if (email) setTrackingEmail(email);

        // Link to local lead via the API (best-effort)
        try {
          await fetch("/api/public/contacts", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              name,
              email,
              phone: phone || undefined,
              source: "registration",
            }),
          });
        } catch {
          // Best-effort; don't block auth on lead creation
        }

        if (data.session) {
          // Auto-confirmed (email verification disabled or already verified)
          onClose();
          window.location.reload();
        } else {
          // Email verification required
          setMessage("Check your email for a verification link. You can close this dialog.");
          setLoading(false);
        }
        return;

      } else if (tab === "login") {
        const { error: signInError } = await supabase.auth.signInWithPassword({
          email,
          password,
        });

        if (signInError) {
          setError(signInError.message);
          setLoading(false);
          return;
        }

        onClose();
        window.location.reload();
        return;

      } else if (tab === "reset") {
        const { error: resetError } = await supabase.auth.resetPasswordForEmail(
          email,
          { redirectTo: `${window.location.origin}/account` }
        );

        if (resetError) {
          setError(resetError.message);
        } else {
          setMessage("Check your email for a password reset link.");
        }
        setLoading(false);
        return;
      }
    } catch {
      setError("Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleSignIn = async () => {
    const supabase = createClient();
    await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: `${window.location.origin}/auth/callback`,
      },
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />

      {/* Modal */}
      <div className="relative bg-white w-full max-w-md mx-4 shadow-2xl">
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 transition"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>

        <div className="p-8">
          <h2
            className="text-2xl text-[var(--color-primary)] mb-6"
            style={{ fontFamily: "Georgia, serif" }}
          >
            {tab === "login" ? "Welcome Back" : tab === "register" ? "Create Account" : "Reset Password"}
          </h2>

          {/* Tab switcher (hide on reset) */}
          {tab !== "reset" && (
            <div className="flex border-b border-gray-200 mb-6">
              <button
                onClick={() => { setTab("login"); setError(""); setMessage(""); }}
                className={`pb-3 px-4 text-sm font-medium uppercase tracking-wider transition ${
                  tab === "login"
                    ? "text-[var(--color-primary)] border-b-2 border-[var(--color-accent)]"
                    : "text-gray-400 hover:text-gray-600"
                }`}
              >
                Sign In
              </button>
              <button
                onClick={() => { setTab("register"); setError(""); setMessage(""); }}
                className={`pb-3 px-4 text-sm font-medium uppercase tracking-wider transition ${
                  tab === "register"
                    ? "text-[var(--color-primary)] border-b-2 border-[var(--color-accent)]"
                    : "text-gray-400 hover:text-gray-600"
                }`}
              >
                Register
              </button>
            </div>
          )}

          {/* Google OAuth — only shown when configured in Supabase dashboard.
              Set NEXT_PUBLIC_GOOGLE_AUTH_ENABLED=true in .env to show. */}
          {tab !== "reset" && process.env.NEXT_PUBLIC_GOOGLE_AUTH_ENABLED === "true" && (
            <>
              <button
                onClick={handleGoogleSignIn}
                className="w-full flex items-center justify-center gap-3 py-3 border border-gray-300 text-sm font-medium text-gray-700 hover:bg-gray-50 transition mb-6"
              >
                <svg className="w-5 h-5" viewBox="0 0 24 24">
                  <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" />
                  <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                  <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
                  <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
                </svg>
                Continue with Google
              </button>

              <div className="relative mb-6">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-gray-200" />
                </div>
                <div className="relative flex justify-center text-sm">
                  <span className="bg-white px-4 text-gray-400">or</span>
                </div>
              </div>
            </>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit} autoComplete="off">
            {tab === "register" && (
              <div className="mb-4">
                <label className="block text-xs text-[var(--color-text-light)] uppercase tracking-wider mb-1">
                  Name
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  autoComplete="name"
                  className="w-full px-4 py-3 border border-gray-300 text-sm focus:outline-none focus:border-[var(--color-accent)] transition"
                  placeholder="Your name"
                />
              </div>
            )}

            {tab === "register" && (
              <div className="mb-4">
                <label className="block text-xs text-[var(--color-text-light)] uppercase tracking-wider mb-1">
                  Phone <span className="normal-case text-gray-400 tracking-normal">(optional, helps us reach you faster)</span>
                </label>
                <input
                  type="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  autoComplete="tel"
                  className="w-full px-4 py-3 border border-gray-300 text-sm focus:outline-none focus:border-[var(--color-accent)] transition"
                  placeholder="(828) 555-1234"
                />
              </div>
            )}

            <div className="mb-4">
              <label className="block text-xs text-[var(--color-text-light)] uppercase tracking-wider mb-1">
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete={tab === "register" ? "off" : "email"}
                className="w-full px-4 py-3 border border-gray-300 text-sm focus:outline-none focus:border-[var(--color-accent)] transition"
                placeholder="you@example.com"
              />
            </div>

            {tab !== "reset" && (
              <div className="mb-6">
                <label className="block text-xs text-[var(--color-text-light)] uppercase tracking-wider mb-1">
                  Password
                </label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={6}
                  autoComplete={tab === "register" ? "new-password" : "current-password"}
                  className="w-full px-4 py-3 border border-gray-300 text-sm focus:outline-none focus:border-[var(--color-accent)] transition"
                  placeholder={tab === "register" ? "At least 6 characters" : "Your password"}
                />
              </div>
            )}

            {error && (
              <p className="text-red-600 text-sm mb-4 uppercase tracking-wide">{error}</p>
            )}

            {message && (
              <p className="text-green-600 text-sm mb-4">{message}</p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 bg-[var(--color-accent)] text-[var(--color-primary)] font-semibold text-sm uppercase tracking-wider hover:bg-[var(--color-accent-hover)] transition disabled:opacity-50"
            >
              {loading
                ? "Please wait..."
                : tab === "login"
                  ? "Sign In"
                  : tab === "register"
                    ? "Create Account"
                    : "Send Reset Link"}
            </button>
          </form>

          {/* Footer links */}
          <div className="mt-4 text-center">
            {tab === "login" && (
              <button
                onClick={() => { setTab("reset"); setError(""); setMessage(""); }}
                className="text-xs text-gray-400 hover:text-[var(--color-accent)] transition"
              >
                Forgot your password?
              </button>
            )}
            {tab === "reset" && (
              <button
                onClick={() => { setTab("login"); setError(""); setMessage(""); }}
                className="text-xs text-gray-400 hover:text-[var(--color-accent)] transition"
              >
                Back to Sign In
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
