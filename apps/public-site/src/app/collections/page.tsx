import Link from "next/link";
import Image from "next/image";
import type { Metadata } from "next";
import { getFeaturedCollections, formatPrice } from "@/lib/api";

export const metadata: Metadata = {
  title: "Curated Collections",
  description:
    "Browse curated property collections in Western North Carolina. Mountain cabins, luxury homes, land, and more.",
};

export const revalidate = 300; // 5 min ISR

export default async function CollectionsPage() {
  const collections = await getFeaturedCollections();

  return (
    <div className="min-h-screen bg-[var(--color-eggshell)]">
      {/* Hero */}
      <section className="bg-[var(--color-primary)] pt-32 pb-20 px-6">
        <div className="max-w-5xl mx-auto text-center">
          <h1
            className="text-4xl md:text-5xl text-white font-light mb-4"
            style={{ fontFamily: "Georgia, serif" }}
          >
            Curated Collections
          </h1>
          <p className="text-white/60 text-lg max-w-2xl mx-auto">
            Handpicked property selections organized by lifestyle, location,
            and investment opportunity across Western North Carolina.
          </p>
        </div>
      </section>

      {/* Collections Grid */}
      <section className="max-w-7xl mx-auto px-6 py-16">
        {collections.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-8">
            {collections.map((collection) => (
              <Link
                key={collection.id}
                href={`/collections/${collection.slug}`}
                className="group block bg-white overflow-hidden border border-gray-200/60 hover:border-[var(--color-accent)] shadow-sm hover:shadow-lg transition-all duration-300"
              >
                {/* Cover Image */}
                <div className="relative aspect-[16/10] bg-gray-100 overflow-hidden">
                  {collection.cover_image ? (
                    <Image
                      src={collection.cover_image}
                      alt={collection.name}
                      fill
                      sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
                      className="object-cover group-hover:scale-105 transition-transform duration-500"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-gray-400">
                      <svg
                        className="w-16 h-16"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={1}
                          d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
                        />
                      </svg>
                    </div>
                  )}
                  {/* Property count badge */}
                  <div className="absolute bottom-3 right-3 bg-black/60 text-white text-xs font-semibold px-3 py-1.5">
                    {collection.property_count}{" "}
                    {collection.property_count === 1 ? "property" : "properties"}
                  </div>
                </div>

                {/* Info */}
                <div className="p-6">
                  <h2
                    className="text-xl text-[var(--color-primary)] font-light mb-2"
                    style={{ fontFamily: "Georgia, serif" }}
                  >
                    {collection.name}
                  </h2>
                  {collection.description && (
                    <p className="text-sm text-[var(--color-text-light)] mb-4 line-clamp-2">
                      {collection.description}
                    </p>
                  )}
                  <div className="flex items-center gap-4 text-sm text-[var(--color-text-light)] pt-3 border-t border-gray-100">
                    {collection.min_price && collection.max_price && (
                      <span>
                        {formatPrice(collection.min_price)} &ndash;{" "}
                        {formatPrice(collection.max_price)}
                      </span>
                    )}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        ) : (
          <div className="text-center py-20">
            <p className="text-[var(--color-text-light)] text-lg mb-4">
              No curated collections available yet.
            </p>
            <Link
              href="/listings"
              className="inline-block bg-[var(--color-primary)] text-white px-8 py-3 text-sm uppercase tracking-wider hover:bg-[var(--color-primary)]/90 transition"
            >
              Browse All Listings
            </Link>
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
            Looking for Something Specific?
          </h2>
          <p className="text-white/60 mb-8">
            Let us create a personalized collection based on your unique
            requirements.
          </p>
          <Link
            href="/contact"
            className="inline-block bg-[var(--color-accent)] text-[var(--color-primary)] px-8 py-3 text-sm font-semibold uppercase tracking-wider hover:bg-[var(--color-accent)]/90 transition"
          >
            Contact Us
          </Link>
        </div>
      </section>
    </div>
  );
}
