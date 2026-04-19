"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { useUser } from "@/hooks/useUser";
import { getAreasClient, getFilteredStats } from "@/lib/api";
import type { Area, FilteredStats } from "@/lib/types";
import ViewToggle from "./ViewToggle";
import AuthModal from "./AuthModal";

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

const STATUS_OPTIONS = [
  { label: "Active", value: "" },
  { label: "Pending", value: "PENDING" },
  { label: "Sold", value: "SOLD" },
];

const SORT_OPTIONS = [
  { label: "Newest", value: "list_date:desc" },
  { label: "Price: Low to High", value: "list_price:asc" },
  { label: "Price: High to Low", value: "list_price:desc" },
  { label: "Beds", value: "beds:desc" },
  { label: "Sqft", value: "sqft:desc" },
  { label: "Acreage", value: "acreage:desc" },
  { label: "Elevation: High to Low", value: "elevation_feet:desc" },
  { label: "Elevation: Low to High", value: "elevation_feet:asc" },
  { label: "Recently Sold", value: "sold_date:desc" },
];

function fmtCurrency(n: number | null | undefined): string {
  if (n == null) return "\u2014";
  if (n >= 1000000) return `$${(n / 1000000).toFixed(1)}M`;
  if (n >= 1000) return `$${Math.round(n / 1000)}k`;
  return `$${n}`;
}

function fmtNum(n: number | null | undefined): string {
  if (n == null) return "\u2014";
  return n.toLocaleString();
}

const SEL =
  "px-3 py-2 bg-white/10 border border-white/20 text-white text-sm focus:outline-none focus:border-[var(--color-accent)] [&>option]:text-gray-900";

export default function SearchFilters() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const searchInputRef = useRef<HTMLInputElement>(null);
  const { session } = useUser();
  const [showAuth, setShowAuth] = useState(false);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved">("idle");
  const [cities, setCities] = useState<Area[]>([]);
  const [counties, setCounties] = useState<Area[]>([]);
  const [stats, setStats] = useState<FilteredStats | null>(null);
  const [listening, setListening] = useState(false);

  // Load city/county options once
  useEffect(() => {
    getAreasClient("city").then(setCities).catch(() => {});
    getAreasClient("county").then(setCounties).catch(() => {});
  }, []);

  // Load filtered stats when search params change
  useEffect(() => {
    const p: Record<string, string> = {};
    for (const [k, v] of searchParams.entries()) {
      if (v && !["sort", "order", "page", "view"].includes(k)) p[k] = v;
    }
    getFilteredStats(p).then(setStats).catch(() => {});
  }, [searchParams]);

  const updateFilters = useCallback(
    (key: string, value: string) => {
      const params = new URLSearchParams(searchParams.toString());
      if (value) params.set(key, value);
      else params.delete(key);
      params.delete("page");
      router.push(`/listings?${params.toString()}`);
    },
    [router, searchParams],
  );

  const applyMultipleFilters = useCallback(
    (filters: Record<string, string>) => {
      const params = new URLSearchParams(searchParams.toString());
      for (const [k, v] of Object.entries(filters)) {
        if (v) params.set(k, v);
        else params.delete(k);
      }
      params.delete("page");
      params.delete("q"); // Clear raw text when applying structured filters
      router.push(`/listings?${params.toString()}`);
    },
    [router, searchParams],
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
    [router, searchParams],
  );

  const clearAllFilters = useCallback(() => router.push("/listings"), [router]);

  // Submit search: try NLP parser first, fall back to raw text
  const submitSearch = useCallback(
    async (text: string) => {
      if (!text.trim()) {
        updateFilters("q", "");
        return;
      }
      // Try the NLP parser to extract structured filters
      try {
        const res = await fetch(`/api/public/search/parse?q=${encodeURIComponent(text)}`);
        if (res.ok) {
          const data = await res.json();
          const parsed = data.data || data;
          // If the parser extracted meaningful filters, apply them
          const filters: Record<string, string> = {};
          if (parsed.city) filters.city = parsed.city;
          if (parsed.county) filters.county = parsed.county;
          if (parsed.min_price) filters.min_price = String(parsed.min_price);
          if (parsed.max_price) filters.max_price = String(parsed.max_price);
          if (parsed.min_beds) filters.min_beds = String(parsed.min_beds);
          if (parsed.min_baths) filters.min_baths = String(parsed.min_baths);
          if (parsed.min_elevation) filters.min_elevation = String(parsed.min_elevation);
          if (parsed.max_elevation) filters.max_elevation = String(parsed.max_elevation);
          if (parsed.min_acreage) filters.min_acreage = String(parsed.min_acreage);
          if (parsed.min_sqft) filters.min_sqft = String(parsed.min_sqft);
          if (parsed.property_type) filters.property_type = parsed.property_type;

          if (Object.keys(filters).length > 0) {
            applyMultipleFilters(filters);
            return;
          }
        }
      } catch {
        // Parser unavailable, fall through to raw text
      }
      // Fall back to raw text search
      updateFilters("q", text);
    },
    [updateFilters, applyMultipleFilters],
  );

  // Voice input (Web Speech API)
  const startVoice = useCallback(() => {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) { alert("Voice input is not supported in this browser."); return; }
    const rec = new SR();
    rec.lang = "en-US";
    rec.interimResults = false;
    rec.onstart = () => setListening(true);
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    rec.onresult = (e: any) => {
      const text = e.results[0][0].transcript;
      if (searchInputRef.current) searchInputRef.current.value = text;
      submitSearch(text);
    };
    rec.start();
  }, [submitSearch]);

  const currentSort = `${searchParams.get("sort") || "list_date"}:${searchParams.get("order") || "desc"}`;
  const hasFilters = Array.from(searchParams.entries()).some(
    ([k]) => !["sort", "order", "page", "view"].includes(k),
  );

  return (
    <div className="bg-[var(--color-primary)] text-white sticky top-0 z-10">
      <div className="max-w-7xl mx-auto px-6 lg:px-8 py-5">

        {/* Search bar + voice */}
        <div className="flex gap-0 mb-4">
          <input
            ref={searchInputRef}
            type="text"
            placeholder="Try '3 bed cabin under 400k in Sylva' or an MLS#..."
            defaultValue={searchParams.get("q") || ""}
            onKeyDown={(e) => {
              if (e.key === "Enter") submitSearch((e.target as HTMLInputElement).value);
            }}
            className="flex-1 px-5 py-3 bg-white/10 border border-white/20 text-white placeholder-white/40 text-sm focus:outline-none focus:border-[var(--color-accent)] transition"
          />
          <button
            onClick={startVoice}
            title="Voice search"
            className={`px-4 py-3 border border-white/20 border-l-0 transition ${
              listening
                ? "bg-red-500/80 text-white animate-pulse"
                : "bg-white/10 text-white/60 hover:text-white hover:bg-white/20"
            }`}
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
            </svg>
          </button>
          <button
            onClick={() => submitSearch(searchInputRef.current?.value || "")}
            className="px-6 py-3 bg-[var(--color-accent)] text-[var(--color-primary)] text-sm font-semibold uppercase tracking-wider hover:bg-[var(--color-accent-hover)] transition"
          >
            Search
          </button>
        </div>

        {/* All filters on one row */}
        <div className="flex flex-wrap gap-2 items-center">
          <select value={searchParams.get("status") || ""} onChange={(e) => updateFilters("status", e.target.value)} className={SEL}>
            {STATUS_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <select value={searchParams.get("county") || ""} onChange={(e) => updateFilters("county", e.target.value)} className={SEL}>
            <option value="">County</option>
            {counties.map((c) => <option key={c.name} value={c.name}>{c.name} ({c.listing_count})</option>)}
          </select>
          <select value={searchParams.get("city") || ""} onChange={(e) => updateFilters("city", e.target.value)} className={SEL}>
            <option value="">City</option>
            {cities.map((c) => <option key={c.name} value={c.name}>{c.name} ({c.listing_count})</option>)}
          </select>
          <select value={searchParams.get("min_price") || ""} onChange={(e) => updateFilters("min_price", e.target.value)} className={SEL}>
            <option value="">Min $</option>
            {PRICE_OPTIONS.filter((o) => o.value).map((o) => <option key={o.value} value={o.value}>{o.label}+</option>)}
          </select>
          <select value={searchParams.get("max_price") || ""} onChange={(e) => updateFilters("max_price", e.target.value)} className={SEL}>
            <option value="">Max $</option>
            {PRICE_OPTIONS.filter((o) => o.value).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <select value={searchParams.get("min_beds") || ""} onChange={(e) => updateFilters("min_beds", e.target.value)} className={SEL}>
            <option value="">Beds</option>
            {BEDS_OPTIONS.filter((o) => o.value).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <select value={searchParams.get("property_type") || ""} onChange={(e) => updateFilters("property_type", e.target.value)} className={SEL}>
            {TYPE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>

          {hasFilters && (
            <>
              <button onClick={clearAllFilters} className="px-2 py-2 text-xs text-[var(--color-accent)] hover:text-white transition">Clear</button>
              <button
                onClick={async () => {
                  if (!session) { setShowAuth(true); return; }
                  setSaveStatus("saving");
                  const filters: Record<string, string> = {};
                  for (const [k, v] of searchParams.entries()) {
                    if (!["sort", "order", "page", "view"].includes(k) && v) filters[k] = v;
                  }
                  try {
                    await fetch("/api/user/searches", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: filters.city || filters.county || filters.q || "My Search", filters }) });
                    setSaveStatus("saved");
                    setTimeout(() => setSaveStatus("idle"), 2000);
                  } catch { setSaveStatus("idle"); }
                }}
                disabled={saveStatus === "saving"}
                className="px-2 py-2 text-xs text-white/70 hover:text-[var(--color-accent)] transition disabled:opacity-50"
              >
                {saveStatus === "saved" ? "Saved!" : saveStatus === "saving" ? "..." : "Save"}
              </button>
              <AuthModal isOpen={showAuth} onClose={() => setShowAuth(false)} />
            </>
          )}

          <button
            onClick={() => updateFilters("zone", searchParams.get("zone") === "1,2,3" ? "" : "1,2,3")}
            className={`px-2 py-2 text-xs border transition whitespace-nowrap ${
              searchParams.get("zone") === "1,2,3"
                ? "bg-[var(--color-accent)] text-[var(--color-primary)] border-[var(--color-accent)] font-semibold"
                : "bg-white/10 border-white/20 text-white hover:border-[var(--color-accent)]"
            }`}
          >
            Expanded WNC
          </button>

          <ViewToggle />

          <select value={currentSort} onChange={(e) => updateSort(e.target.value)} className={`${SEL} ml-auto`}>
            {SORT_OPTIONS.map((o) => <option key={o.value} value={o.value}>Sort: {o.label}</option>)}
          </select>
        </div>

        {/* Stats summary row */}
        {stats && stats.count > 0 && (
          <div className="flex flex-wrap gap-6 mt-3 pt-3 border-t border-white/10 text-xs text-white/50">
            <span>{fmtNum(stats.count)} listings</span>
            <span>Avg {fmtCurrency(stats.avg_price)}</span>
            <span>Median {fmtCurrency(stats.median_price)}</span>
            <span>Avg {fmtNum(stats.avg_sqft)} sqft</span>
            <span>{fmtCurrency(stats.avg_price_per_sqft)}/sqft</span>
            <span>Avg {stats.avg_dom ?? "\u2014"} DOM</span>
            <span>Avg {stats.avg_lot_acres ?? "\u2014"} acres</span>
          </div>
        )}
      </div>
    </div>
  );
}
