"use client";

import { useEffect } from "react";
import { trackPropertyView } from "@/lib/track";

interface Props {
  listingId: string;
  email?: string;
}

/**
 * Invisible component that fires a "Viewed Property" event on mount.
 * Drop this into the listing detail page server component.
 */
export default function TrackPropertyView({ listingId, email }: Props) {
  useEffect(() => {
    trackPropertyView(listingId, email);
  }, [listingId, email]);

  return null;
}
