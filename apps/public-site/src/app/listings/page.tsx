import { Suspense } from "react";
import type { Metadata } from "next";
import Link from "next/link";
import { searchListings } from "@/lib/api";
import PropertyCard from "@/components/PropertyCard";
import SearchFilters from "@/components/SearchFilters";

export const metadata: Metadata = {
  title: "Property Search",
  description:
    "Search homes, land, and properties for sale in Western North Carolina.",
};

interface PageProps {
  searchParams: Promise<Record<string, string | undefined>>;
}

async function ListingsGrid({
  searchParams,
}: {
  searchParams: Record<string, string | undefined>;
}) {
  let listings, pagination;
  try {
    const result = await searchListings({
    q: searchParams.q,
    city: searchParams.city,
    county: searchParams.county,
    min_price: searchParams.min_price
      ? parseInt(searchParams.min_price)
      : undefined,
    max_price: searchParams.max_price
      ? parseInt(searchParams.max_price)
      : undefined,
    min_beds: searchParams.min_beds
      ? parseInt(searchParams.min_beds)
      : undefined,
    min_baths: searchParams.min_baths
      ? parseFloat(searchParams.min_baths)
      : undefined,
    min_sqft: searchParams.min_sqft
      ? parseInt(searchParams.min_sqft)
      : undefined,
    min_acreage: searchParams.min_acreage
      ? parseFloat(searchParams.min_acreage)
      : undefined,
    property_type: searchParams.property_type,
    sort: searchParams.sort || "list_date",
    order: (searchParams.order as "asc" | "desc") || "desc",
    page: searchParams.page ? parseInt(searchParams.page) : 1,
    limit: 24,
    });
    listings = result.listings;
    pagination = result.pagination;
  } catch {
    return (
      <div className="text-center py-20">
        <h3 className="text-xl text-[var(--color-primary)] mb-2">
          Unable to load listings
        </h3>
        <p className="text-[var(--color-text-light)]">
          Please try again in a moment, or{" "}
          <Link href="/contact" className="text-[var(--color-accent)] hover:underline">
            contact us
          </Link>{" "}
          for help.
        </p>
      </div>
    );
  }

  if (listings.length === 0) {
    return (
      <div className="text-center py-20">
        <h3 className="text-xl text-[var(--color-primary)] mb-2">
          No listings found
        </h3>
        <p className="text-[var(--color-text-light)]">
          Try adjusting your search filters or{" "}
          <Link href="/listings" className="text-[var(--color-accent)] hover:underline">
            view all listings
          </Link>
          .
        </p>
      </div>
    );
  }

  // Build pagination URL helper
  const buildPageUrl = (page: number) => {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(searchParams)) {
      if (value && key !== "page") {
        params.set(key, value);
      }
    }
    params.set("page", String(page));
    return `/listings?${params.toString()}`;
  };

  return (
    <div>
      {/* Results count */}
      <div className="flex items-center justify-between mb-6">
        <p className="text-sm text-[var(--color-text-light)]">
          Showing{" "}
          <span className="font-medium text-[var(--color-text)]">
            {(pagination.page - 1) * pagination.limit + 1}
          </span>
          {" - "}
          <span className="font-medium text-[var(--color-text)]">
            {Math.min(
              pagination.page * pagination.limit,
              pagination.total
            )}
          </span>{" "}
          of{" "}
          <span className="font-medium text-[var(--color-text)]">
            {pagination.total.toLocaleString()}
          </span>{" "}
          properties
        </p>
      </div>

      {/* Listing grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
        {listings.map((listing) => (
          <PropertyCard key={listing.id} listing={listing} />
        ))}
      </div>

      {/* Pagination */}
      {pagination.pages > 1 && (
        <div className="flex items-center justify-center gap-2 mt-10">
          {pagination.page > 1 && (
            <Link
              href={buildPageUrl(pagination.page - 1)}
              className="px-4 py-2 border border-[var(--color-primary)]/20 text-sm text-[var(--color-primary)] hover:bg-[var(--color-primary)] hover:text-white transition"
            >
              Previous
            </Link>
          )}

          {Array.from({ length: Math.min(pagination.pages, 7) }, (_, i) => {
            let pageNum: number;
            if (pagination.pages <= 7) {
              pageNum = i + 1;
            } else if (pagination.page <= 4) {
              pageNum = i + 1;
            } else if (pagination.page >= pagination.pages - 3) {
              pageNum = pagination.pages - 6 + i;
            } else {
              pageNum = pagination.page - 3 + i;
            }

            return (
              <Link
                key={pageNum}
                href={buildPageUrl(pageNum)}
                className={`px-4 py-2 border text-sm transition ${
                  pageNum === pagination.page
                    ? "bg-[var(--color-primary)] text-white border-[var(--color-primary)]"
                    : "border-[var(--color-primary)]/20 text-[var(--color-primary)] hover:bg-[var(--color-primary)] hover:text-white"
                }`}
              >
                {pageNum}
              </Link>
            );
          })}

          {pagination.page < pagination.pages && (
            <Link
              href={buildPageUrl(pagination.page + 1)}
              className="px-4 py-2 border border-[var(--color-primary)]/20 text-sm text-[var(--color-primary)] hover:bg-[var(--color-primary)] hover:text-white transition"
            >
              Next
            </Link>
          )}
        </div>
      )}
    </div>
  );
}

export default async function ListingsPage({ searchParams }: PageProps) {
  const params = await searchParams;

  return (
    <div className="bg-[var(--color-eggshell)] min-h-screen">
      {/* Spacer for transparent header */}
      <div className="h-20 bg-[var(--color-primary)]" />

      <Suspense fallback={null}>
        <SearchFilters />
      </Suspense>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Suspense
          fallback={
            <div className="text-center py-20">
              <div className="inline-block w-8 h-8 border-4 border-[var(--color-primary)]/20 border-t-[var(--color-accent)] rounded-full animate-spin" />
              <p className="text-[var(--color-text-light)] mt-4">Loading listings...</p>
            </div>
          }
        >
          <ListingsGrid searchParams={params} />
        </Suspense>
      </div>
    </div>
  );
}
