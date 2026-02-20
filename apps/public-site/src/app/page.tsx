import Link from "next/link";
import { searchListings, getStats, getAreas, formatPrice } from "@/lib/api";
import PropertyCard from "@/components/PropertyCard";

export default async function HomePage() {
  // Fetch data in parallel
  const [listingsResult, stats, areas] = await Promise.all([
    searchListings({ limit: 6, sort: "list_date", order: "desc" }).catch(
      () => ({ listings: [], pagination: { total: 0, page: 1, limit: 6, pages: 0 } })
    ),
    getStats().catch(() => null),
    getAreas("city").catch(() => []),
  ]);

  const { listings: featuredListings } = listingsResult;
  const topAreas = areas.slice(0, 8);

  return (
    <div>
      {/* Hero Section with mountain background */}
      <section className="relative text-white overflow-hidden">
        {/* Background image */}
        <div
          className="absolute inset-0 bg-cover bg-center bg-no-repeat"
          style={{ backgroundImage: "url('/hero-mountains.jpg')" }}
        />
        {/* Dark overlay for text readability */}
        <div className="absolute inset-0 bg-black/50" />

        {/* Content */}
        <div className="relative z-10 py-24 md:py-32">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
            <h1 className="text-4xl md:text-6xl font-bold mb-4 drop-shadow-lg">
              Find Your Mountain Home
            </h1>
            <p className="text-xl md:text-2xl text-gray-100 mb-10 max-w-2xl mx-auto drop-shadow">
              Search {stats?.active_listings?.toLocaleString() || ""} active
              listings across Western North Carolina.
              From Franklin to Waynesville, Sylva to Bryson City.
            </p>

            {/* Search bar */}
            <form action="/listings" method="get" className="max-w-2xl mx-auto">
              <div className="flex gap-2">
                <input
                  type="text"
                  name="q"
                  placeholder="Search by city, address, or keyword..."
                  className="flex-1 px-6 py-4 rounded-lg text-gray-900 text-lg focus:ring-2 focus:ring-blue-300 shadow-lg"
                />
                <button
                  type="submit"
                  className="px-8 py-4 bg-[var(--color-accent)] text-white font-semibold rounded-lg hover:bg-green-600 transition shadow-lg"
                >
                  Search
                </button>
              </div>
            </form>

            {/* Quick stats */}
            {stats && (
              <div className="flex justify-center gap-8 mt-12 text-sm">
                <div className="bg-black/30 backdrop-blur-sm rounded-lg px-5 py-3">
                  <div className="text-2xl font-bold">
                    {stats.active_listings.toLocaleString()}
                  </div>
                  <div className="text-gray-200">Active Listings</div>
                </div>
                <div className="bg-black/30 backdrop-blur-sm rounded-lg px-5 py-3">
                  <div className="text-2xl font-bold">
                    {stats.cities_served}
                  </div>
                  <div className="text-gray-200">Cities</div>
                </div>
                <div className="bg-black/30 backdrop-blur-sm rounded-lg px-5 py-3">
                  <div className="text-2xl font-bold">
                    {stats.counties_served}
                  </div>
                  <div className="text-gray-200">Counties</div>
                </div>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* Featured Listings */}
      {featuredListings.length > 0 && (
        <section className="py-16">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex items-center justify-between mb-8">
              <h2 className="text-2xl font-bold text-gray-900">
                New Listings
              </h2>
              <Link
                href="/listings"
                className="text-[var(--color-primary)] hover:underline font-medium"
              >
                View All &rarr;
              </Link>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
              {featuredListings.map((listing) => (
                <PropertyCard key={listing.id} listing={listing} />
              ))}
            </div>
          </div>
        </section>
      )}

      {/* Areas We Serve */}
      {topAreas.length > 0 && (
        <section className="py-16 bg-gray-50">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <h2 className="text-2xl font-bold text-gray-900 mb-8">
              Areas We Serve
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {topAreas.map((area) => (
                <Link
                  key={area.name}
                  href={`/listings?city=${encodeURIComponent(area.name)}`}
                  className="bg-white rounded-lg p-5 border border-gray-200 hover:shadow-md transition-shadow"
                >
                  <h3 className="font-semibold text-gray-900">{area.name}</h3>
                  <p className="text-sm text-gray-500 mt-1">
                    {area.listing_count} listings
                  </p>
                  {area.avg_price && (
                    <p className="text-sm text-gray-600 mt-1">
                      Avg: {formatPrice(area.avg_price)}
                    </p>
                  )}
                </Link>
              ))}
            </div>
            <div className="text-center mt-8">
              <Link
                href="/areas"
                className="text-[var(--color-primary)] hover:underline font-medium"
              >
                See All Areas &rarr;
              </Link>
            </div>
          </div>
        </section>
      )}

      {/* CTA Section */}
      <section className="py-16">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <h2 className="text-2xl font-bold text-gray-900 mb-4">
            Ready to Find Your Mountain Home?
          </h2>
          <p className="text-gray-600 mb-8 max-w-xl mx-auto">
            Whether you are looking for a cozy cabin, a family home, mountain
            land, or an investment property, we are here to help you find exactly
            what you need.
          </p>
          <div className="flex gap-4 justify-center">
            <Link
              href="/listings"
              className="px-8 py-3 bg-[var(--color-primary)] text-white rounded-lg font-medium hover:bg-[var(--color-primary-light)] transition"
            >
              Browse Listings
            </Link>
            <Link
              href="/contact"
              className="px-8 py-3 border-2 border-[var(--color-primary)] text-[var(--color-primary)] rounded-lg font-medium hover:bg-gray-50 transition"
            >
              Contact Us
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
