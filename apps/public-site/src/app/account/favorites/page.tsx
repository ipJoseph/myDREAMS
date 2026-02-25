"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import { formatPrice, formatNumber } from "@/lib/api";

interface FavoriteListing {
  favorite_id: string;
  favorited_at: string;
  id: string;
  mls_number: string;
  status: string;
  list_price: number;
  sold_price?: number;
  address: string;
  city: string;
  state: string;
  zip: string;
  property_type: string;
  beds?: number;
  baths?: number;
  sqft?: number;
  acreage?: number;
  primary_photo?: string;
  days_on_market?: number;
}

export default function FavoritesPage() {
  const { data: session, status } = useSession();
  const router = useRouter();
  const [favorites, setFavorites] = useState<FavoriteListing[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (status === "unauthenticated") {
      router.push("/listings");
      return;
    }
    if (status !== "authenticated") return;

    async function fetchFavorites() {
      try {
        const res = await fetch("/api/user/favorites");
        if (res.ok) {
          const data = await res.json();
          if (data.success) setFavorites(data.data);
        }
      } catch {
        // Silently fail
      } finally {
        setLoading(false);
      }
    }
    fetchFavorites();
  }, [status, router]);

  const removeFavorite = async (listingId: string) => {
    await fetch(`/api/user/favorites/${listingId}`, { method: "DELETE" });
    setFavorites((prev) => prev.filter((f) => f.id !== listingId));
  };

  if (status === "loading" || loading) {
    return (
      <div className="bg-[var(--color-eggshell)] min-h-screen">
        <div className="h-20 bg-[var(--color-primary)]" />
        <div className="max-w-7xl mx-auto px-6 py-16 text-center">
          <div className="inline-block w-8 h-8 border-4 border-[var(--color-primary)]/20 border-t-[var(--color-accent)] rounded-full animate-spin" />
        </div>
      </div>
    );
  }

  return (
    <div className="bg-[var(--color-eggshell)] min-h-screen">
      <div className="h-20 bg-[var(--color-primary)]" />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <div className="mb-8">
          <h1
            className="text-3xl text-[var(--color-primary)]"
            style={{ fontFamily: "Georgia, serif" }}
          >
            My Favorites
          </h1>
          <p className="text-[var(--color-text-light)] mt-2">
            {favorites.length} saved {favorites.length === 1 ? "property" : "properties"}
          </p>
        </div>

        {favorites.length === 0 ? (
          <div className="text-center py-20">
            <svg className="w-16 h-16 text-gray-300 mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
            </svg>
            <h3 className="text-xl text-[var(--color-primary)] mb-2">No favorites yet</h3>
            <p className="text-[var(--color-text-light)] mb-6">
              Browse properties and click the heart icon to save them here.
            </p>
            <Link
              href="/listings"
              className="inline-block px-6 py-3 bg-[var(--color-accent)] text-[var(--color-primary)] font-semibold text-sm uppercase tracking-wider hover:bg-[var(--color-accent-hover)] transition"
            >
              Browse Properties
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {favorites.map((fav) => (
              <div key={fav.id} className="bg-white border border-gray-200/60 overflow-hidden group">
                <Link href={`/listings/${fav.id}`}>
                  <div className="relative aspect-[4/3] bg-gray-900 overflow-hidden">
                    {fav.primary_photo ? (
                      <Image
                        src={fav.primary_photo}
                        alt={`${fav.address}, ${fav.city}`}
                        fill
                        sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
                        className="object-cover group-hover:scale-105 transition-transform duration-500"
                        loading="lazy"
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-gray-600">
                        <svg className="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                            d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0h4" />
                        </svg>
                      </div>
                    )}
                    <span
                      className={`absolute top-3 left-3 text-xs font-semibold px-2.5 py-1 uppercase tracking-wider ${
                        fav.status === "ACTIVE"
                          ? "bg-[var(--color-accent)] text-[var(--color-primary)]"
                          : fav.status === "SOLD" || fav.status === "CLOSED"
                            ? "bg-red-600 text-white"
                            : "bg-white/90 text-gray-700"
                      }`}
                    >
                      {fav.status}
                    </span>
                  </div>
                  <div className="p-5">
                    <div className="text-2xl font-light text-[var(--color-primary)]" style={{ fontFamily: "Georgia, serif" }}>
                      {formatPrice(fav.sold_price || fav.list_price)}
                    </div>
                    <div className="flex items-center gap-3 text-sm mt-2 text-[var(--color-text-light)]">
                      {fav.beds != null && <span>{fav.beds} bd</span>}
                      {fav.baths != null && <span>{fav.baths} ba</span>}
                      {fav.sqft != null && <span>{formatNumber(fav.sqft)} sqft</span>}
                    </div>
                    <div className="text-sm mt-3 truncate text-[var(--color-text)]">{fav.address}</div>
                    <div className="text-sm text-[var(--color-text-light)]">{fav.city}, {fav.state} {fav.zip}</div>
                  </div>
                </Link>
                <div className="px-5 pb-4 flex items-center justify-between border-t border-gray-100 pt-3">
                  <span className="text-xs text-[var(--color-text-light)]">
                    Saved {new Date(fav.favorited_at).toLocaleDateString()}
                  </span>
                  <button
                    onClick={() => removeFavorite(fav.id)}
                    className="text-xs text-red-500 hover:text-red-700 transition"
                  >
                    Remove
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
