import Link from "next/link";
import Image from "next/image";
import type { Listing } from "@/lib/types";
import { formatPrice, formatNumber } from "@/lib/api";

interface PropertyCardProps {
  listing: Listing;
}

export default function PropertyCard({ listing }: PropertyCardProps) {
  return (
    <Link
      href={`/listings/${listing.id}`}
      className="group block bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden hover:shadow-md transition-shadow"
    >
      {/* Photo */}
      <div className="relative aspect-[4/3] bg-gray-100 overflow-hidden">
        {listing.primary_photo ? (
          <Image
            src={listing.primary_photo}
            alt={`${listing.address}, ${listing.city}`}
            fill
            sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
            className="object-cover group-hover:scale-105 transition-transform duration-300"
            loading="lazy"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-gray-400">
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
            className={`text-xs font-semibold px-2 py-1 rounded ${
              listing.status === "ACTIVE"
                ? "bg-green-600 text-white"
                : listing.status === "PENDING"
                  ? "bg-yellow-500 text-white"
                  : "bg-gray-600 text-white"
            }`}
          >
            {listing.status}
          </span>
        </div>
        {/* Photo count */}
        {listing.photo_count != null && listing.photo_count > 1 && (
          <div className="absolute bottom-3 right-3 bg-black/60 text-white text-xs px-2 py-1 rounded">
            {listing.photo_count} photos
          </div>
        )}
      </div>

      {/* Info */}
      <div className="p-4">
        <div className="text-xl font-bold text-gray-900">
          {formatPrice(listing.list_price)}
        </div>
        <div className="flex items-center gap-3 text-sm text-gray-600 mt-1">
          {listing.beds != null && <span>{listing.beds} bd</span>}
          {listing.baths != null && <span>{listing.baths} ba</span>}
          {listing.sqft != null && (
            <span>{formatNumber(listing.sqft)} sqft</span>
          )}
          {listing.acreage != null && listing.acreage > 0 && (
            <span>{listing.acreage.toFixed(2)} ac</span>
          )}
        </div>
        <div className="text-sm text-gray-700 mt-2 truncate">
          {listing.address}
        </div>
        <div className="text-sm text-gray-500">
          {listing.city}, {listing.state} {listing.zip}
        </div>
        <div className="flex items-center justify-between mt-3 text-xs text-gray-400">
          <span>{listing.property_type}</span>
          <span>MLS# {listing.mls_number}</span>
        </div>
      </div>
    </Link>
  );
}
