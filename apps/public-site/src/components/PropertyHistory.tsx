"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { AddressHistory, AddressHistoryListing, PropertyChange } from "@/lib/types";
import { formatPrice } from "@/lib/api";

interface PropertyHistoryProps {
  listingId: string;
}

type TimelineEntry =
  | { type: "listing"; date: string; data: AddressHistoryListing }
  | { type: "change"; date: string; data: PropertyChange };

export default function PropertyHistory({ listingId }: PropertyHistoryProps) {
  const [history, setHistory] = useState<AddressHistory | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchHistory() {
      try {
        const res = await fetch(`/api/public/listings/${listingId}/history`);
        if (!res.ok) return;
        const json = await res.json();
        if (json.success) {
          setHistory(json.data);
        }
      } catch {
        // Silently fail; history is supplemental
      } finally {
        setLoading(false);
      }
    }
    fetchHistory();
  }, [listingId]);

  if (loading) return null;
  if (!history) return null;

  const { prior_listings, changes } = history;
  if (prior_listings.length === 0 && changes.length === 0) return null;

  // Build unified timeline sorted by date descending
  const timeline: TimelineEntry[] = [];

  for (const listing of prior_listings) {
    const date = listing.sold_date || listing.list_date || "";
    timeline.push({ type: "listing", date, data: listing });
  }

  for (const change of changes) {
    timeline.push({ type: "change", date: change.date || "", data: change });
  }

  timeline.sort((a, b) => {
    if (!a.date && !b.date) return 0;
    if (!a.date) return 1;
    if (!b.date) return -1;
    return b.date.localeCompare(a.date);
  });

  return (
    <div className="mb-10">
      <h2 className="text-xl text-[var(--color-primary)] mb-4">
        Property History
      </h2>
      <div className="relative">
        {/* Vertical line */}
        <div className="absolute left-4 top-0 bottom-0 w-px bg-gray-200" />

        <div className="space-y-4">
          {timeline.map((entry, i) => (
            <div key={i} className="relative pl-10">
              {/* Dot */}
              <div
                className={`absolute left-2.5 top-3 w-3 h-3 rounded-full border-2 ${
                  entry.type === "listing"
                    ? "bg-[var(--color-primary)] border-[var(--color-primary)]"
                    : "bg-white border-[var(--color-accent)]"
                }`}
              />

              {entry.type === "listing" ? (
                <ListingEntry listing={entry.data} />
              ) : (
                <ChangeEntry change={entry.data} />
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ListingEntry({ listing }: { listing: AddressHistoryListing }) {
  const isSold = listing.status === "SOLD" || listing.status === "CLOSED";
  const displayDate = isSold && listing.sold_date
    ? new Date(listing.sold_date).toLocaleDateString()
    : listing.list_date
      ? new Date(listing.list_date).toLocaleDateString()
      : null;

  return (
    <Link
      href={`/listings/${listing.id}`}
      className="block bg-white border border-gray-200/60 p-4 hover:border-[var(--color-accent)] transition"
    >
      <div className="flex items-center justify-between mb-1">
        <span
          className={`text-xs font-semibold px-2 py-0.5 uppercase tracking-wider ${
            listing.status === "ACTIVE"
              ? "bg-[var(--color-accent)] text-[var(--color-primary)]"
              : isSold
                ? "bg-red-600 text-white"
                : "bg-gray-200 text-gray-700"
          }`}
        >
          {listing.status}
        </span>
        {displayDate && (
          <span className="text-xs text-[var(--color-text-light)]">
            {displayDate}
          </span>
        )}
      </div>
      <div className="flex items-baseline gap-3 mt-2">
        {isSold && listing.sold_price ? (
          <>
            <span className="text-lg font-light text-[var(--color-primary)]" style={{ fontFamily: "Georgia, serif" }}>
              {formatPrice(listing.sold_price)}
            </span>
            {listing.sold_price !== listing.list_price && (
              <span className="text-sm text-[var(--color-text-light)] line-through">
                {formatPrice(listing.list_price)}
              </span>
            )}
          </>
        ) : (
          <span className="text-lg font-light text-[var(--color-primary)]" style={{ fontFamily: "Georgia, serif" }}>
            {formatPrice(listing.list_price)}
          </span>
        )}
      </div>
      <div className="flex items-center gap-3 mt-1 text-xs text-[var(--color-text-light)]">
        <span>MLS# {listing.mls_number}</span>
        {listing.days_on_market != null && <span>{listing.days_on_market} DOM</span>}
        {listing.listing_office_name && <span>{listing.listing_office_name}</span>}
      </div>
    </Link>
  );
}

function ChangeEntry({ change }: { change: PropertyChange }) {
  const date = change.date
    ? new Date(change.date).toLocaleDateString()
    : null;

  let label: string;
  let detail: string;

  if (change.change_type === "price") {
    const direction = change.change_percent && change.change_percent < 0 ? "reduced" : "increased";
    const pctStr = change.change_percent
      ? ` (${change.change_percent > 0 ? "+" : ""}${change.change_percent.toFixed(1)}%)`
      : "";
    label = `Price ${direction}`;
    detail = `${formatPrice(Number(change.old_value))} to ${formatPrice(Number(change.new_value))}${pctStr}`;
  } else if (change.change_type === "status") {
    label = "Status changed";
    detail = `${change.old_value} to ${change.new_value}`;
  } else {
    label = change.change_type;
    detail = `${change.old_value} to ${change.new_value}`;
  }

  return (
    <div className="bg-gray-50 border border-gray-200/60 px-4 py-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-[var(--color-text)]">
          {label}
        </span>
        {date && (
          <span className="text-xs text-[var(--color-text-light)]">
            {date}
          </span>
        )}
      </div>
      <p className="text-sm text-[var(--color-text-light)] mt-0.5">{detail}</p>
    </div>
  );
}
