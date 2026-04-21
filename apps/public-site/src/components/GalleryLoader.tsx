"use client";

/**
 * GalleryLoader: polling wrapper around PhotoBrowser.
 *
 * Implements PHOTO_PIPELINE_SPEC.md public contract for the detail page.
 *
 * - If the initial gallery_status is 'ready', the photos array arrives
 *   complete and we render PhotoBrowser immediately, no polling.
 * - If 'pending', we render the primary photo only and poll the gallery
 *   endpoint every 2s for up to 30s. When the server flips to 'ready',
 *   we swap in the full local-path array.
 * - If 'skipped' or missing, we show primary only with no polling.
 *
 * The server-side detail endpoint also bumps gallery_priority=10 when
 * it sees a pending listing get viewed, so the backfill worker usually
 * hydrates within a few seconds.
 */
import { useEffect, useRef, useState } from "react";
import PhotoBrowser from "./PhotoBrowser";

interface GalleryLoaderProps {
  listingId: string;
  initialPhotos: string[];
  initialGalleryStatus: "ready" | "pending" | "skipped" | string;
  primaryPhoto: string | null;
  address: string;
  city: string;
}

const POLL_INTERVAL_MS = 2000;
const POLL_MAX_DURATION_MS = 30000;

export default function GalleryLoader({
  listingId,
  initialPhotos,
  initialGalleryStatus,
  primaryPhoto,
  address,
  city,
}: GalleryLoaderProps) {
  const [photos, setPhotos] = useState<string[]>(initialPhotos);
  const [status, setStatus] = useState<string>(initialGalleryStatus);
  const hasPolledRef = useRef(false);

  useEffect(() => {
    if (status !== "pending") return;
    if (hasPolledRef.current) return;
    hasPolledRef.current = true;

    const startedAt = Date.now();
    let cancelled = false;

    const tick = async () => {
      if (cancelled) return;
      if (Date.now() - startedAt > POLL_MAX_DURATION_MS) return;

      try {
        const res = await fetch(`/api/public/listings/${listingId}/gallery`, {
          cache: "no-store",
        });
        if (res.ok) {
          const body = await res.json();
          const data = body?.data;
          if (data?.status === "ready" && Array.isArray(data.photos)) {
            const full = primaryPhoto
              ? [primaryPhoto, ...data.photos.filter((p: string) => p !== primaryPhoto)]
              : data.photos;
            if (!cancelled) {
              setPhotos(full);
              setStatus("ready");
            }
            return;
          }
          if (data?.status === "skipped") {
            if (!cancelled) setStatus("skipped");
            return;
          }
        }
      } catch {
        // swallow; next tick will retry
      }

      if (!cancelled) {
        setTimeout(tick, POLL_INTERVAL_MS);
      }
    };

    setTimeout(tick, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
    };
  }, [listingId, status, primaryPhoto]);

  const isHydrating = status === "pending";

  return (
    <div className="relative">
      <PhotoBrowser photos={photos} address={address} city={city} />
      {isHydrating && (
        <div className="pointer-events-none absolute bottom-4 right-4 bg-black/70 text-white text-xs tracking-wider uppercase px-3 py-2 rounded-sm flex items-center gap-2">
          <span
            className="inline-block w-2.5 h-2.5 border-2 border-white border-t-transparent rounded-full animate-spin"
            aria-hidden
          />
          Loading more photos...
        </div>
      )}
    </div>
  );
}
