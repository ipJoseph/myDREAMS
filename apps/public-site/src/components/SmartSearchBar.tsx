"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";

interface ParsedResult {
  filters: Record<string, string | number | boolean>;
  remainder: string;
  interpretations: string[];
  redirect: string | null;
  is_mls_lookup: boolean;
  is_address_lookup: boolean;
}

interface Suggestion {
  type: "city" | "county" | "address";
  value: string;
  label: string;
  count?: number;
  listing_id?: string;
  price?: number;
}

interface SmartSearchBarProps {
  variant: "hero" | "compact";
  defaultValue?: string;
}

export default function SmartSearchBar({ variant, defaultValue = "" }: SmartSearchBarProps) {
  const [query, setQuery] = useState(defaultValue);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [chips, setChips] = useState<string[]>([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [selectedIdx, setSelectedIdx] = useState(-1);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const router = useRouter();

  // Fetch autocomplete suggestions (debounced)
  const fetchSuggestions = useCallback(async (q: string) => {
    if (q.length < 2) {
      setSuggestions([]);
      setShowDropdown(false);
      return;
    }
    try {
      const res = await fetch(`/api/public/autocomplete?q=${encodeURIComponent(q)}&limit=8`);
      const data = await res.json();
      if (data.success && data.data.suggestions.length > 0) {
        setSuggestions(data.data.suggestions);
        setShowDropdown(true);
      } else {
        setSuggestions([]);
        setShowDropdown(false);
      }
    } catch {
      setSuggestions([]);
    }
  }, []);

  // Parse query for chip preview (debounced)
  const fetchChips = useCallback(async (q: string) => {
    if (q.length < 3) {
      setChips([]);
      return;
    }
    try {
      const res = await fetch(`/api/public/search/parse?q=${encodeURIComponent(q)}`);
      const data = await res.json();
      if (data.success && data.data.interpretations.length > 0) {
        setChips(data.data.interpretations);
      } else {
        setChips([]);
      }
    } catch {
      setChips([]);
    }
  }, []);

  // Handle input changes with debounce
  const handleChange = (value: string) => {
    setQuery(value);
    setSelectedIdx(-1);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      fetchSuggestions(value);
      fetchChips(value);
    }, 200);
  };

  // Handle search submission
  const handleSearch = async () => {
    const q = query.trim();
    if (!q) return;

    setLoading(true);
    setShowDropdown(false);

    try {
      const res = await fetch(`/api/public/search/parse?q=${encodeURIComponent(q)}`);
      const data = await res.json();

      if (data.success) {
        const result: ParsedResult = data.data;

        // MLS lookup: redirect to listing detail
        if (result.redirect) {
          window.location.href = result.redirect;
          return;
        }

        // Build URL params from parsed filters
        const params = new URLSearchParams();
        const filterMap: Record<string, string> = {
          city: "city",
          county: "county",
          min_price: "min_price",
          max_price: "max_price",
          min_beds: "min_beds",
          min_baths: "min_baths",
          min_sqft: "min_sqft",
          min_acreage: "min_acreage",
          min_elevation: "min_elevation",
          max_elevation: "max_elevation",
          min_view_score: "min_view_score",
          has_view: "has_view",
          property_type: "property_type",
          q: "q",
        };

        for (const [key, param] of Object.entries(filterMap)) {
          const val = result.filters[key];
          if (val !== undefined && val !== null && val !== "") {
            params.set(param, String(val));
          }
        }

        // Full page navigation (not router.push) to trigger SSR fetch
        window.location.href = `/listings?${params.toString()}`;
      }
    } catch {
      // Fallback: plain text search
      router.push(`/listings?q=${encodeURIComponent(q)}`);
    } finally {
      setLoading(false);
    }
  };

  // Handle suggestion selection (full navigation to trigger SSR)
  const selectSuggestion = (suggestion: Suggestion) => {
    setShowDropdown(false);
    if (suggestion.type === "address" && suggestion.listing_id) {
      window.location.href = `/listings/${suggestion.listing_id}`;
    } else if (suggestion.type === "city") {
      window.location.href = `/listings?city=${encodeURIComponent(suggestion.value)}`;
    } else if (suggestion.type === "county") {
      window.location.href = `/listings?county=${encodeURIComponent(suggestion.value)}`;
    }
  };

  // Keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      if (selectedIdx >= 0 && selectedIdx < suggestions.length) {
        selectSuggestion(suggestions[selectedIdx]);
      } else {
        handleSearch();
      }
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIdx((prev) => Math.min(prev + 1, suggestions.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIdx((prev) => Math.max(prev - 1, -1));
    } else if (e.key === "Escape") {
      setShowDropdown(false);
      setSelectedIdx(-1);
    }
  };

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node) &&
          inputRef.current && !inputRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const isHero = variant === "hero";

  return (
    <div className="relative w-full">
      {/* Search input */}
      <div className="flex gap-0">
        <div className="relative flex-1">
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => handleChange(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => { if (suggestions.length > 0) setShowDropdown(true); }}
            placeholder={isHero
              ? "Try '3 bed cabin under 400k in Sylva' or an MLS#..."
              : "Search by city, MLS#, or try '3 bed under 400k'..."
            }
            className={isHero
              ? "w-full px-6 py-4 bg-white/10 backdrop-blur-sm border border-white/20 text-white placeholder-white/50 focus:outline-none focus:border-[var(--color-accent)] transition text-base"
              : "w-full px-4 py-2.5 bg-white border border-gray-200 text-gray-900 placeholder-gray-400 rounded-l-lg focus:outline-none focus:border-[var(--color-accent)] transition text-sm"
            }
          />
          {loading && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2">
              <div className="w-4 h-4 border-2 border-gray-300 border-t-[var(--color-accent)] rounded-full animate-spin" />
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={handleSearch}
          disabled={loading}
          className={isHero
            ? "px-8 py-4 bg-[var(--color-accent)] text-[var(--color-primary)] font-semibold uppercase tracking-wider text-sm hover:bg-[var(--color-accent-hover)] transition"
            : "px-5 py-2.5 bg-[var(--color-primary)] text-white font-medium text-sm rounded-r-lg hover:bg-[var(--color-primary-light)] transition"
          }
        >
          Search
        </button>
      </div>

      {/* Interpretation chips */}
      {chips.length > 0 && (
        <div className={`flex flex-wrap gap-2 mt-2 ${isHero ? "" : "mt-1.5"}`}>
          {chips.map((chip, i) => (
            <span
              key={i}
              className={isHero
                ? "px-3 py-1 text-xs font-medium rounded-full bg-white/15 text-white/90 backdrop-blur-sm border border-white/20"
                : "px-2.5 py-0.5 text-xs font-medium rounded-full bg-[var(--color-accent)]/10 text-[var(--color-accent-hover)] border border-[var(--color-accent)]/20"
              }
            >
              {chip}
            </span>
          ))}
        </div>
      )}

      {/* Autocomplete dropdown */}
      {showDropdown && suggestions.length > 0 && (
        <div
          ref={dropdownRef}
          className={`absolute z-50 w-full mt-1 bg-white rounded-lg shadow-xl border border-gray-200 overflow-hidden ${isHero ? "max-w-2xl" : ""}`}
        >
          {suggestions.map((s, i) => (
            <button
              key={`${s.type}-${s.value}-${i}`}
              onClick={() => selectSuggestion(s)}
              className={`w-full text-left px-4 py-2.5 flex items-center gap-3 hover:bg-gray-50 transition text-sm ${
                i === selectedIdx ? "bg-gray-50" : ""
              }`}
            >
              {/* Type icon */}
              <span className="flex-shrink-0 w-5 h-5 flex items-center justify-center text-gray-400">
                {s.type === "city" && (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 21h18M5 21V7l8-4v18M13 21V3l6 4v14"/></svg>
                )}
                {s.type === "county" && (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/><circle cx="12" cy="10" r="3"/></svg>
                )}
                {s.type === "address" && (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/></svg>
                )}
              </span>

              {/* Label */}
              <span className="flex-1 text-gray-700">{s.label}</span>

              {/* Count badge or price */}
              {s.count && (
                <span className="text-xs text-gray-400 font-mono">{s.count}</span>
              )}
              {s.price && (
                <span className="text-xs text-gray-400 font-mono">
                  ${(s.price / 1000).toFixed(0)}k
                </span>
              )}

              {/* Type label */}
              <span className="text-xs text-gray-300 uppercase tracking-wide">
                {s.type}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
