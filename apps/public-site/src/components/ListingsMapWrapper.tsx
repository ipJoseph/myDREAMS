"use client";

import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import type { ListingSearchParams } from "@/lib/types";

const ListingsMap = dynamic(() => import("./ListingsMap"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-[600px] bg-gray-100">
      <div className="inline-block w-8 h-8 border-4 border-[var(--color-primary)]/20 border-t-[var(--color-accent)] rounded-full animate-spin" />
    </div>
  ),
});

export default function ListingsMapWrapper() {
  const searchParams = useSearchParams();

  const filters: ListingSearchParams = {
    q: searchParams.get("q") || undefined,
    city: searchParams.get("city") || undefined,
    county: searchParams.get("county") || undefined,
    min_price: searchParams.get("min_price")
      ? parseInt(searchParams.get("min_price")!)
      : undefined,
    max_price: searchParams.get("max_price")
      ? parseInt(searchParams.get("max_price")!)
      : undefined,
    min_beds: searchParams.get("min_beds")
      ? parseInt(searchParams.get("min_beds")!)
      : undefined,
    min_baths: searchParams.get("min_baths")
      ? parseFloat(searchParams.get("min_baths")!)
      : undefined,
    min_sqft: searchParams.get("min_sqft")
      ? parseInt(searchParams.get("min_sqft")!)
      : undefined,
    min_acreage: searchParams.get("min_acreage")
      ? parseFloat(searchParams.get("min_acreage")!)
      : undefined,
    property_type: searchParams.get("property_type") || undefined,
    status: searchParams.get("status") || undefined,
  };

  return <ListingsMap filters={filters} />;
}
