"use client";

import { useState } from "react";
import { useSession } from "next-auth/react";
import AuthModal from "./AuthModal";

interface FavoriteButtonProps {
  listingId: string;
  initialFavorited?: boolean;
  size?: "sm" | "md";
}

export default function FavoriteButton({
  listingId,
  initialFavorited = false,
  size = "sm",
}: FavoriteButtonProps) {
  const { data: session } = useSession();
  const [isFavorited, setIsFavorited] = useState(initialFavorited);
  const [loading, setLoading] = useState(false);
  const [showAuth, setShowAuth] = useState(false);

  const iconSize = size === "sm" ? "w-5 h-5" : "w-6 h-6";
  const buttonSize = size === "sm" ? "p-2" : "p-3";

  const handleToggle = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();

    if (!session) {
      setShowAuth(true);
      return;
    }

    setLoading(true);
    try {
      if (isFavorited) {
        await fetch(`/api/user/favorites/${listingId}`, {
          method: "DELETE",
        });
        setIsFavorited(false);
      } else {
        await fetch("/api/user/favorites", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ listing_id: listingId }),
        });
        setIsFavorited(true);
      }
    } catch {
      // Silently fail
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <button
        onClick={handleToggle}
        disabled={loading}
        className={`${buttonSize} bg-black/40 hover:bg-black/60 text-white transition rounded-full disabled:opacity-50`}
        title={isFavorited ? "Remove from favorites" : "Save to favorites"}
      >
        <svg
          className={iconSize}
          fill={isFavorited ? "currentColor" : "none"}
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z"
          />
        </svg>
      </button>
      <AuthModal isOpen={showAuth} onClose={() => setShowAuth(false)} />
    </>
  );
}
