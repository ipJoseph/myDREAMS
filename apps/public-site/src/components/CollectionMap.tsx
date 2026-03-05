"use client";

import { useEffect, useRef, useCallback } from "react";
import {
  APIProvider,
  Map,
  useMap,
} from "@vis.gl/react-google-maps";
import { formatPrice } from "@/lib/api";

interface CollectionListing {
  id: string;
  address: string;
  city: string;
  county?: string;
  latitude?: number;
  longitude?: number;
  list_price: number;
  beds?: number;
  baths?: number;
  sqft?: number;
  primary_photo?: string;
  display_order: number;
  agent_notes?: string;
}

interface CollectionMapProps {
  listings: CollectionListing[];
  height?: number;
}

export default function CollectionMap({ listings, height = 500 }: CollectionMapProps) {
  const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_KEY;
  if (!apiKey) {
    return (
      <div
        className="flex items-center justify-center bg-gray-100 text-[var(--color-text-light)]"
        style={{ height }}
      >
        Map unavailable (API key not configured)
      </div>
    );
  }

  const geoListings = listings.filter((l) => l.latitude && l.longitude);
  if (geoListings.length === 0) {
    return (
      <div
        className="flex items-center justify-center bg-gray-100 text-[var(--color-text-light)]"
        style={{ height }}
      >
        No location data available for these properties
      </div>
    );
  }

  return (
    <APIProvider apiKey={apiKey}>
      <CollectionMapInner listings={geoListings} height={height} />
    </APIProvider>
  );
}

function CollectionMapInner({
  listings,
  height,
}: {
  listings: CollectionListing[];
  height: number;
}) {
  const map = useMap();
  const markersRef = useRef<google.maps.Marker[]>([]);
  const infoWindowRef = useRef<google.maps.InfoWindow | null>(null);

  const showInfoWindow = useCallback(
    (
      mapInstance: google.maps.Map,
      marker: google.maps.Marker,
      listing: CollectionListing,
      index: number
    ) => {
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
        listing.sqft
          ? `<strong>${listing.sqft.toLocaleString()}</strong> sqft`
          : "",
      ]
        .filter(Boolean)
        .join(" &middot; ");

      const notesHtml = listing.agent_notes
        ? `<div style="font-size:11px;color:#555;margin-top:6px;padding:6px 8px;background:#f8f6f0;border-radius:4px">${esc(listing.agent_notes)}</div>`
        : "";

      const content = `
        <div style="font-family:system-ui,sans-serif;max-width:280px;margin:-8px -8px 0">
          ${photoHtml}
          <div style="padding:10px 12px">
            <div style="display:flex;align-items:center;gap:8px">
              <span style="background:#C5A55A;color:#1B3A4B;font-weight:700;width:24px;height:24px;display:flex;align-items:center;justify-content:center;font-size:12px;flex-shrink:0">${index + 1}</span>
              <span style="font-size:18px;font-weight:700;color:#1B3A4B">${formatPrice(listing.list_price)}</span>
            </div>
            <div style="font-size:13px;color:#333;margin-top:4px">${esc(listing.address)}</div>
            <div style="font-size:12px;color:#666">${esc(listing.city)}${listing.county ? `, ${esc(listing.county)} Co.` : ""}</div>
            <div style="font-size:12px;color:#666;margin-top:4px">${stats}</div>
            ${notesHtml}
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

  useEffect(() => {
    if (!map || listings.length === 0) return;

    // Clean previous markers
    markersRef.current.forEach((m) => m.setMap(null));
    markersRef.current = [];

    const bounds = new google.maps.LatLngBounds();
    const markers: google.maps.Marker[] = [];

    listings.forEach((listing, index) => {
      if (!listing.latitude || !listing.longitude) return;

      const pos = { lat: listing.latitude, lng: listing.longitude };

      // Numbered gold marker
      const marker = new google.maps.Marker({
        position: pos,
        map,
        title: `${index + 1}. ${listing.address}`,
        label: {
          text: String(index + 1),
          color: "#1B3A4B",
          fontWeight: "bold",
          fontSize: "12px",
        },
        icon: {
          path: "M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z",
          fillColor: "#C5A55A",
          fillOpacity: 1,
          strokeColor: "#1B3A4B",
          strokeWeight: 1.5,
          scale: 1.8,
          anchor: new google.maps.Point(12, 22),
          labelOrigin: new google.maps.Point(12, 9),
        },
        zIndex: listings.length - index, // First items on top
      });

      marker.addListener("click", () => {
        showInfoWindow(map, marker, listing, index);
      });

      markers.push(marker);
      bounds.extend(pos);
    });

    markersRef.current = markers;

    // Fit bounds
    if (markers.length === 1) {
      map.setCenter(markers[0].getPosition()!);
      map.setZoom(14);
    } else if (markers.length > 1) {
      map.fitBounds(bounds, { top: 50, bottom: 50, left: 50, right: 50 });
    }

    return () => {
      markersRef.current.forEach((m) => m.setMap(null));
      markersRef.current = [];
    };
  }, [map, listings, showInfoWindow]);

  // Cleanup info window on unmount
  useEffect(() => {
    return () => {
      infoWindowRef.current?.close();
    };
  }, []);

  return (
    <div style={{ height }}>
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
  );
}
