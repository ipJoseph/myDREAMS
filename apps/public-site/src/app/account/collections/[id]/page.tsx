"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { useRouter, useParams } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import { formatPrice, formatNumber } from "@/lib/api";

interface CollectionListing {
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
  display_order: number;
  agent_notes?: string;
  added_at: string;
}

interface CollectionDetail {
  id: string;
  name: string;
  description: string;
  status: string;
  share_token: string;
  showing_requested: number;
  showing_requested_at: string | null;
  created_at: string;
  listings: CollectionListing[];
}

export default function CollectionDetailPage() {
  const { data: session, status } = useSession();
  const router = useRouter();
  const params = useParams();
  const collectionId = params.id as string;

  const [collection, setCollection] = useState<CollectionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);
  const [showingLoading, setShowingLoading] = useState(false);
  const [showingMessage, setShowingMessage] = useState("");

  useEffect(() => {
    if (status === "unauthenticated") {
      router.push("/listings");
      return;
    }
    if (status !== "authenticated") return;
    fetchCollection();
  }, [status, router, collectionId]);

  async function fetchCollection() {
    try {
      const res = await fetch(`/api/user/collections/${collectionId}`);
      if (res.ok) {
        const data = await res.json();
        if (data.success) setCollection(data.data);
      }
    } catch {
      // Silently fail
    } finally {
      setLoading(false);
    }
  }

  const removeItem = async (listingId: string) => {
    await fetch(`/api/user/collections/${collectionId}/items/${listingId}`, {
      method: "DELETE",
    });
    setCollection((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        listings: prev.listings.filter((l) => l.id !== listingId),
      };
    });
  };

  const copyShareLink = () => {
    if (!collection?.share_token) return;
    const url = `${window.location.origin}/shared/${collection.share_token}`;
    navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const requestShowings = async () => {
    if (!collection || showingLoading) return;
    setShowingLoading(true);
    setShowingMessage("");
    try {
      const res = await fetch(
        `/api/user/collections/${collectionId}/request-showings`,
        { method: "POST" }
      );
      const data = await res.json();
      if (data.success) {
        setCollection((prev) =>
          prev
            ? {
                ...prev,
                showing_requested: 1,
                showing_requested_at: data.data.showing_requested_at,
              }
            : prev
        );
        setShowingMessage("Showing request sent to your agent!");
        setTimeout(() => setShowingMessage(""), 5000);
      }
    } catch {
      setShowingMessage("Something went wrong. Please try again.");
      setTimeout(() => setShowingMessage(""), 4000);
    } finally {
      setShowingLoading(false);
    }
  };

  const cancelShowings = async () => {
    if (!collection || showingLoading) return;
    setShowingLoading(true);
    try {
      const res = await fetch(
        `/api/user/collections/${collectionId}/cancel-showings`,
        { method: "POST" }
      );
      const data = await res.json();
      if (data.success) {
        setCollection((prev) =>
          prev
            ? { ...prev, showing_requested: 0, showing_requested_at: null }
            : prev
        );
      }
    } catch {
      // Silently fail
    } finally {
      setShowingLoading(false);
    }
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

  if (!collection) {
    return (
      <div className="bg-[var(--color-eggshell)] min-h-screen">
        <div className="h-20 bg-[var(--color-primary)]" />
        <div className="max-w-7xl mx-auto px-6 py-16 text-center">
          <h2 className="text-xl text-[var(--color-primary)]">Collection not found</h2>
          <Link href="/account/collections" className="text-[var(--color-accent)] mt-4 inline-block">
            Back to collections
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-[var(--color-eggshell)] min-h-screen">
      <div className="h-20 bg-[var(--color-primary)]" />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        {/* Header */}
        <div className="mb-8">
          <Link href="/account/collections" className="text-sm text-[var(--color-text-light)] hover:text-[var(--color-accent)] transition mb-4 inline-block">
            &larr; All Collections
          </Link>
          <div className="flex items-start justify-between flex-wrap gap-4">
            <div>
              <h1
                className="text-3xl text-[var(--color-primary)]"
                style={{ fontFamily: "Georgia, serif" }}
              >
                {collection.name}
              </h1>
              {collection.description && (
                <p className="text-[var(--color-text-light)] mt-2">{collection.description}</p>
              )}
              <p className="text-sm text-[var(--color-text-light)] mt-2">
                {collection.listings.length} {collection.listings.length === 1 ? "property" : "properties"}
              </p>
            </div>
            <div className="flex items-center gap-3 flex-wrap">
              {/* Request Showings Button */}
              {collection.listings.length > 0 && (
                collection.showing_requested ? (
                  <div className="flex items-center gap-2">
                    <span className="flex items-center gap-2 px-4 py-2.5 bg-green-50 border border-green-200 text-sm text-green-700">
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                      Showings Requested
                      {collection.showing_requested_at && (
                        <span className="text-xs text-green-500 ml-1">
                          {new Date(collection.showing_requested_at).toLocaleDateString()}
                        </span>
                      )}
                    </span>
                    <button
                      onClick={cancelShowings}
                      disabled={showingLoading}
                      className="text-xs text-gray-400 hover:text-red-500 transition px-2 py-1"
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={requestShowings}
                    disabled={showingLoading}
                    className="flex items-center gap-2 px-5 py-2.5 bg-[var(--color-accent)] text-[var(--color-primary)] font-semibold text-sm uppercase tracking-wider hover:bg-[var(--color-accent-hover)] transition disabled:opacity-50"
                  >
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                        d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                    </svg>
                    {showingLoading ? "Sending..." : "Request Showings"}
                  </button>
                )
              )}
              {collection.share_token && collection.listings.length > 0 && (
                <a
                  href={`/api/public/collections/${collection.share_token}/brochure`}
                  className="flex items-center gap-2 px-4 py-2.5 border border-gray-300 text-sm text-[var(--color-text)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] transition"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  Download All as PDF
                </a>
              )}
              <button
                onClick={copyShareLink}
                className="flex items-center gap-2 px-4 py-2.5 border border-gray-300 text-sm text-[var(--color-text)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] transition"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" />
                </svg>
                {copied ? "Link Copied!" : "Share Link"}
              </button>
            </div>
          </div>

          {/* Showing confirmation message */}
          {showingMessage && (
            <div className="mt-4 px-4 py-3 bg-green-50 border border-green-200 text-green-700 text-sm">
              {showingMessage}
            </div>
          )}
        </div>

        {/* Listings grid */}
        {collection.listings.length === 0 ? (
          <div className="text-center py-20">
            <svg className="w-16 h-16 text-gray-300 mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0h4" />
            </svg>
            <h3 className="text-xl text-[var(--color-primary)] mb-2">No properties yet</h3>
            <p className="text-[var(--color-text-light)] mb-6">
              Add properties from listing pages using the &quot;Add to Collection&quot; button.
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
            {collection.listings.map((listing) => (
              <div key={listing.id} className="bg-white border border-gray-200/60 overflow-hidden group">
                <Link href={`/listings/${listing.id}`}>
                  <div className="relative aspect-[4/3] bg-gray-900 overflow-hidden">
                    {listing.primary_photo ? (
                      <Image
                        src={listing.primary_photo}
                        alt={`${listing.address}, ${listing.city}`}
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
                        listing.status === "ACTIVE"
                          ? "bg-[var(--color-accent)] text-[var(--color-primary)]"
                          : listing.status === "SOLD" || listing.status === "CLOSED"
                            ? "bg-red-600 text-white"
                            : "bg-white/90 text-gray-700"
                      }`}
                    >
                      {listing.status}
                    </span>
                  </div>
                  <div className="p-5">
                    <div className="text-2xl font-light text-[var(--color-primary)]" style={{ fontFamily: "Georgia, serif" }}>
                      {formatPrice(listing.sold_price || listing.list_price)}
                    </div>
                    <div className="flex items-center gap-3 text-sm mt-2 text-[var(--color-text-light)]">
                      {listing.beds != null && <span>{listing.beds} bd</span>}
                      {listing.baths != null && <span>{listing.baths} ba</span>}
                      {listing.sqft != null && <span>{formatNumber(listing.sqft)} sqft</span>}
                      {listing.acreage != null && listing.acreage > 0 && <span>{listing.acreage.toFixed(2)} ac</span>}
                    </div>
                    <div className="text-sm mt-3 truncate text-[var(--color-text)]">{listing.address}</div>
                    <div className="text-sm text-[var(--color-text-light)]">{listing.city}, {listing.state} {listing.zip}</div>
                  </div>
                </Link>
                <div className="px-5 pb-4 flex items-center justify-between border-t border-gray-100 pt-3">
                  <span className="text-xs text-[var(--color-text-light)]">
                    Added {new Date(listing.added_at).toLocaleDateString()}
                  </span>
                  <button
                    onClick={() => removeItem(listing.id)}
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
