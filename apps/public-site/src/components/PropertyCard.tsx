import Link from "next/link";
import Image from "next/image";
import type { Listing } from "@/lib/types";
import { formatPrice, formatNumber } from "@/lib/api";
import FavoriteButton from "./FavoriteButton";
import AddToCollectionButton from "./AddToCollectionButton";

interface PropertyCardProps {
  listing: Listing;
  variant?: "light" | "dark";
}

export default function PropertyCard({ listing, variant = "light" }: PropertyCardProps) {
  const isDark = variant === "dark";

  return (
    <Link
      href={`/listings/${listing.id}`}
      className={`group block overflow-hidden transition-all duration-300 ${
        isDark
          ? "bg-white/5 hover:bg-white/10"
          : "bg-white border border-gray-200/60 hover:border-[var(--color-accent)] shadow-sm hover:shadow-md"
      }`}
    >
      {/* Photo */}
      <div className="relative aspect-[4/3] bg-gray-900 overflow-hidden">
        {listing.primary_photo ? (
          <Image
            src={listing.primary_photo}
            alt={`${listing.address}, ${listing.city}`}
            fill
            sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
            className="object-cover group-hover:scale-105 transition-transform duration-500"
            loading="lazy"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-gray-600">
            <svg
              className="w-16 h-16"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0h4"
              />
            </svg>
          </div>
        )}
        {/* Status badge */}
        <div className="absolute top-3 left-3">
          <span
            className={`text-xs font-semibold px-2.5 py-1 uppercase tracking-wider ${
              listing.status === "ACTIVE"
                ? "bg-[var(--color-accent)] text-[var(--color-primary)]"
                : listing.status === "PENDING"
                  ? "bg-white/90 text-gray-700"
                  : listing.status === "SOLD" || listing.status === "CLOSED"
                    ? "bg-red-600 text-white"
                    : "bg-gray-600 text-white"
            }`}
          >
            {listing.status === "SOLD" || listing.status === "CLOSED"
              ? listing.sold_date
                ? `Sold ${new Date(listing.sold_date).toLocaleDateString("en-US", { month: "short", year: "numeric" })}`
                : "Sold"
              : listing.status}
          </span>
        </div>
        {/* Days on market */}
        {listing.days_on_market != null && (
          <div className="absolute top-3 right-3 bg-black/60 text-white text-xs font-semibold px-2.5 py-1">
            {listing.days_on_market} DOM
          </div>
        )}
        {/* Favorite + Collection buttons */}
        <div className="absolute bottom-3 left-3 flex items-center gap-2">
          <FavoriteButton listingId={listing.id} />
          <AddToCollectionButton listingId={listing.id} />
        </div>
        {/* Photo count */}
        {listing.photo_count != null && listing.photo_count > 1 && (
          <div className="absolute bottom-3 right-3 bg-black/60 text-white text-xs px-2 py-1">
            {listing.photo_count} photos
          </div>
        )}
      </div>

      {/* Info */}
      <div className="p-5">
        {(listing.status === "SOLD" || listing.status === "CLOSED") && listing.sold_price ? (
          <div>
            <div className={`text-2xl font-light ${isDark ? "text-white" : "text-[var(--color-primary)]"}`}
              style={{ fontFamily: "Georgia, serif" }}>
              {formatPrice(listing.sold_price)}
            </div>
            {listing.sold_price !== listing.list_price && (
              <div className={`text-sm line-through ${isDark ? "text-white/40" : "text-[var(--color-text-light)]"}`}>
                Listed at {formatPrice(listing.list_price)}
              </div>
            )}
          </div>
        ) : (
          <div className={`text-2xl font-light ${isDark ? "text-white" : "text-[var(--color-primary)]"}`}
            style={{ fontFamily: "Georgia, serif" }}>
            {formatPrice(listing.list_price)}
          </div>
        )}
        <div className={`flex items-center gap-3 text-sm mt-2 ${isDark ? "text-white/50" : "text-[var(--color-text-light)]"}`}>
          {listing.beds != null && <span>{listing.beds} bd</span>}
          {listing.baths != null && <span>{listing.baths} ba</span>}
          {listing.sqft != null && (
            <span>{formatNumber(listing.sqft)} sqft</span>
          )}
          {listing.acreage != null && listing.acreage > 0 && (
            <span>{listing.acreage.toFixed(2)} ac</span>
          )}
          {listing.elevation_feet != null && (
            <span>{formatNumber(listing.elevation_feet)} ft elev</span>
          )}
        </div>
        <div className={`text-sm mt-3 truncate ${isDark ? "text-white/70" : "text-[var(--color-text)]"}`}>
          {listing.address}
        </div>
        <div className={`text-sm ${isDark ? "text-white/40" : "text-[var(--color-text-light)]"}`}>
          {listing.city}, {listing.state} {listing.zip}
        </div>
        <div className={`flex items-center justify-between mt-4 pt-3 text-xs border-t ${
          isDark ? "border-white/10 text-white/30" : "border-gray-100 text-[var(--color-text-light)]"
        }`}>
          <span>{listing.property_type}</span>
          <span>MLS# {listing.mls_number}</span>
        </div>
      </div>
    </Link>
  );
}
