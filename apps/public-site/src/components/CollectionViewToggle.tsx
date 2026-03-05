"use client";

import { useState, type ReactNode } from "react";
import dynamic from "next/dynamic";

const CollectionMap = dynamic(() => import("@/components/CollectionMap"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-[500px] bg-gray-100">
      <div className="inline-block w-8 h-8 border-4 border-[var(--color-primary)]/20 border-t-[var(--color-accent)] rounded-full animate-spin" />
    </div>
  ),
});

interface CollectionViewToggleProps {
  listings: Array<{
    id: string;
    address: string;
    city: string;
    county?: string;
    latitude?: number;
    longitude?: number;
    list_price: number;
    beds?: number;
    baths?: number;
    sqft?: number;
    primary_photo?: string;
    display_order: number;
    agent_notes?: string;
  }>;
  children: ReactNode;
}

export default function CollectionViewToggle({
  listings,
  children,
}: CollectionViewToggleProps) {
  const [viewMode, setViewMode] = useState<"grid" | "map">("grid");

  const hasGeo = listings.some((l) => l.latitude && l.longitude);

  return (
    <div>
      {/* View toggle */}
      {listings.length > 0 && hasGeo && (
        <div className="flex items-center gap-2 mb-6">
          <button
            onClick={() => setViewMode("grid")}
            className={`flex items-center gap-2 px-4 py-2 text-sm border transition ${
              viewMode === "grid"
                ? "border-[var(--color-accent)] text-[var(--color-primary)] bg-white"
                : "border-gray-300 text-[var(--color-text-light)] hover:border-[var(--color-accent)]"
            }`}
          >
            <svg
              className="w-4 h-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"
              />
            </svg>
            Grid
          </button>
          <button
            onClick={() => setViewMode("map")}
            className={`flex items-center gap-2 px-4 py-2 text-sm border transition ${
              viewMode === "map"
                ? "border-[var(--color-accent)] text-[var(--color-primary)] bg-white"
                : "border-gray-300 text-[var(--color-text-light)] hover:border-[var(--color-accent)]"
            }`}
          >
            <svg
              className="w-4 h-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7"
              />
            </svg>
            Map
          </button>
        </div>
      )}

      {/* Map view */}
      {viewMode === "map" && listings.length > 0 && (
        <div className="mb-8 border border-gray-200/60 overflow-hidden">
          <CollectionMap listings={listings} height={500} />
        </div>
      )}

      {/* Grid view (server-rendered children) */}
      {viewMode === "grid" && children}
    </div>
  );
}
