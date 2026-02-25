import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getListing, formatPrice, formatNumber } from "@/lib/api";
import { getCountyLinks } from "@/lib/countyLinks";
import PhotoBrowser from "@/components/PhotoBrowser";
import PropertyMap from "@/components/PropertyMap";
import PropertyHistory from "@/components/PropertyHistory";

interface PageProps {
  params: Promise<{ id: string }>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { id } = await params;
  const listing = await getListing(id);
  if (!listing) return { title: "Listing Not Found" };

  return {
    title: `${listing.address}, ${listing.city} NC`,
    description: listing.status === "SOLD" || listing.status === "CLOSED"
      ? `${listing.beds} bed, ${listing.baths} bath ${listing.property_type} sold for ${formatPrice(listing.sold_price || listing.list_price)} in ${listing.city}, NC. MLS# ${listing.mls_number}.`
      : `${listing.beds} bed, ${listing.baths} bath ${listing.property_type} for sale at ${formatPrice(listing.list_price)} in ${listing.city}, NC. MLS# ${listing.mls_number}.`,
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
    ? [listing.primary_photo, ...photos.filter((p: string) => p !== listing.primary_photo)]
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
    <div className="bg-[var(--color-eggshell)]">
      {/* Schema.org JSON-LD */}
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(schemaData) }}
      />

      {/* Spacer for transparent header */}
      <div className="h-20 bg-[var(--color-primary)]" />

      {/* Photo gallery */}
      <section className="bg-[var(--color-dark)]">
        <PhotoBrowser photos={allPhotos} address={listing.address} city={listing.city} />
      </section>

      {/* Listing details */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Main content */}
          <div className="lg:col-span-2">
            {/* Header */}
            <div className="mb-8">
              <div className="flex items-start justify-between">
                <div>
                  {(listing.status === "SOLD" || listing.status === "CLOSED") && listing.sold_price ? (
                    <>
                      <h1 className="text-4xl font-light text-[var(--color-primary)]"
                        style={{ fontFamily: "Georgia, serif" }}>
                        Sold for {formatPrice(listing.sold_price)}
                      </h1>
                      {listing.sold_price !== listing.list_price && (
                        <p className="text-lg text-[var(--color-text-light)] line-through mt-1">
                          Listed at {formatPrice(listing.list_price)}
                        </p>
                      )}
                    </>
                  ) : (
                    <h1 className="text-4xl font-light text-[var(--color-primary)]"
                      style={{ fontFamily: "Georgia, serif" }}>
                      {formatPrice(listing.list_price)}
                    </h1>
                  )}
                  <p className="text-lg text-[var(--color-text)] mt-2">
                    {listing.address}
                  </p>
                  <p className="text-[var(--color-text-light)]">
                    {listing.city}, {listing.state} {listing.zip}
                    {listing.county && ` (${listing.county} County)`}
                  </p>
                </div>
                <span
                  className={`text-xs font-semibold px-3 py-1.5 uppercase tracking-wider ${
                    listing.status === "ACTIVE"
                      ? "bg-[var(--color-accent)] text-[var(--color-primary)]"
                      : listing.status === "PENDING"
                        ? "bg-white text-[var(--color-text)]"
                        : listing.status === "SOLD" || listing.status === "CLOSED"
                          ? "bg-red-600 text-white"
                          : "bg-gray-200 text-[var(--color-text)]"
                  }`}
                >
                  {listing.status === "SOLD" || listing.status === "CLOSED"
                    ? listing.sold_date
                      ? `Sold ${new Date(listing.sold_date).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}`
                      : "Sold"
                    : listing.status}
                </span>
              </div>

              {/* Key stats */}
              <div className="flex flex-wrap gap-6 mt-5 text-lg">
                {listing.beds != null && (
                  <div>
                    <span className="font-semibold text-[var(--color-primary)]">{listing.beds}</span>{" "}
                    <span className="text-[var(--color-text-light)]">beds</span>
                  </div>
                )}
                {listing.baths != null && (
                  <div>
                    <span className="font-semibold text-[var(--color-primary)]">{listing.baths}</span>{" "}
                    <span className="text-[var(--color-text-light)]">baths</span>
                  </div>
                )}
                {listing.sqft != null && (
                  <div>
                    <span className="font-semibold text-[var(--color-primary)]">
                      {formatNumber(listing.sqft)}
                    </span>{" "}
                    <span className="text-[var(--color-text-light)]">sqft</span>
                  </div>
                )}
                {listing.acreage != null && listing.acreage > 0 && (
                  <div>
                    <span className="font-semibold text-[var(--color-primary)]">
                      {listing.acreage.toFixed(2)}
                    </span>{" "}
                    <span className="text-[var(--color-text-light)]">acres</span>
                  </div>
                )}
                {listing.elevation_feet != null && (
                  <div>
                    <span className="font-semibold text-[var(--color-primary)]">
                      {formatNumber(listing.elevation_feet)}
                    </span>{" "}
                    <span className="text-[var(--color-text-light)]">ft elevation</span>
                  </div>
                )}
                {listing.year_built != null && (
                  <div>
                    <span className="text-[var(--color-text-light)]">Built</span>{" "}
                    <span className="font-semibold text-[var(--color-primary)]">{listing.year_built}</span>
                  </div>
                )}
              </div>
            </div>

            {/* Description */}
            {listing.public_remarks && (
              <div className="mb-10">
                <h2 className="text-xl text-[var(--color-primary)] mb-3">
                  Description
                </h2>
                <p className="text-[var(--color-text)] leading-relaxed whitespace-pre-line">
                  {listing.public_remarks}
                </p>
              </div>
            )}

            {/* Property details grid */}
            <div className="mb-10">
              <h2 className="text-xl text-[var(--color-primary)] mb-4">
                Property Details
              </h2>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-y-3 text-sm">
                <Detail label="Property Type" value={listing.property_type} />
                <Detail label="MLS #" value={listing.mls_number} />
                <Detail label="MLS Source" value={listing.mls_source} />
                <Detail label="Status" value={listing.status} />
                <Detail label="List Date" value={listing.list_date} />
                {listing.sold_date && (
                  <Detail label="Sold Date" value={new Date(listing.sold_date).toLocaleDateString()} />
                )}
                {listing.sold_price != null && (
                  <Detail label="Sold Price" value={formatPrice(listing.sold_price)} />
                )}
                <Detail label="Days on Market" value={listing.days_on_market?.toString()} />
                <Detail label="Year Built" value={listing.year_built?.toString()} />
                <Detail label="Stories" value={listing.stories?.toString()} />
                <Detail label="Garage Spaces" value={listing.garage_spaces?.toString()} />
                <Detail label="Subdivision" value={listing.subdivision} />
                <Detail label="Elevation" value={listing.elevation_feet ? `${formatNumber(listing.elevation_feet)} ft` : undefined} />
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

            {/* County Records */}
            <CountyRecords county={listing.county} parcelNumber={listing.parcel_number} />

            {/* Property History */}
            <PropertyHistory listingId={listing.id} />
          </div>

          {/* Sidebar */}
          <div className="lg:col-span-1">
            {/* Contact card */}
            <div className="bg-white border border-gray-200/60 p-6 sticky top-24">
              <h3 className="text-[var(--color-primary)] mb-4"
                style={{ fontFamily: "Georgia, serif" }}>
                Interested in this property?
              </h3>
              <Link
                href={`/contact?listing=${listing.mls_number}&address=${encodeURIComponent(listing.address)}`}
                className="block w-full text-center py-3 bg-[var(--color-accent)] text-[var(--color-primary)] font-semibold text-sm uppercase tracking-wider hover:bg-[var(--color-accent-hover)] transition mb-4"
              >
                Request Information
              </Link>

              <a
                href="tel:8282839003"
                className="block w-full text-center py-3 border border-[var(--color-primary)] text-[var(--color-primary)] text-sm uppercase tracking-wider hover:bg-[var(--color-primary)] hover:text-white transition"
              >
                Call (828) 283-9003
              </a>

              {/* Agent info */}
              {listing.listing_agent_name && (
                <div className="border-t border-gray-200/60 pt-4 mt-5">
                  <p className="text-xs text-[var(--color-text-light)] uppercase tracking-wider">Listed by</p>
                  <p className="font-medium text-[var(--color-primary)] mt-1">
                    {listing.listing_agent_name}
                  </p>
                  {listing.listing_office_name && (
                    <p className="text-sm text-[var(--color-text-light)]">
                      {listing.listing_office_name}
                    </p>
                  )}
                </div>
              )}

              {/* Virtual tour */}
              {listing.virtual_tour_url && (
                <div className="border-t border-gray-200/60 pt-4 mt-4">
                  <a
                    href={listing.virtual_tour_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[var(--color-accent)] hover:underline text-sm font-medium uppercase tracking-wider"
                  >
                    View Virtual Tour
                  </a>
                </div>
              )}
            </div>

            {/* MLS disclaimer */}
            <div className="mt-4 p-4 bg-white border border-gray-200/60 text-xs text-[var(--color-text-light)]">
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

        {/* Property Map */}
        {listing.latitude && listing.longitude && (
          <PropertyMap
            latitude={listing.latitude}
            longitude={listing.longitude}
            address={listing.address}
            city={listing.city}
            state={listing.state || "NC"}
            zip={listing.zip}
          />
        )}

        {/* Back link */}
        <div className="mt-10 pt-8 border-t border-gray-200/40">
          <Link
            href="/listings"
            className="text-[var(--color-accent)] text-sm uppercase tracking-wider hover:underline"
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
      <span className="text-[var(--color-text-light)]">{label}:</span>{" "}
      <span className="text-[var(--color-primary)] font-medium">{value}</span>
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
    <div className="mb-10">
      <h2 className="text-xl text-[var(--color-primary)] mb-3">{title}</h2>
      <div className="flex flex-wrap gap-2">
        {items.map((item, i) => (
          <span
            key={i}
            className="px-3 py-1.5 bg-white border border-gray-200/60 text-sm text-[var(--color-text)]"
          >
            {item}
          </span>
        ))}
      </div>
    </div>
  );
}

function CountyRecords({
  county,
  parcelNumber,
}: {
  county: string | undefined;
  parcelNumber: string | undefined;
}) {
  const links = getCountyLinks(county, parcelNumber);
  if (!links || (!links.gisUrl && links.docs.length === 0)) return null;

  return (
    <div className="mb-10">
      <h2 className="text-xl text-[var(--color-primary)] mb-4">
        County Records
      </h2>
      <div className="bg-white border border-gray-200/60 p-5">
        <p className="text-xs text-[var(--color-text-light)] mb-3">
          {county} County public records for parcel {parcelNumber}
        </p>
        <div className="flex flex-wrap gap-3">
          {links.gisUrl && (
            <a
              href={links.gisUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 px-4 py-2.5 bg-[var(--color-primary)] text-white text-sm font-medium hover:opacity-90 transition"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
              </svg>
              GIS Map
            </a>
          )}
          {links.docs.map((doc) => (
            <a
              key={doc.label}
              href={doc.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 px-4 py-2.5 border border-[var(--color-primary)]/20 text-[var(--color-primary)] text-sm font-medium hover:bg-[var(--color-primary)] hover:text-white transition"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              {doc.label}
            </a>
          ))}
        </div>
      </div>
    </div>
  );
}
