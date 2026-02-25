import Link from "next/link";
import Image from "next/image";
import { formatPrice, formatNumber } from "@/lib/api";
import type { Metadata } from "next";

interface SharedListing {
  id: string;
  mls_number: string;
  status: string;
  list_price: number;
  sold_price?: number;
  address: string;
  city: string;
  state: string;
  zip: string;
  county: string;
  property_type: string;
  beds?: number;
  baths?: number;
  sqft?: number;
  acreage?: number;
  elevation_feet?: number;
  primary_photo?: string;
  photo_count?: number;
  days_on_market?: number;
  agent_notes?: string;
}

interface SharedCollection {
  name: string;
  description: string;
  status: string;
  created_at: string;
  listings: SharedListing[];
  listing_count: number;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

async function getSharedCollection(token: string): Promise<SharedCollection | null> {
  try {
    const res = await fetch(`${API_BASE}/api/public/collections/${token}`, {
      next: { revalidate: 300 },
    });
    if (!res.ok) return null;
    const data = await res.json();
    return data.success ? data.data : null;
  } catch {
    return null;
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ token: string }>;
}): Promise<Metadata> {
  const { token } = await params;
  const collection = await getSharedCollection(token);
  if (!collection) {
    return { title: "Collection Not Found" };
  }
  return {
    title: collection.name,
    description: collection.description || `${collection.listing_count} properties curated for you`,
  };
}

export default async function SharedCollectionPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  const collection = await getSharedCollection(token);

  if (!collection) {
    return (
      <div className="bg-[var(--color-eggshell)] min-h-screen">
        <div className="h-20 bg-[var(--color-primary)]" />
        <div className="max-w-7xl mx-auto px-6 py-16 text-center">
          <h1 className="text-3xl text-[var(--color-primary)] mb-4" style={{ fontFamily: "Georgia, serif" }}>
            Collection Not Found
          </h1>
          <p className="text-[var(--color-text-light)] mb-6">
            This collection may have been removed or the link may be incorrect.
          </p>
          <Link
            href="/listings"
            className="inline-block px-6 py-3 bg-[var(--color-accent)] text-[var(--color-primary)] font-semibold text-sm uppercase tracking-wider hover:bg-[var(--color-accent-hover)] transition"
          >
            Browse Properties
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
        <div className="mb-10 text-center">
          <h1
            className="text-4xl text-[var(--color-primary)]"
            style={{ fontFamily: "Georgia, serif" }}
          >
            {collection.name}
          </h1>
          {collection.description && (
            <p className="text-[var(--color-text-light)] mt-3 max-w-2xl mx-auto">
              {collection.description}
            </p>
          )}
          <p className="text-sm text-[var(--color-text-light)] mt-4">
            {collection.listing_count} {collection.listing_count === 1 ? "property" : "properties"} curated for you
          </p>
        </div>

        {/* Listings */}
        {collection.listings.length === 0 ? (
          <div className="text-center py-16">
            <p className="text-[var(--color-text-light)]">No properties in this collection yet.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {collection.listings.map((listing) => (
              <Link
                key={listing.id}
                href={`/listings/${listing.id}`}
                className="bg-white border border-gray-200/60 overflow-hidden group block hover:shadow-md transition-shadow"
              >
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
                  {listing.days_on_market != null && (
                    <div className="absolute top-3 right-3 bg-black/60 text-white text-xs font-semibold px-2.5 py-1">
                      {listing.days_on_market} DOM
                    </div>
                  )}
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
                    {listing.elevation_feet != null && <span>{formatNumber(listing.elevation_feet)} ft elev</span>}
                  </div>
                  <div className="text-sm mt-3 truncate text-[var(--color-text)]">{listing.address}</div>
                  <div className="text-sm text-[var(--color-text-light)]">{listing.city}, {listing.state} {listing.zip}</div>
                  {listing.agent_notes && (
                    <div className="mt-3 p-3 bg-[var(--color-eggshell)] text-sm text-[var(--color-text)]">
                      <span className="text-xs text-[var(--color-text-light)] uppercase tracking-wider block mb-1">Agent Note</span>
                      {listing.agent_notes}
                    </div>
                  )}
                  <div className="flex items-center justify-between mt-4 pt-3 text-xs border-t border-gray-100 text-[var(--color-text-light)]">
                    <span>{listing.property_type}</span>
                    <span>MLS# {listing.mls_number}</span>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}

        {/* Footer CTA */}
        <div className="mt-12 text-center">
          <p className="text-sm text-[var(--color-text-light)] mb-4">
            Interested in any of these properties?
          </p>
          <div className="flex items-center justify-center gap-4">
            <Link
              href="/contact"
              className="inline-block px-8 py-3 bg-[var(--color-accent)] text-[var(--color-primary)] font-semibold text-sm uppercase tracking-wider hover:bg-[var(--color-accent-hover)] transition"
            >
              Contact Us
            </Link>
            {collection.listings.length > 0 && (
              <a
                href={`/api/public/collections/${token}/brochure`}
                className="inline-flex items-center gap-2 px-6 py-3 border border-gray-300 text-sm text-[var(--color-text)] font-semibold uppercase tracking-wider hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] transition"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                Download PDF
              </a>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
