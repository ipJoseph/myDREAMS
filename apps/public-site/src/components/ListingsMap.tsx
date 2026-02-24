"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import {
  APIProvider,
  Map,
  useMap,
} from "@vis.gl/react-google-maps";
import { MarkerClusterer } from "@googlemaps/markerclusterer";
import type { MapListing } from "@/lib/types";
import { fetchMapListings, formatPrice } from "@/lib/api";
import type { ListingSearchParams } from "@/lib/types";

/* ---------------------------------------------------------------- */
/*  Status colors                                                     */
/* ---------------------------------------------------------------- */

function statusColor(status: string): string {
  const s = (status || "").toUpperCase();
  if (s === "ACTIVE") return "#10b981";
  if (s === "PENDING" || s === "CONTINGENT") return "#f59e0b";
  if (s === "SOLD" || s === "CLOSED") return "#ef4444";
  return "#2563eb";
}

/* ---------------------------------------------------------------- */
/*  Main export                                                       */
/* ---------------------------------------------------------------- */

interface ListingsMapProps {
  filters: ListingSearchParams;
}

export default function ListingsMap({ filters }: ListingsMapProps) {
  const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_KEY;
  if (!apiKey) {
    return (
      <div className="flex items-center justify-center h-[600px] bg-gray-100 text-[var(--color-text-light)]">
        Map unavailable (API key not configured)
      </div>
    );
  }

  return (
    <APIProvider apiKey={apiKey}>
      <MapInner filters={filters} />
    </APIProvider>
  );
}

/* ---------------------------------------------------------------- */
/*  MapInner: handles data loading, markers, clustering               */
/* ---------------------------------------------------------------- */

function MapInner({ filters }: { filters: ListingSearchParams }) {
  const map = useMap();
  const [listings, setListings] = useState<MapListing[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedListing, setSelectedListing] = useState<MapListing | null>(null);

  const markersRef = useRef<google.maps.Marker[]>([]);
  const clustererRef = useRef<MarkerClusterer | null>(null);
  const infoWindowRef = useRef<google.maps.InfoWindow | null>(null);

  // Fetch listings when filters change
  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    fetchMapListings(filters)
      .then((data) => {
        if (!cancelled) {
          setListings(data);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [
    filters.status,
    filters.city,
    filters.county,
    filters.min_price,
    filters.max_price,
    filters.min_beds,
    filters.min_baths,
    filters.min_sqft,
    filters.min_acreage,
    filters.property_type,
    filters.q,
  ]);

  // Build markers + clusterer when data or map changes
  useEffect(() => {
    if (!map || listings.length === 0) return;

    // Clean previous
    markersRef.current.forEach((m) => m.setMap(null));
    markersRef.current = [];
    clustererRef.current?.clearMarkers();

    const bounds = new google.maps.LatLngBounds();
    const markers: google.maps.Marker[] = [];

    for (const listing of listings) {
      if (!listing.latitude || !listing.longitude) continue;

      const color = statusColor(listing.status);
      const pos = { lat: listing.latitude, lng: listing.longitude };

      const marker = new google.maps.Marker({
        position: pos,
        title: listing.address,
        icon: {
          path: google.maps.SymbolPath.CIRCLE,
          scale: 8,
          fillColor: color,
          fillOpacity: 0.9,
          strokeColor: "#fff",
          strokeWeight: 2,
        },
      });

      marker.addListener("click", () => {
        setSelectedListing(listing);
        showInfoWindow(map, marker, listing);
      });

      markers.push(marker);
      bounds.extend(pos);
    }

    markersRef.current = markers;

    // Cluster
    clustererRef.current = new MarkerClusterer({
      map,
      markers,
    });

    // Fit bounds with padding
    if (markers.length > 0) {
      map.fitBounds(bounds, { top: 50, bottom: 50, left: 50, right: 50 });
    }

    return () => {
      markersRef.current.forEach((m) => m.setMap(null));
      markersRef.current = [];
      clustererRef.current?.clearMarkers();
      clustererRef.current = null;
    };
  }, [map, listings]);

  const showInfoWindow = useCallback(
    (mapInstance: google.maps.Map, marker: google.maps.Marker, listing: MapListing) => {
      infoWindowRef.current?.close();

      const esc = (s: string) =>
        s
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;");

      const photoHtml = listing.primary_photo
        ? `<img src="${esc(listing.primary_photo)}" style="width:100%;height:120px;object-fit:cover;display:block;" onerror="this.style.display='none'" />`
        : "";

      const stats = [
        listing.beds ? `<strong>${listing.beds}</strong> bd` : "",
        listing.baths ? `<strong>${listing.baths}</strong> ba` : "",
        listing.sqft ? `<strong>${listing.sqft.toLocaleString()}</strong> sqft` : "",
        listing.elevation_feet ? `<strong>${listing.elevation_feet.toLocaleString()}</strong> ft` : "",
      ]
        .filter(Boolean)
        .join(" &middot; ");

      const content = `
        <div style="font-family:system-ui,sans-serif;max-width:280px;margin:-8px -8px 0">
          ${photoHtml}
          <div style="padding:10px 12px">
            <div style="font-size:18px;font-weight:700;color:#1B3A4B">${formatPrice(listing.list_price)}</div>
            <div style="font-size:13px;color:#333;margin-top:2px">${esc(listing.address)}</div>
            <div style="font-size:12px;color:#666">${esc(listing.city)}${listing.county ? `, ${esc(listing.county)} Co.` : ""}</div>
            <div style="font-size:12px;color:#666;margin-top:4px">${stats}</div>
            <a href="/listings/${listing.id}" target="_blank" style="display:inline-block;margin-top:8px;padding:6px 14px;background:#1B3A4B;color:#fff;text-decoration:none;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px">View Details</a>
          </div>
        </div>
      `;

      const iw = new google.maps.InfoWindow({ content });
      iw.open(mapInstance, marker);
      infoWindowRef.current = iw;
    },
    []
  );

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      infoWindowRef.current?.close();
    };
  }, []);

  return (
    <div className="relative">
      <div style={{ height: 600 }}>
        <Map
          defaultCenter={{ lat: 35.4, lng: -83.3 }}
          defaultZoom={9}
          gestureHandling="greedy"
          zoomControl
          fullscreenControl
          streetViewControl={false}
          mapTypeControl
          style={{ width: "100%", height: "100%" }}
        />
      </div>

      {/* Loading overlay */}
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-white/60">
          <div className="inline-block w-8 h-8 border-4 border-[var(--color-primary)]/20 border-t-[var(--color-accent)] rounded-full animate-spin" />
        </div>
      )}

      {/* Legend + count */}
      <div className="flex items-center justify-between px-4 py-3 bg-white border-t border-gray-200/60">
        <div className="flex items-center gap-4 text-xs">
          <span className="flex items-center gap-1.5">
            <span className="inline-block w-3 h-3 rounded-full bg-[#10b981]" />
            Active
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block w-3 h-3 rounded-full bg-[#f59e0b]" />
            Pending
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block w-3 h-3 rounded-full bg-[#ef4444]" />
            Sold
          </span>
        </div>
        <span className="text-xs text-[var(--color-text-light)]">
          {loading ? "Loading..." : `${listings.length.toLocaleString()} properties`}
        </span>
      </div>
    </div>
  );
}
