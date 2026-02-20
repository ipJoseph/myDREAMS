"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useRef } from "react";

const PRICE_OPTIONS = [
  { label: "Any", value: "" },
  { label: "$100k", value: "100000" },
  { label: "$200k", value: "200000" },
  { label: "$300k", value: "300000" },
  { label: "$400k", value: "400000" },
  { label: "$500k", value: "500000" },
  { label: "$750k", value: "750000" },
  { label: "$1M", value: "1000000" },
  { label: "$2M", value: "2000000" },
];

const BEDS_OPTIONS = [
  { label: "Any", value: "" },
  { label: "1+", value: "1" },
  { label: "2+", value: "2" },
  { label: "3+", value: "3" },
  { label: "4+", value: "4" },
  { label: "5+", value: "5" },
];

const TYPE_OPTIONS = [
  { label: "All Types", value: "" },
  { label: "Residential", value: "Residential" },
  { label: "Land", value: "Land" },
  { label: "Farm", value: "Farm" },
  { label: "Commercial", value: "Commercial" },
  { label: "Multi-Family", value: "Multi-Family" },
];

const SORT_OPTIONS = [
  { label: "Newest", value: "list_date:desc" },
  { label: "Price: Low to High", value: "list_price:asc" },
  { label: "Price: High to Low", value: "list_price:desc" },
  { label: "Beds", value: "beds:desc" },
  { label: "Sqft", value: "sqft:desc" },
  { label: "Acreage", value: "acreage:desc" },
];

export default function SearchFilters() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const searchInputRef = useRef<HTMLInputElement>(null);

  const updateFilters = useCallback(
    (key: string, value: string) => {
      const params = new URLSearchParams(searchParams.toString());
      if (value) {
        params.set(key, value);
      } else {
        params.delete(key);
      }
      // Reset to page 1 when filters change
      params.delete("page");
      router.push(`/listings?${params.toString()}`);
    },
    [router, searchParams]
  );

  const updateSort = useCallback(
    (sortValue: string) => {
      const params = new URLSearchParams(searchParams.toString());
      const [sort, order] = sortValue.split(":");
      params.set("sort", sort);
      params.set("order", order);
      params.delete("page");
      router.push(`/listings?${params.toString()}`);
    },
    [router, searchParams]
  );

  const clearAllFilters = useCallback(() => {
    router.push("/listings");
  }, [router]);

  const currentSort = `${searchParams.get("sort") || "list_date"}:${searchParams.get("order") || "desc"}`;

  // Check if any filters are active
  const hasActiveFilters = Array.from(searchParams.entries()).some(
    ([key]) => !["sort", "order", "page"].includes(key)
  );

  return (
    <div className="bg-white border-b border-gray-200 sticky top-0 z-10">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
        {/* Search bar */}
        <div className="flex gap-3 mb-4">
          <input
            ref={searchInputRef}
            type="text"
            placeholder="Search by address, city, or keyword..."
            defaultValue={searchParams.get("q") || ""}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                updateFilters("q", (e.target as HTMLInputElement).value);
              }
            }}
            className="flex-1 px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
          <button
            onClick={() => {
              updateFilters("q", searchInputRef.current?.value || "");
            }}
            className="px-6 py-2 bg-[var(--color-primary)] text-white rounded-md hover:bg-[var(--color-primary-light)] transition"
          >
            Search
          </button>
        </div>

        {/* Filter row */}
        <div className="flex flex-wrap gap-3 items-center">
          <select
            value={searchParams.get("min_price") || ""}
            onChange={(e) => updateFilters("min_price", e.target.value)}
            className="px-3 py-2 border border-gray-300 rounded-md text-sm"
          >
            <option value="">Min Price</option>
            {PRICE_OPTIONS.filter((o) => o.value).map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}+
              </option>
            ))}
          </select>

          <select
            value={searchParams.get("max_price") || ""}
            onChange={(e) => updateFilters("max_price", e.target.value)}
            className="px-3 py-2 border border-gray-300 rounded-md text-sm"
          >
            <option value="">Max Price</option>
            {PRICE_OPTIONS.filter((o) => o.value).map((o) => (
              <option key={o.value} value={o.value}>
                Up to {o.label}
              </option>
            ))}
          </select>

          <select
            value={searchParams.get("min_beds") || ""}
            onChange={(e) => updateFilters("min_beds", e.target.value)}
            className="px-3 py-2 border border-gray-300 rounded-md text-sm"
          >
            <option value="">Beds</option>
            {BEDS_OPTIONS.filter((o) => o.value).map((o) => (
              <option key={o.value} value={o.value}>
                {o.label} beds
              </option>
            ))}
          </select>

          <select
            value={searchParams.get("property_type") || ""}
            onChange={(e) => updateFilters("property_type", e.target.value)}
            className="px-3 py-2 border border-gray-300 rounded-md text-sm"
          >
            {TYPE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>

          {hasActiveFilters && (
            <button
              onClick={clearAllFilters}
              className="px-3 py-2 text-sm text-red-600 hover:text-red-800 hover:bg-red-50 rounded-md transition"
            >
              Clear Filters
            </button>
          )}

          <select
            value={currentSort}
            onChange={(e) => updateSort(e.target.value)}
            className="px-3 py-2 border border-gray-300 rounded-md text-sm ml-auto"
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                Sort: {o.label}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}
