"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import Link from "next/link";

interface SavedSearch {
  id: string;
  name: string;
  filters: Record<string, string | number>;
  alert_frequency: string;
  created_at: string;
}

function filterSummary(filters: Record<string, string | number>): string {
  const parts: string[] = [];
  if (filters.city) parts.push(String(filters.city));
  if (filters.county) parts.push(`${filters.county} County`);
  if (filters.min_price) parts.push(`$${Number(filters.min_price).toLocaleString()}+`);
  if (filters.max_price) parts.push(`up to $${Number(filters.max_price).toLocaleString()}`);
  if (filters.min_beds) parts.push(`${filters.min_beds}+ beds`);
  if (filters.property_type) parts.push(String(filters.property_type));
  if (filters.q) parts.push(`"${filters.q}"`);
  return parts.length > 0 ? parts.join(", ") : "All listings";
}

function filtersToSearchParams(filters: Record<string, string | number>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  }
  return params.toString();
}

export default function SavedSearchesPage() {
  const { data: session, status } = useSession();
  const router = useRouter();
  const [searches, setSearches] = useState<SavedSearch[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (status === "unauthenticated") {
      router.push("/listings");
      return;
    }
    if (status !== "authenticated") return;

    async function fetchSearches() {
      try {
        const res = await fetch("/api/user/searches");
        if (res.ok) {
          const data = await res.json();
          if (data.success) setSearches(data.data);
        }
      } catch {
        // Silently fail
      } finally {
        setLoading(false);
      }
    }
    fetchSearches();
  }, [status, router]);

  const deleteSearch = async (searchId: string) => {
    await fetch(`/api/user/searches/${searchId}`, { method: "DELETE" });
    setSearches((prev) => prev.filter((s) => s.id !== searchId));
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
            Saved Searches
          </h1>
          <p className="text-[var(--color-text-light)] mt-2">
            {searches.length} saved {searches.length === 1 ? "search" : "searches"}
          </p>
        </div>

        {searches.length === 0 ? (
          <div className="text-center py-20">
            <svg className="w-16 h-16 text-gray-300 mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <h3 className="text-xl text-[var(--color-primary)] mb-2">No saved searches</h3>
            <p className="text-[var(--color-text-light)] mb-6">
              Search for properties and save your filters to get notified of new matches.
            </p>
            <Link
              href="/listings"
              className="inline-block px-6 py-3 bg-[var(--color-accent)] text-[var(--color-primary)] font-semibold text-sm uppercase tracking-wider hover:bg-[var(--color-accent-hover)] transition"
            >
              Search Properties
            </Link>
          </div>
        ) : (
          <div className="space-y-4">
            {searches.map((search) => (
              <div
                key={search.id}
                className="bg-white border border-gray-200/60 p-6 flex items-center justify-between"
              >
                <div className="flex-1 min-w-0">
                  <h3 className="text-lg text-[var(--color-primary)] font-medium truncate">
                    {search.name}
                  </h3>
                  <p className="text-sm text-[var(--color-text-light)] mt-1">
                    {filterSummary(search.filters)}
                  </p>
                  <div className="flex items-center gap-4 mt-2 text-xs text-[var(--color-text-light)]">
                    <span>Created {new Date(search.created_at).toLocaleDateString()}</span>
                    <span className="capitalize">Alerts: {search.alert_frequency}</span>
                  </div>
                </div>
                <div className="flex items-center gap-3 ml-4">
                  <Link
                    href={`/listings?${filtersToSearchParams(search.filters)}`}
                    className="px-4 py-2 bg-[var(--color-accent)] text-[var(--color-primary)] text-sm font-semibold uppercase tracking-wider hover:bg-[var(--color-accent-hover)] transition"
                  >
                    Run Search
                  </Link>
                  <button
                    onClick={() => deleteSearch(search.id)}
                    className="px-3 py-2 text-sm text-red-500 hover:text-red-700 transition"
                  >
                    Delete
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
