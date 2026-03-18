"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import PropertyCard from "./PropertyCard";
import type { Listing } from "@/lib/types";

const PROPERTY_TYPES = [
  { key: "Residential", label: "Residential" },
  { key: "Land", label: "Land" },
  { key: "Commercial Sale", label: "Commercial" },
] as const;

interface NewOnMarketProps {
  /** Initial listings to show before any client-side filtering */
  initialListings: Listing[];
}

export default function NewOnMarket({ initialListings }: NewOnMarketProps) {
  const [activeTypes, setActiveTypes] = useState<Set<string>>(
    new Set(["Residential"])
  );
  const [listings, setListings] = useState<Listing[]>(initialListings);
  const [loading, setLoading] = useState(false);

  const toggleType = (type: string) => {
    setActiveTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) {
        // Don't allow deselecting all
        if (next.size === 1) return prev;
        next.delete(type);
      } else {
        next.add(type);
      }
      return next;
    });
  };

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    const types = Array.from(activeTypes);
    // Fetch for each active type and merge results
    Promise.all(
      types.map((type) =>
        fetch(
          `/api/public/listings?max_dom=14&limit=6&sort=list_date&order=desc&property_type=${encodeURIComponent(type)}`
        )
          .then((r) => r.json())
          .then((d) => d.data || [])
          .catch(() => [])
      )
    ).then((results) => {
      if (cancelled) return;
      // Merge, sort by list_date desc, take top 6
      const merged = results
        .flat()
        .sort(
          (a: Listing, b: Listing) =>
            new Date(b.list_date || "").getTime() -
            new Date(a.list_date || "").getTime()
        )
        .slice(0, 6);
      setListings(merged);
      setLoading(false);
    });

    return () => {
      cancelled = true;
    };
  }, [activeTypes]);

  return (
    <section className="bg-[var(--color-dark)] py-24">
      <div className="max-w-7xl mx-auto px-6 lg:px-8">
        <div className="flex flex-col md:flex-row md:items-end justify-between mb-12 gap-6">
          <div>
            <p className="text-[var(--color-accent)] text-xs uppercase tracking-[0.2em] mb-3">
              Just Listed
            </p>
            <h2 className="text-3xl md:text-4xl text-white">
              New on the Market
            </h2>
          </div>
          <div className="flex items-center gap-3">
            {PROPERTY_TYPES.map(({ key, label }) => (
              <button
                key={key}
                onClick={() => toggleType(key)}
                className={`px-4 py-2 text-xs uppercase tracking-wider border transition ${
                  activeTypes.has(key)
                    ? "bg-[var(--color-accent)] text-[var(--color-primary)] border-[var(--color-accent)]"
                    : "bg-transparent text-white/50 border-white/20 hover:border-white/40 hover:text-white/70"
                }`}
              >
                {label}
              </button>
            ))}
            <Link
              href="/listings"
              className="hidden md:inline-block ml-4 text-[var(--color-accent)] text-sm uppercase tracking-wider border-b border-[var(--color-accent)]/30 pb-1 hover:border-[var(--color-accent)] transition"
            >
              View All
            </Link>
          </div>
        </div>
        <div
          className={`grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 transition-opacity duration-200 ${
            loading ? "opacity-50" : "opacity-100"
          }`}
        >
          {listings.map((listing) => (
            <PropertyCard key={listing.id} listing={listing} variant="dark" />
          ))}
          {listings.length === 0 && !loading && (
            <p className="text-white/40 col-span-3 text-center py-12">
              No new listings found for the selected types.
            </p>
          )}
        </div>
        <div className="md:hidden text-center mt-10">
          <Link
            href="/listings"
            className="text-[var(--color-accent)] text-sm uppercase tracking-wider border-b border-[var(--color-accent)]/30 pb-1"
          >
            View All Properties
          </Link>
        </div>
      </div>
    </section>
  );
}
