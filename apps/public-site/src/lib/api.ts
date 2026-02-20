/**
 * API client for the myDREAMS public endpoints.
 *
 * In development, requests go through Next.js rewrites to localhost:5000.
 * In production, requests go directly to api.wncmountain.homes.
 */

import type {
  Listing,
  ListingSearchParams,
  Pagination,
  Area,
  ListingStats,
} from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

/**
 * Build the API URL. For server-side calls (SSR), use the full URL.
 * For client-side calls, use the rewrite proxy path.
 */
function apiUrl(path: string): string {
  if (typeof window === "undefined") {
    // Server-side: use full URL
    return `${API_BASE}/api/public${path}`;
  }
  // Client-side: use Next.js rewrite proxy
  return `/api/public${path}`;
}

interface ApiResponse<T> {
  success: boolean;
  data: T;
  error?: { code: string; message: string };
}

interface ListingsResponse {
  success: boolean;
  data: Listing[];
  pagination: Pagination;
}

async function fetchApi<T>(url: string): Promise<T> {
  const res = await fetch(url, { next: { revalidate: 900 } }); // Cache 15 min (matches MLS sync interval)
  if (!res.ok) {
    throw new Error(`API error: ${res.status}`);
  }
  return res.json();
}

/**
 * Search listings with filters and pagination.
 */
export async function searchListings(
  params: ListingSearchParams = {}
): Promise<{ listings: Listing[]; pagination: Pagination }> {
  const searchParams = new URLSearchParams();

  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      searchParams.set(key, String(value));
    }
  }

  const qs = searchParams.toString();
  const url = apiUrl(`/listings${qs ? `?${qs}` : ""}`);
  const data = await fetchApi<ListingsResponse>(url);

  return {
    listings: data.data,
    pagination: data.pagination,
  };
}

/**
 * Get a single listing by ID.
 */
export async function getListing(id: string): Promise<Listing | null> {
  try {
    const url = apiUrl(`/listings/${id}`);
    const data = await fetchApi<ApiResponse<Listing>>(url);
    return data.data;
  } catch {
    return null;
  }
}

/**
 * Get areas (cities or counties) with listing counts.
 */
export async function getAreas(
  type: "city" | "county" = "city"
): Promise<Area[]> {
  const url = apiUrl(`/areas?type=${type}`);
  const data = await fetchApi<ApiResponse<Area[]>>(url);
  return data.data;
}

/**
 * Get aggregate listing statistics.
 */
export async function getStats(): Promise<ListingStats> {
  const url = apiUrl("/stats");
  const data = await fetchApi<ApiResponse<ListingStats>>(url);
  return data.data;
}

/**
 * Format price as USD string.
 */
export function formatPrice(price: number | null | undefined): string {
  if (price == null) return "N/A";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(price);
}

/**
 * Format number with commas.
 */
export function formatNumber(n: number | null | undefined): string {
  if (n == null) return "N/A";
  return new Intl.NumberFormat("en-US").format(n);
}
