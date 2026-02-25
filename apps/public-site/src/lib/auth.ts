/**
 * Auth.js v5 configuration for wncmountain.homes.
 *
 * Supports:
 *   - Email/password (Credentials provider)
 *   - Google OAuth
 *
 * Uses a custom SQLite adapter that talks to the dreams.db database
 * via the Flask API (so the Next.js app never opens SQLite directly).
 */

import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";
import Google from "next-auth/providers/google";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [
    Credentials({
      name: "Email",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        if (!credentials?.email || !credentials?.password) return null;

        try {
          const res = await fetch(`${API_BASE}/api/user/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              email: credentials.email,
              password: credentials.password,
            }),
          });

          if (!res.ok) return null;

          const data = await res.json();
          if (!data.success) return null;

          return {
            id: data.data.id,
            email: data.data.email,
            name: data.data.name,
            image: data.data.avatar_url,
          };
        } catch {
          return null;
        }
      },
    }),
    Google({
      clientId: process.env.GOOGLE_CLIENT_ID,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET,
    }),
  ],

  pages: {
    signIn: "/auth/signin",
    error: "/auth/error",
  },

  session: {
    strategy: "jwt",
    maxAge: 30 * 24 * 60 * 60, // 30 days
  },

  callbacks: {
    async jwt({ token, user, account }) {
      // On initial sign-in, persist user data into the JWT
      if (user) {
        token.id = user.id;
      }

      // For Google OAuth, sync the user to our backend
      if (account?.provider === "google" && user) {
        try {
          const res = await fetch(`${API_BASE}/api/user/oauth-sync`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              provider: "google",
              provider_account_id: account.providerAccountId,
              email: user.email,
              name: user.name,
              avatar_url: user.image,
            }),
          });
          if (res.ok) {
            const data = await res.json();
            if (data.success) {
              token.id = data.data.id;
            }
          }
        } catch {
          // Non-fatal: user can still browse, just won't be linked
        }
      }

      return token;
    },

    async session({ session, token }) {
      if (session.user && token.id) {
        session.user.id = token.id as string;
      }
      return session;
    },
  },

  trustHost: true,
});
