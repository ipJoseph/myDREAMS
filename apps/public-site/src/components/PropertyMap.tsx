"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import {
  APIProvider,
  Map,
  useMap,
  useApiIsLoaded,
  useMapsLibrary,
} from "@vis.gl/react-google-maps";

/* ---------------------------------------------------------------- */
/*  Types & Constants                                                */
/* ---------------------------------------------------------------- */

interface PropertyMapProps {
  latitude: number;
  longitude: number;
  address: string;
  city: string;
  state: string;
  zip: string;
}

type ViewMode = "map" | "satellite" | "streetview";

interface POICategory {
  id: string;
  label: string;
  icon: string;
  type: string;
}

const POI_CATEGORIES: POICategory[] = [
  { id: "bakery", label: "Bakery", icon: "\u{1F950}", type: "bakery" },
  { id: "bank", label: "Bank", icon: "\u{1F3E6}", type: "bank" },
  { id: "cafe", label: "Cafe", icon: "\u2615", type: "cafe" },
  { id: "church", label: "Church", icon: "\u26EA", type: "church" },
  { id: "synagogue", label: "Synagogue", icon: "\u{1F54D}", type: "synagogue" },
  { id: "golf", label: "Golf", icon: "\u26F3", type: "golf_course" },
  { id: "grocery", label: "Grocery", icon: "\u{1F6D2}", type: "supermarket" },
  { id: "hospital", label: "Hospital", icon: "\u{1F3E5}", type: "hospital" },
  { id: "library", label: "Library", icon: "\u{1F4DA}", type: "library" },
  { id: "lodging", label: "Lodging", icon: "\u{1F3E8}", type: "lodging" },
  { id: "park", label: "Park", icon: "\u{1F333}", type: "park" },
  { id: "restaurant", label: "Restaurant", icon: "\u{1F37D}\uFE0F", type: "restaurant" },
  { id: "salon", label: "Salon", icon: "\u{1F487}", type: "beauty_salon" },
];

const SEARCH_RADIUS = 4828; // ~3 miles in meters

/* ---------------------------------------------------------------- */
/*  Main export (guards on API key)                                  */
/* ---------------------------------------------------------------- */

export default function PropertyMap(props: PropertyMapProps) {
  const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_KEY;
  if (!apiKey) return null;
  return <PropertyMapInner {...props} apiKey={apiKey} />;
}

/* ---------------------------------------------------------------- */
/*  Inner component (all hooks live here)                            */
/* ---------------------------------------------------------------- */

function PropertyMapInner({
  latitude,
  longitude,
  address,
  city,
  state,
  zip,
  apiKey,
}: PropertyMapProps & { apiKey: string }) {
  const [viewMode, setViewMode] = useState<ViewMode>("map");
  const [activePOIs, setActivePOIs] = useState<Set<string>>(new Set());

  const togglePOI = useCallback((id: string) => {
    setActivePOIs((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const fullAddress = `${address}, ${city}, ${state} ${zip}`;
  const directionsUrl = `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(fullAddress)}`;

  return (
    <section className="mt-10 mb-8">
      <h2
        className="text-2xl text-[var(--color-primary)] mb-5"
        style={{ fontFamily: "Georgia, serif" }}
      >
        Property Map
      </h2>

      <div className="bg-white border border-gray-200/60 overflow-hidden">
        {/* View mode tabs */}
        <div className="flex border-b border-gray-200/60">
          {([
            { mode: "map" as ViewMode, label: "Map View" },
            { mode: "satellite" as ViewMode, label: "Satellite View" },
            { mode: "streetview" as ViewMode, label: "Street View" },
          ]).map(({ mode, label }) => (
            <button
              key={mode}
              onClick={() => setViewMode(mode)}
              className={`flex-1 py-3 text-xs font-semibold uppercase tracking-wider transition ${
                viewMode === mode
                  ? "bg-[var(--color-accent)] text-[var(--color-primary)]"
                  : "bg-white text-[var(--color-text-light)] hover:bg-gray-50"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Map / Street View */}
        <APIProvider apiKey={apiKey}>
          <div style={{ height: 450 }}>
            {viewMode === "streetview" ? (
              <StreetViewPanel latitude={latitude} longitude={longitude} />
            ) : (
              <MapPanel
                latitude={latitude}
                longitude={longitude}
                viewMode={viewMode}
                activePOIs={activePOIs}
              />
            )}
          </div>
        </APIProvider>

        {/* POI chips (map/satellite modes only) */}
        {viewMode !== "streetview" && (
          <div className="flex gap-2 px-4 py-3 overflow-x-auto border-t border-gray-200/60">
            {POI_CATEGORIES.map((cat) => (
              <button
                key={cat.id}
                onClick={() => togglePOI(cat.id)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition border ${
                  activePOIs.has(cat.id)
                    ? "bg-[var(--color-accent)] border-[var(--color-accent)] text-[var(--color-primary)]"
                    : "bg-white border-gray-200 text-[var(--color-text-light)] hover:border-gray-300"
                }`}
              >
                <span className="text-sm">{cat.icon}</span>
                {cat.label}
              </button>
            ))}
          </div>
        )}

        {/* Directions button */}
        <div className="p-4 border-t border-gray-200/60">
          <a
            href={directionsUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-center gap-2 w-full py-3 bg-[var(--color-primary)] text-white font-semibold text-sm uppercase tracking-wider hover:opacity-90 transition"
          >
            <svg
              className="w-4 h-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"
              />
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"
              />
            </svg>
            Get Directions
          </a>
        </div>
      </div>
    </section>
  );
}

/* ---------------------------------------------------------------- */
/*  MapPanel: Google Map with property marker + POI markers          */
/* ---------------------------------------------------------------- */

function MapPanel({
  latitude,
  longitude,
  viewMode,
  activePOIs,
}: {
  latitude: number;
  longitude: number;
  viewMode: "map" | "satellite";
  activePOIs: Set<string>;
}) {
  const map = useMap();
  const placesLib = useMapsLibrary("places");

  const propertyMarkerRef = useRef<google.maps.Marker | null>(null);
  const poiMarkersRef = useRef<Record<string, google.maps.Marker[]>>({});
  const poiCacheRef = useRef<Record<string, google.maps.places.PlaceResult[]>>({});
  const infoWindowRef = useRef<google.maps.InfoWindow | null>(null);

  const position = { lat: latitude, lng: longitude };

  // Switch map type
  useEffect(() => {
    if (!map) return;
    map.setMapTypeId(viewMode === "satellite" ? "satellite" : "roadmap");
  }, [map, viewMode]);

  // Property marker
  useEffect(() => {
    if (!map) return;

    const pinSvg =
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 36" width="36" height="54">' +
      '<path d="M12 0C5.4 0 0 5.4 0 12c0 9 12 24 12 24s12-15 12-24C24 5.4 18.6 0 12 0z" fill="%23C5A572" stroke="%231B3A4B" stroke-width="1.5"/>' +
      '<circle cx="12" cy="12" r="5" fill="%231B3A4B"/>' +
      "</svg>";

    propertyMarkerRef.current = new google.maps.Marker({
      map,
      position,
      title: "Property Location",
      icon: {
        url: `data:image/svg+xml,${pinSvg}`,
        scaledSize: new google.maps.Size(36, 54),
        anchor: new google.maps.Point(18, 54),
      },
      zIndex: 1000,
    });

    return () => {
      propertyMarkerRef.current?.setMap(null);
      propertyMarkerRef.current = null;
    };
  }, [map, latitude, longitude]);

  // POI markers: add for active categories, remove for deactivated
  useEffect(() => {
    if (!map || !placesLib) return;

    const svc = new placesLib.PlacesService(map);

    // Add markers for each active category that doesn't already have them
    for (const id of Array.from(activePOIs)) {
      if (poiMarkersRef.current[id]) continue;

      const cat = POI_CATEGORIES.find((c) => c.id === id);
      if (!cat) continue;

      // Use cached results if available
      if (poiCacheRef.current[id]) {
        poiMarkersRef.current[id] = buildPOIMarkers(
          map,
          poiCacheRef.current[id],
          cat,
          infoWindowRef,
        );
        continue;
      }

      // Placeholder prevents duplicate requests while fetch is in flight
      poiMarkersRef.current[id] = [];

      svc.nearbySearch(
        { location: position, radius: SEARCH_RADIUS, type: cat.type },
        (results, status) => {
          if (
            status === google.maps.places.PlacesServiceStatus.OK &&
            results
          ) {
            poiCacheRef.current[id] = results;
            // Only create markers if category is still tracked (not toggled off mid-flight)
            if (id in poiMarkersRef.current) {
              poiMarkersRef.current[id] = buildPOIMarkers(
                map,
                results,
                cat,
                infoWindowRef,
              );
            }
          }
        },
      );
    }

    // Remove markers for categories that were toggled off
    for (const id of Object.keys(poiMarkersRef.current)) {
      if (!activePOIs.has(id)) {
        poiMarkersRef.current[id].forEach((m) => m.setMap(null));
        delete poiMarkersRef.current[id];
      }
    }
  }, [map, placesLib, activePOIs, latitude, longitude]);

  // Cleanup everything on unmount
  useEffect(() => {
    return () => {
      propertyMarkerRef.current?.setMap(null);
      Object.values(poiMarkersRef.current)
        .flat()
        .forEach((m) => m.setMap(null));
      poiMarkersRef.current = {};
      infoWindowRef.current?.close();
    };
  }, []);

  return (
    <Map
      defaultCenter={position}
      defaultZoom={14}
      gestureHandling="cooperative"
      zoomControl
      fullscreenControl
      streetViewControl={false}
      mapTypeControl={false}
      style={{ width: "100%", height: "100%" }}
    />
  );
}

/* ---------------------------------------------------------------- */
/*  buildPOIMarkers: create Marker instances for nearby places       */
/* ---------------------------------------------------------------- */

function buildPOIMarkers(
  map: google.maps.Map,
  places: google.maps.places.PlaceResult[],
  cat: POICategory,
  infoWindowRef: { current: google.maps.InfoWindow | null },
): google.maps.Marker[] {
  return places
    .filter((p) => p.geometry?.location)
    .map((place) => {
      const marker = new google.maps.Marker({
        map,
        position: place.geometry!.location!,
        title: place.name || cat.label,
        icon: {
          path: google.maps.SymbolPath.CIRCLE,
          scale: 14,
          fillColor: "#ffffff",
          fillOpacity: 0.95,
          strokeColor: "#C5A572",
          strokeWeight: 2,
        },
        label: { text: cat.icon, fontSize: "14px" },
      });

      const name = escapeHtml(place.name || cat.label);
      const vicinity = place.vicinity ? escapeHtml(place.vicinity) : "";

      const content =
        `<div style="font-family:system-ui,sans-serif;max-width:200px">` +
        `<strong style="color:#1B3A4B">${name}</strong>` +
        (vicinity
          ? `<br><span style="color:#666;font-size:12px">${vicinity}</span>`
          : "") +
        (place.rating
          ? `<br><span style="font-size:12px;color:#666">Rating: ${place.rating}/5</span>`
          : "") +
        `</div>`;

      const iw = new google.maps.InfoWindow({ content });

      marker.addListener("click", () => {
        infoWindowRef.current?.close();
        iw.open(map, marker);
        infoWindowRef.current = iw;
      });

      return marker;
    });
}

/* ---------------------------------------------------------------- */
/*  StreetViewPanel: Google Street View panorama                     */
/* ---------------------------------------------------------------- */

function StreetViewPanel({
  latitude,
  longitude,
}: {
  latitude: number;
  longitude: number;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const apiLoaded = useApiIsLoaded();
  const [status, setStatus] = useState<"loading" | "ok" | "unavailable">(
    "loading",
  );

  useEffect(() => {
    if (!apiLoaded || !containerRef.current) return;

    const pos = { lat: latitude, lng: longitude };

    new google.maps.StreetViewService().getPanorama(
      { location: pos, radius: 100 },
      (_, svStatus) => {
        if (
          svStatus === google.maps.StreetViewStatus.OK &&
          containerRef.current
        ) {
          setStatus("ok");
          new google.maps.StreetViewPanorama(containerRef.current, {
            position: pos,
            pov: { heading: 0, pitch: 0 },
            zoom: 1,
            addressControl: false,
            fullscreenControl: true,
          });
        } else {
          setStatus("unavailable");
        }
      },
    );
  }, [apiLoaded, latitude, longitude]);

  return (
    <div className="relative w-full h-full">
      <div ref={containerRef} className="w-full h-full" />
      {status !== "ok" && (
        <div className="absolute inset-0 flex items-center justify-center bg-gray-50 text-[var(--color-text-light)] text-sm">
          {status === "unavailable"
            ? "Street View is not available for this location"
            : "Loading Street View..."}
        </div>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- */
/*  Utility: escape HTML to prevent XSS in InfoWindow content        */
/* ---------------------------------------------------------------- */

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
