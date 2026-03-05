import Link from "next/link";
import Image from "next/image";
import { formatPrice, formatNumber } from "@/lib/api";
import type { Metadata } from "next";

interface SharedListing {
  id: string;
  address: string;
  city: string;
  state: string;
  zip: string;
  latitude?: number;
  longitude?: number;
  list_price: number;
  beds?: number;
  baths?: number;
  sqft?: number;
  acreage?: number;
  primary_photo?: string;
  display_order?: number;
  agent_notes?: string;
  mls_number: string;
}

interface SharedCollection {
  name: string;
  description: string;
  status: string;
  listings: SharedListing[];
  listing_count: number;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

async function getSharedCollection(
  token: string
): Promise<SharedCollection | null> {
  try {
    const res = await fetch(`${API_BASE}/api/public/collections/${token}`, {
      next: { revalidate: 300 },
    });
    if (!res.ok) return null;
    const data = await res.json();
    return data.success ? data.data : null;
  } catch {
    return null;
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ token: string }>;
}): Promise<Metadata> {
  const { token } = await params;
  const collection = await getSharedCollection(token);
  if (!collection) {
    return { title: "Route Not Found" };
  }
  return {
    title: `${collection.name} - Route Map`,
    description: `View the route for ${collection.listing_count} properties`,
  };
}

export default async function SharedRouteMapPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  const collection = await getSharedCollection(token);

  if (!collection) {
    return (
      <div className="bg-[var(--color-eggshell)] min-h-screen">
        <div className="h-20 bg-[var(--color-primary)]" />
        <div className="max-w-7xl mx-auto px-6 py-16 text-center">
          <h1
            className="text-3xl text-[var(--color-primary)] mb-4"
            style={{ fontFamily: "Georgia, serif" }}
          >
            Route Not Found
          </h1>
          <p className="text-[var(--color-text-light)] mb-6">
            This collection may have been removed or the link may be incorrect.
          </p>
          <Link
            href="/listings"
            className="inline-block px-6 py-3 bg-[var(--color-accent)] text-[var(--color-primary)] font-semibold text-sm uppercase tracking-wider hover:bg-[var(--color-accent-hover)] transition"
          >
            Browse Properties
          </Link>
        </div>
      </div>
    );
  }

  const geoListings = collection.listings.filter(
    (l) => l.latitude && l.longitude
  );

  return (
    <div className="bg-[var(--color-eggshell)] min-h-screen">
      <div className="h-20 bg-[var(--color-primary)]" />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        {/* Header */}
        <div className="mb-8">
          <Link
            href={`/shared/${token}`}
            className="text-sm text-[var(--color-text-light)] hover:text-[var(--color-accent)] transition"
          >
            &larr; Back to Collection
          </Link>
          <h1
            className="text-3xl text-[var(--color-primary)] mt-4"
            style={{ fontFamily: "Georgia, serif" }}
          >
            {collection.name} - Route Map
          </h1>
          <p className="text-sm text-[var(--color-text-light)] mt-2">
            {collection.listing_count}{" "}
            {collection.listing_count === 1 ? "property" : "properties"}
          </p>
        </div>

        {geoListings.length === 0 ? (
          <div className="text-center py-16">
            <p className="text-[var(--color-text-light)]">
              No location data available for these properties.
            </p>
          </div>
        ) : (
          <>
            {/* Map container - client-side rendered */}
            <div
              id="route-map"
              className="w-full border border-gray-200/60 bg-gray-100"
              style={{ height: "500px" }}
            />

            {/* Property list below map */}
            <div className="mt-8 space-y-4">
              {collection.listings.map((listing, index) => (
                <div
                  key={listing.id}
                  className="flex items-start gap-4 p-4 bg-white border border-gray-200/60"
                >
                  <div className="flex-shrink-0 w-10 h-10 bg-[var(--color-primary)] text-[var(--color-accent)] flex items-center justify-center font-bold text-lg">
                    {index + 1}
                  </div>
                  {listing.primary_photo && (
                    <div className="flex-shrink-0 w-24 h-18 relative overflow-hidden bg-gray-200">
                      <Image
                        src={listing.primary_photo}
                        alt={listing.address}
                        fill
                        sizes="96px"
                        className="object-cover"
                      />
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-baseline gap-3">
                      <span
                        className="text-lg font-light text-[var(--color-primary)]"
                        style={{ fontFamily: "Georgia, serif" }}
                      >
                        {formatPrice(listing.list_price)}
                      </span>
                      <span className="text-sm text-[var(--color-text-light)]">
                        {listing.beds != null && `${listing.beds} bd`}
                        {listing.baths != null && ` / ${listing.baths} ba`}
                        {listing.sqft != null &&
                          ` / ${formatNumber(listing.sqft)} sqft`}
                      </span>
                    </div>
                    <Link
                      href={`/listings/${listing.id}`}
                      className="text-sm text-[var(--color-text)] hover:text-[var(--color-accent)] transition block truncate mt-1"
                    >
                      {listing.address}, {listing.city}, {listing.state}{" "}
                      {listing.zip}
                    </Link>
                    {listing.agent_notes && (
                      <p className="text-xs text-[var(--color-text-light)] mt-1 italic">
                        {listing.agent_notes}
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}

        {/* Footer CTA */}
        <div className="mt-12 text-center">
          <p className="text-sm text-[var(--color-text-light)] mb-4">
            Ready to see these properties in person?
          </p>
          <div className="flex items-center justify-center gap-4">
            <Link
              href="/contact"
              className="inline-block px-8 py-3 bg-[var(--color-accent)] text-[var(--color-primary)] font-semibold text-sm uppercase tracking-wider hover:bg-[var(--color-accent-hover)] transition"
            >
              Schedule Showings
            </Link>
            <Link
              href={`/shared/${token}`}
              className="inline-block px-6 py-3 border border-gray-300 text-sm text-[var(--color-text)] font-semibold uppercase tracking-wider hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] transition"
            >
              View Collection
            </Link>
          </div>
        </div>
      </div>

      {/* Client-side map script */}
      <script
        dangerouslySetInnerHTML={{
          __html: `
            var LISTINGS = ${JSON.stringify(
              geoListings.map((l, i) => ({
                lat: l.latitude,
                lng: l.longitude,
                address: l.address,
                city: l.city,
                price: l.list_price,
                beds: l.beds,
                baths: l.baths,
                sqft: l.sqft,
                num: i + 1,
                id: l.id,
              }))
            )};

            function initRouteMap() {
              if (!LISTINGS.length) return;
              var map = new google.maps.Map(document.getElementById('route-map'), {
                zoom: 10,
                center: { lat: LISTINGS[0].lat, lng: LISTINGS[0].lng },
                mapTypeControl: true,
                streetViewControl: false,
                fullscreenControl: true,
              });

              var bounds = new google.maps.LatLngBounds();
              var infoWindow = new google.maps.InfoWindow();

              LISTINGS.forEach(function(listing) {
                var pos = { lat: listing.lat, lng: listing.lng };
                var marker = new google.maps.Marker({
                  position: pos,
                  map: map,
                  label: { text: String(listing.num), color: '#1B3A4B', fontWeight: '700', fontSize: '12px' },
                  icon: {
                    path: 'M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z',
                    fillColor: '#C5A55A',
                    fillOpacity: 1,
                    strokeColor: '#1B3A4B',
                    strokeWeight: 1.5,
                    scale: 1.8,
                    anchor: new google.maps.Point(12, 22),
                    labelOrigin: new google.maps.Point(12, 9),
                  },
                  title: listing.num + '. ' + listing.address,
                });
                bounds.extend(pos);

                marker.addListener('click', function() {
                  var price = listing.price ? '$' + listing.price.toLocaleString() : 'Price N/A';
                  var details = [];
                  if (listing.beds) details.push(listing.beds + ' bd');
                  if (listing.baths) details.push(listing.baths + ' ba');
                  if (listing.sqft) details.push(listing.sqft.toLocaleString() + ' sqft');
                  var html = '<div style="font-family:system-ui;max-width:250px">' +
                    '<div style="font-size:16px;font-weight:700;color:#1B3A4B">' + listing.num + '. ' + price + '</div>' +
                    '<div style="font-size:13px;color:#333;margin-top:2px">' + listing.address + '</div>' +
                    '<div style="font-size:12px;color:#666">' + listing.city + '</div>' +
                    (details.length ? '<div style="font-size:12px;color:#666;margin-top:4px">' + details.join(' &middot; ') + '</div>' : '') +
                    '<a href="/listings/' + listing.id + '" style="display:inline-block;margin-top:6px;padding:4px 10px;background:#1B3A4B;color:#fff;text-decoration:none;font-size:11px;font-weight:600">View Details</a>' +
                    '</div>';
                  infoWindow.setContent(html);
                  infoWindow.open(map, marker);
                });
              });

              // Draw route line between properties in order
              if (LISTINGS.length > 1) {
                var ds = new google.maps.DirectionsService();
                var dr = new google.maps.DirectionsRenderer({
                  map: map,
                  suppressMarkers: true,
                  polylineOptions: { strokeColor: '#C5A55A', strokeWeight: 3, strokeOpacity: 0.7 },
                });
                var waypoints = LISTINGS.slice(1, -1).map(function(l) {
                  return { location: { lat: l.lat, lng: l.lng }, stopover: true };
                });
                ds.route({
                  origin: { lat: LISTINGS[0].lat, lng: LISTINGS[0].lng },
                  destination: { lat: LISTINGS[LISTINGS.length - 1].lat, lng: LISTINGS[LISTINGS.length - 1].lng },
                  waypoints: waypoints,
                  travelMode: google.maps.TravelMode.DRIVING,
                }, function(result, status) {
                  if (status === 'OK') dr.setDirections(result);
                });
              }

              if (LISTINGS.length > 1) {
                map.fitBounds(bounds, { top: 40, bottom: 40, left: 40, right: 40 });
              }
            }
            window.initRouteMap = initRouteMap;
          `,
        }}
      />
      <script
        async
        defer
        src={`https://maps.googleapis.com/maps/api/js?key=${process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY || ""}&callback=initRouteMap`}
      />
    </div>
  );
}
