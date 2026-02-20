import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getListing, formatPrice, formatNumber } from "@/lib/api";

interface PageProps {
  params: Promise<{ id: string }>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { id } = await params;
  const listing = await getListing(id);
  if (!listing) return { title: "Listing Not Found" };

  return {
    title: `${listing.address}, ${listing.city} NC`,
    description: `${listing.beds} bed, ${listing.baths} bath ${listing.property_type} for sale at ${formatPrice(listing.list_price)} in ${listing.city}, NC. MLS# ${listing.mls_number}.`,
  };
}

function parseJsonFeatures(value: string | null | undefined): string[] {
  if (!value) return [];
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return value.split(",").map((s) => s.trim()).filter(Boolean);
  }
}

export default async function ListingDetailPage({ params }: PageProps) {
  const { id } = await params;
  const listing = await getListing(id);

  if (!listing) {
    notFound();
  }

  const photos = Array.isArray(listing.photos) ? listing.photos : [];
  const allPhotos = listing.primary_photo
    ? [listing.primary_photo, ...photos.filter((p) => p !== listing.primary_photo)]
    : photos;

  // Schema.org structured data for SEO
  const schemaData = {
    "@context": "https://schema.org",
    "@type": "RealEstateListing",
    name: `${listing.address}, ${listing.city}, ${listing.state}`,
    url: `https://wncmountain.homes/listings/${listing.id}`,
    datePosted: listing.list_date,
    ...(listing.primary_photo && { image: listing.primary_photo }),
    offers: {
      "@type": "Offer",
      price: listing.list_price,
      priceCurrency: "USD",
    },
    address: {
      "@type": "PostalAddress",
      streetAddress: listing.address,
      addressLocality: listing.city,
      addressRegion: listing.state,
      postalCode: listing.zip,
    },
    ...(listing.latitude && {
      geo: {
        "@type": "GeoCoordinates",
        latitude: listing.latitude,
        longitude: listing.longitude,
      },
    }),
    numberOfRooms: listing.beds,
    numberOfBathroomsTotal: listing.baths,
    floorSize: listing.sqft
      ? { "@type": "QuantitativeValue", value: listing.sqft, unitCode: "FTK" }
      : undefined,
  };

  return (
    <div>
      {/* Schema.org JSON-LD */}
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(schemaData) }}
      />

      {/* Photo gallery */}
      <section className="bg-gray-100">
        <div className="max-w-7xl mx-auto">
          {allPhotos.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-1 max-h-[500px] overflow-hidden">
              <div className="aspect-[4/3] md:aspect-auto md:row-span-2">
                <img
                  src={allPhotos[0]}
                  alt={`${listing.address}, ${listing.city}`}
                  className="w-full h-full object-cover"
                />
              </div>
              <div className="hidden md:grid grid-cols-2 gap-1">
                {allPhotos.slice(1, 5).map((photo, i) => (
                  <div key={i} className="aspect-[4/3] relative">
                    <img
                      src={photo}
                      alt={`Photo ${i + 2}`}
                      className="w-full h-full object-cover"
                      loading="lazy"
                    />
                    {i === 3 && allPhotos.length > 5 && (
                      <div className="absolute inset-0 bg-black/40 flex items-center justify-center text-white font-semibold text-lg">
                        +{allPhotos.length - 5} more
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="h-64 flex items-center justify-center text-gray-400">
              No photos available
            </div>
          )}
        </div>
      </section>

      {/* Listing details */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Main content */}
          <div className="lg:col-span-2">
            {/* Header */}
            <div className="mb-6">
              <div className="flex items-start justify-between">
                <div>
                  <h1 className="text-3xl font-bold text-gray-900">
                    {formatPrice(listing.list_price)}
                  </h1>
                  <p className="text-lg text-gray-700 mt-1">
                    {listing.address}
                  </p>
                  <p className="text-gray-500">
                    {listing.city}, {listing.state} {listing.zip}
                    {listing.county && ` (${listing.county} County)`}
                  </p>
                </div>
                <span
                  className={`text-sm font-semibold px-3 py-1 rounded ${
                    listing.status === "ACTIVE"
                      ? "bg-green-100 text-green-800"
                      : listing.status === "PENDING"
                        ? "bg-yellow-100 text-yellow-800"
                        : "bg-gray-100 text-gray-800"
                  }`}
                >
                  {listing.status}
                </span>
              </div>

              {/* Key stats */}
              <div className="flex flex-wrap gap-6 mt-4 text-lg">
                {listing.beds != null && (
                  <div>
                    <span className="font-bold">{listing.beds}</span>{" "}
                    <span className="text-gray-500">beds</span>
                  </div>
                )}
                {listing.baths != null && (
                  <div>
                    <span className="font-bold">{listing.baths}</span>{" "}
                    <span className="text-gray-500">baths</span>
                  </div>
                )}
                {listing.sqft != null && (
                  <div>
                    <span className="font-bold">
                      {formatNumber(listing.sqft)}
                    </span>{" "}
                    <span className="text-gray-500">sqft</span>
                  </div>
                )}
                {listing.acreage != null && listing.acreage > 0 && (
                  <div>
                    <span className="font-bold">
                      {listing.acreage.toFixed(2)}
                    </span>{" "}
                    <span className="text-gray-500">acres</span>
                  </div>
                )}
                {listing.year_built != null && (
                  <div>
                    <span className="text-gray-500">Built</span>{" "}
                    <span className="font-bold">{listing.year_built}</span>
                  </div>
                )}
              </div>
            </div>

            {/* Description */}
            {listing.public_remarks && (
              <div className="mb-8">
                <h2 className="text-xl font-semibold text-gray-900 mb-3">
                  Description
                </h2>
                <p className="text-gray-600 leading-relaxed whitespace-pre-line">
                  {listing.public_remarks}
                </p>
              </div>
            )}

            {/* Property details grid */}
            <div className="mb-8">
              <h2 className="text-xl font-semibold text-gray-900 mb-3">
                Property Details
              </h2>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-y-3 text-sm">
                <Detail label="Property Type" value={listing.property_type} />
                <Detail label="MLS #" value={listing.mls_number} />
                <Detail label="MLS Source" value={listing.mls_source} />
                <Detail label="Status" value={listing.status} />
                <Detail
                  label="List Date"
                  value={listing.list_date}
                />
                <Detail
                  label="Days on Market"
                  value={listing.days_on_market?.toString()}
                />
                <Detail label="Year Built" value={listing.year_built?.toString()} />
                <Detail label="Stories" value={listing.stories?.toString()} />
                <Detail
                  label="Garage Spaces"
                  value={listing.garage_spaces?.toString()}
                />
                <Detail label="Subdivision" value={listing.subdivision} />
                <Detail
                  label="HOA Fee"
                  value={
                    listing.hoa_fee
                      ? `${formatPrice(listing.hoa_fee)}${listing.hoa_frequency ? ` / ${listing.hoa_frequency}` : ""}`
                      : undefined
                  }
                />
                <Detail
                  label="Taxes"
                  value={
                    listing.tax_annual_amount
                      ? `${formatPrice(listing.tax_annual_amount)}/yr`
                      : undefined
                  }
                />
              </div>
            </div>

            {/* Features */}
            <FeatureSection
              title="Interior Features"
              items={parseJsonFeatures(listing.interior_features)}
            />
            <FeatureSection
              title="Exterior Features"
              items={parseJsonFeatures(listing.exterior_features)}
            />
            <FeatureSection
              title="Heating & Cooling"
              items={[
                ...parseJsonFeatures(listing.heating),
                ...parseJsonFeatures(listing.cooling),
              ]}
            />
            <FeatureSection
              title="Appliances"
              items={parseJsonFeatures(listing.appliances)}
            />
          </div>

          {/* Sidebar */}
          <div className="lg:col-span-1">
            {/* Contact card */}
            <div className="bg-white border border-gray-200 rounded-lg p-6 sticky top-4">
              <h3 className="font-semibold text-gray-900 mb-4">
                Interested in this property?
              </h3>
              <Link
                href={`/contact?listing=${listing.mls_number}&address=${encodeURIComponent(listing.address)}`}
                className="block w-full text-center py-3 bg-[var(--color-primary)] text-white rounded-md font-medium hover:bg-[var(--color-primary-light)] transition mb-4"
              >
                Request Information
              </Link>

              {/* Agent info */}
              {listing.listing_agent_name && (
                <div className="border-t border-gray-200 pt-4 mt-4">
                  <p className="text-sm text-gray-500">Listed by</p>
                  <p className="font-medium text-gray-900">
                    {listing.listing_agent_name}
                  </p>
                  {listing.listing_office_name && (
                    <p className="text-sm text-gray-500">
                      {listing.listing_office_name}
                    </p>
                  )}
                </div>
              )}

              {/* Virtual tour */}
              {listing.virtual_tour_url && (
                <div className="border-t border-gray-200 pt-4 mt-4">
                  <a
                    href={listing.virtual_tour_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-600 hover:underline text-sm font-medium"
                  >
                    View Virtual Tour
                  </a>
                </div>
              )}
            </div>

            {/* MLS disclaimer */}
            <div className="mt-4 p-4 bg-gray-50 rounded-lg text-xs text-gray-500">
              <p>
                Data provided by{" "}
                {listing.mls_source === "NavicaMLS"
                  ? "Carolina Smokies Association of REALTORS"
                  : listing.mls_source === "CanopyMLS"
                    ? "Canopy MLS"
                    : listing.mls_source}
                . All information deemed reliable but not guaranteed.
              </p>
              {listing.updated_at && (
                <p className="mt-1">
                  Last updated: {new Date(listing.updated_at).toLocaleDateString()}
                </p>
              )}
            </div>
          </div>
        </div>

        {/* Back link */}
        <div className="mt-8 pt-8 border-t border-gray-200">
          <Link
            href="/listings"
            className="text-[var(--color-primary)] hover:underline"
          >
            &larr; Back to Search
          </Link>
        </div>
      </div>
    </div>
  );
}

function Detail({
  label,
  value,
}: {
  label: string;
  value: string | undefined | null;
}) {
  if (!value) return null;
  return (
    <div>
      <span className="text-gray-500">{label}:</span>{" "}
      <span className="text-gray-900 font-medium">{value}</span>
    </div>
  );
}

function FeatureSection({
  title,
  items,
}: {
  title: string;
  items: string[];
}) {
  if (items.length === 0) return null;
  return (
    <div className="mb-8">
      <h2 className="text-xl font-semibold text-gray-900 mb-3">{title}</h2>
      <div className="flex flex-wrap gap-2">
        {items.map((item, i) => (
          <span
            key={i}
            className="px-3 py-1 bg-gray-100 rounded-full text-sm text-gray-700"
          >
            {item}
          </span>
        ))}
      </div>
    </div>
  );
}
