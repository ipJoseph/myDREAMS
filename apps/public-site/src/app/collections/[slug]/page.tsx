import Link from "next/link";
import Image from "next/image";
import type { Metadata } from "next";
import { getFeaturedCollection, formatPrice, formatNumber } from "@/lib/api";
import { notFound } from "next/navigation";

interface Props {
  params: Promise<{ slug: string }>;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const collection = await getFeaturedCollection(slug);
  if (!collection) return { title: "Collection Not Found" };
  return {
    title: `${collection.name} | Curated Collection`,
    description:
      collection.description ||
      `Browse ${collection.listing_count} curated properties in this collection.`,
  };
}

export const revalidate = 300;

export default async function CollectionDetailPage({ params }: Props) {
  const { slug } = await params;
  const collection = await getFeaturedCollection(slug);

  if (!collection) {
    notFound();
  }

  const listings = collection.listings || [];
  const prices = listings
    .map((l) => l.list_price)
    .filter((p): p is number => p != null && p > 0);
  const minPrice = prices.length > 0 ? Math.min(...prices) : null;
  const maxPrice = prices.length > 0 ? Math.max(...prices) : null;

  return (
    <div className="min-h-screen bg-[var(--color-eggshell)]">
      {/* Hero */}
      <section className="relative bg-[var(--color-primary)] pt-32 pb-20 px-6 overflow-hidden">
        {collection.cover_image && (
          <Image
            src={collection.cover_image}
            alt={collection.name}
            fill
            className="object-cover opacity-20"
            priority
          />
        )}
        <div className="relative max-w-5xl mx-auto text-center">
          <Link
            href="/collections"
            className="inline-block text-white/50 text-sm mb-6 hover:text-white transition"
          >
            &larr; All Collections
          </Link>
          <h1
            className="text-4xl md:text-5xl text-white font-light mb-4"
            style={{ fontFamily: "Georgia, serif" }}
          >
            {collection.name}
          </h1>
          {collection.description && (
            <p className="text-white/60 text-lg max-w-2xl mx-auto mb-8">
              {collection.description}
            </p>
          )}
          <div className="flex items-center justify-center gap-6 text-white/50 text-sm">
            <span>
              {collection.listing_count}{" "}
              {collection.listing_count === 1 ? "property" : "properties"}
            </span>
            {minPrice && maxPrice && (
              <span>
                {formatPrice(minPrice)} &ndash; {formatPrice(maxPrice)}
              </span>
            )}
          </div>
        </div>
      </section>

      {/* Listings Grid */}
      <section className="max-w-7xl mx-auto px-6 py-12">
        {listings.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-8">
            {listings.map((listing, index) => (
              <div
                key={listing.id}
                className="bg-white overflow-hidden border border-gray-200/60 shadow-sm"
              >
                {/* Photo */}
                <Link
                  href={`/listings/${listing.id}`}
                  className="block relative aspect-[4/3] bg-gray-900 overflow-hidden group"
                >
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
                      <svg
                        className="w-16 h-16"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={1.5}
                          d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0h4"
                        />
                      </svg>
                    </div>
                  )}
                  {/* Number badge */}
                  <div className="absolute top-3 left-3 bg-[var(--color-accent)] text-[var(--color-primary)] w-8 h-8 flex items-center justify-center text-sm font-bold">
                    {index + 1}
                  </div>
                  {listing.status && (
                    <div className="absolute top-3 right-3">
                      <span
                        className={`text-xs font-semibold px-2.5 py-1 uppercase tracking-wider ${
                          listing.status === "ACTIVE"
                            ? "bg-[var(--color-accent)] text-[var(--color-primary)]"
                            : listing.status === "PENDING"
                              ? "bg-white/90 text-gray-700"
                              : "bg-gray-600 text-white"
                        }`}
                      >
                        {listing.status}
                      </span>
                    </div>
                  )}
                  {listing.days_on_market != null && (
                    <div className="absolute bottom-3 right-3 bg-black/60 text-white text-xs font-semibold px-2.5 py-1">
                      {listing.days_on_market} DOM
                    </div>
                  )}
                </Link>

                {/* Info */}
                <div className="p-5">
                  <div
                    className="text-2xl font-light text-[var(--color-primary)]"
                    style={{ fontFamily: "Georgia, serif" }}
                  >
                    {formatPrice(listing.list_price)}
                  </div>
                  <div className="flex items-center gap-3 text-sm mt-2 text-[var(--color-text-light)]">
                    {listing.beds != null && <span>{listing.beds} bd</span>}
                    {listing.baths != null && <span>{listing.baths} ba</span>}
                    {listing.sqft != null && (
                      <span>{formatNumber(listing.sqft)} sqft</span>
                    )}
                    {listing.acreage != null && listing.acreage > 0 && (
                      <span>{listing.acreage.toFixed(2)} ac</span>
                    )}
                  </div>
                  <Link
                    href={`/listings/${listing.id}`}
                    className="block text-sm mt-3 text-[var(--color-text)] hover:text-[var(--color-accent)] transition truncate"
                  >
                    {listing.address}
                  </Link>
                  <div className="text-sm text-[var(--color-text-light)]">
                    {listing.city}, {listing.state} {listing.zip}
                  </div>

                  {/* Agent Notes */}
                  {listing.agent_notes && (
                    <div className="mt-4 p-3 bg-[var(--color-eggshell)] text-sm text-[var(--color-text)]">
                      <span className="font-semibold text-xs uppercase tracking-wider text-[var(--color-text-light)] block mb-1">
                        Agent Notes
                      </span>
                      {listing.agent_notes}
                    </div>
                  )}

                  <div className="flex items-center justify-between mt-4 pt-3 text-xs border-t border-gray-100 text-[var(--color-text-light)]">
                    <span>{listing.property_type}</span>
                    <span>MLS# {listing.mls_number}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-20">
            <p className="text-[var(--color-text-light)] text-lg">
              This collection is empty.
            </p>
          </div>
        )}
      </section>

      {/* CTA */}
      <section className="bg-[var(--color-primary)] py-16 px-6">
        <div className="max-w-3xl mx-auto text-center">
          <h2
            className="text-3xl text-white font-light mb-4"
            style={{ fontFamily: "Georgia, serif" }}
          >
            Interested in These Properties?
          </h2>
          <p className="text-white/60 mb-8">
            Schedule showings, get more details, or let us refine the
            selection to match your needs.
          </p>
          <div className="flex items-center justify-center gap-4 flex-wrap">
            <Link
              href="/contact"
              className="inline-block bg-[var(--color-accent)] text-[var(--color-primary)] px-8 py-3 text-sm font-semibold uppercase tracking-wider hover:bg-[var(--color-accent)]/90 transition"
            >
              Contact Us
            </Link>
            <Link
              href="/collections"
              className="inline-block border border-white/30 text-white px-8 py-3 text-sm uppercase tracking-wider hover:bg-white/10 transition"
            >
              Browse Collections
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
