import Link from "next/link";
import Image from "next/image";
import { searchListings, getStats, getAreas, formatPrice, formatNumber } from "@/lib/api";
import PropertyCard from "@/components/PropertyCard";

export default async function HomePage() {
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
      {/* ============================================
          HERO: Full viewport, mountain background
          ============================================ */}
      <section className="relative min-h-screen flex items-end text-white overflow-hidden">
        {/* Background image */}
        <div
          className="absolute inset-0 bg-cover bg-center bg-no-repeat"
          style={{ backgroundImage: "url('/hero-mountains.jpg')" }}
        />
        {/* Gradient overlay: heavier at bottom for text, lighter at top to show sky */}
        <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/30 to-black/10" />

        {/* Hero content, positioned at bottom-left like Vignette */}
        <div className="relative z-10 w-full pb-20 pt-40">
          <div className="max-w-7xl mx-auto px-6 lg:px-8">
            <div className="max-w-2xl">
              <p className="text-[var(--color-accent)] text-sm uppercase tracking-[0.2em] mb-4">
                Western North Carolina Real Estate
              </p>
              <h1 className="text-5xl md:text-7xl leading-tight mb-6">
                Find Your Place<br />
                in the Mountains
              </h1>
              <p className="text-lg text-white/70 mb-10 max-w-lg">
                Homes, land, and investment properties across the
                Great Smoky Mountains and Blue Ridge.
              </p>

              {/* Search bar */}
              <form action="/listings" method="get" className="mb-8">
                <div className="flex gap-0">
                  <input
                    type="text"
                    name="q"
                    placeholder="Search by city, address, or keyword..."
                    className="flex-1 px-6 py-4 bg-white/10 backdrop-blur-sm border border-white/20 text-white placeholder-white/50 focus:outline-none focus:border-[var(--color-accent)] transition"
                  />
                  <button
                    type="submit"
                    className="px-8 py-4 bg-[var(--color-accent)] text-[var(--color-primary)] font-semibold uppercase tracking-wider text-sm hover:bg-[var(--color-accent-hover)] transition"
                  >
                    Search
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>

        {/* Scroll indicator */}
        <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-10">
          <div className="w-px h-10 bg-white/30 mx-auto mb-2" />
          <span className="text-white/40 text-xs uppercase tracking-widest">Scroll</span>
        </div>
      </section>

      {/* ============================================
          STATS BAR: Dark teal background
          ============================================ */}
      {stats && (
        <section className="bg-[var(--color-primary)] text-white py-16">
          <div className="max-w-7xl mx-auto px-6 lg:px-8">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-8 text-center">
              <div>
                <div className="text-4xl md:text-5xl font-light" style={{ fontFamily: "Georgia, serif" }}>
                  {stats.active_listings.toLocaleString()}
                </div>
                <div className="text-white/50 text-xs uppercase tracking-widest mt-2">
                  Active Listings
                </div>
              </div>
              <div>
                <div className="text-4xl md:text-5xl font-light" style={{ fontFamily: "Georgia, serif" }}>
                  {stats.cities_served}
                </div>
                <div className="text-white/50 text-xs uppercase tracking-widest mt-2">
                  Communities
                </div>
              </div>
              <div>
                <div className="text-4xl md:text-5xl font-light" style={{ fontFamily: "Georgia, serif" }}>
                  {stats.counties_served}
                </div>
                <div className="text-white/50 text-xs uppercase tracking-widest mt-2">
                  Counties
                </div>
              </div>
              <div>
                <div className="text-4xl md:text-5xl font-light" style={{ fontFamily: "Georgia, serif" }}>
                  {formatPrice(stats.avg_price)}
                </div>
                <div className="text-white/50 text-xs uppercase tracking-widest mt-2">
                  Average Price
                </div>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* ============================================
          FEATURED LISTINGS: Dark background
          ============================================ */}
      {featuredListings.length > 0 && (
        <section className="bg-[var(--color-dark)] py-24">
          <div className="max-w-7xl mx-auto px-6 lg:px-8">
            <div className="flex items-end justify-between mb-12">
              <div>
                <p className="text-[var(--color-accent)] text-xs uppercase tracking-[0.2em] mb-3">
                  Just Listed
                </p>
                <h2 className="text-3xl md:text-4xl text-white">
                  New on the Market
                </h2>
              </div>
              <Link
                href="/listings"
                className="hidden md:inline-block text-[var(--color-accent)] text-sm uppercase tracking-wider border-b border-[var(--color-accent)]/30 pb-1 hover:border-[var(--color-accent)] transition"
              >
                View All Properties
              </Link>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
              {featuredListings.map((listing) => (
                <PropertyCard key={listing.id} listing={listing} variant="dark" />
              ))}
            </div>
            <div className="md:hidden text-center mt-10">
              <Link
                href="/listings"
                className="text-[var(--color-accent)] text-sm uppercase tracking-wider border-b border-[var(--color-accent)]/30 pb-1"
              >
                View All Properties
              </Link>
            </div>
          </div>
        </section>
      )}

      {/* ============================================
          AREAS: Eggshell background
          ============================================ */}
      {topAreas.length > 0 && (
        <section className="bg-[var(--color-eggshell)] py-24">
          <div className="max-w-7xl mx-auto px-6 lg:px-8">
            <div className="text-center mb-14">
              <p className="text-[var(--color-accent)] text-xs uppercase tracking-[0.2em] mb-3">
                Our Territory
              </p>
              <h2 className="text-3xl md:text-4xl text-[var(--color-primary)]">
                Areas We Serve
              </h2>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-5">
              {topAreas.map((area) => (
                <Link
                  key={area.name}
                  href={`/listings?city=${encodeURIComponent(area.name)}`}
                  className="group bg-white border border-gray-200/60 p-6 hover:border-[var(--color-accent)] transition-all duration-300"
                >
                  <h3 className="text-lg text-[var(--color-primary)] group-hover:text-[var(--color-accent)] transition-colors" style={{ fontFamily: "Georgia, serif" }}>
                    {area.name}
                  </h3>
                  <p className="text-sm text-[var(--color-text-light)] mt-2">
                    {area.listing_count} listings
                  </p>
                  {area.avg_price && (
                    <p className="text-sm text-[var(--color-text)] mt-1">
                      Avg: {formatPrice(area.avg_price)}
                    </p>
                  )}
                </Link>
              ))}
            </div>
            <div className="text-center mt-10">
              <Link
                href="/areas"
                className="text-[var(--color-primary)] text-sm uppercase tracking-wider border-b border-[var(--color-primary)]/30 pb-1 hover:border-[var(--color-primary)] transition"
              >
                See All Areas
              </Link>
            </div>
          </div>
        </section>
      )}

      {/* ============================================
          ABOUT / INTRO: Split section
          ============================================ */}
      <section className="bg-[var(--color-primary)] text-white">
        <div className="max-w-7xl mx-auto">
          <div className="grid grid-cols-1 lg:grid-cols-2">
            {/* Image side */}
            <div className="relative min-h-[400px] lg:min-h-[500px]">
              <div
                className="absolute inset-0 bg-cover bg-center"
                style={{ backgroundImage: "url('/hero-mountains.jpg')" }}
              />
              <div className="absolute inset-0 bg-[var(--color-primary)]/30" />
            </div>
            {/* Text side */}
            <div className="flex items-center p-12 lg:p-20">
              <div>
                <p className="text-[var(--color-accent)] text-xs uppercase tracking-[0.2em] mb-4">
                  Who We Are
                </p>
                <h2 className="text-3xl md:text-4xl mb-6">
                  Your Mountain<br />Real Estate Team
                </h2>
                <p className="text-white/60 leading-relaxed mb-6">
                  Jon Tharp Homes is a Keller Williams team dedicated to
                  Western North Carolina. We specialize in residential homes,
                  mountain land, farms, and investment properties across the
                  Great Smoky Mountains and Blue Ridge regions.
                </p>
                <p className="text-white/60 leading-relaxed mb-8">
                  With deep local knowledge and access to Carolina Smokies MLS,
                  we help buyers find exactly what they are looking for, whether
                  that is a cozy cabin, a family homestead, or a commercial
                  investment opportunity.
                </p>
                <Link
                  href="/about"
                  className="inline-block text-[var(--color-accent)] text-sm uppercase tracking-wider border border-[var(--color-accent)] px-8 py-3 hover:bg-[var(--color-accent)] hover:text-[var(--color-primary)] transition"
                >
                  Learn More
                </Link>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ============================================
          CTA: Final call to action
          ============================================ */}
      <section className="bg-[var(--color-eggshell)] py-24">
        <div className="max-w-3xl mx-auto px-6 lg:px-8 text-center">
          <p className="text-[var(--color-accent)] text-xs uppercase tracking-[0.2em] mb-4">
            Get Started
          </p>
          <h2 className="text-3xl md:text-4xl text-[var(--color-primary)] mb-6">
            Ready to Find Your Place?
          </h2>
          <p className="text-[var(--color-text-light)] mb-10 max-w-xl mx-auto leading-relaxed">
            Whether you are buying, selling, or exploring your options in
            Western North Carolina, we would love to hear from you.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link
              href="/listings"
              className="px-10 py-4 bg-[var(--color-primary)] text-white text-sm uppercase tracking-wider hover:bg-[var(--color-primary-light)] transition"
            >
              Browse Properties
            </Link>
            <Link
              href="/contact"
              className="px-10 py-4 border border-[var(--color-primary)] text-[var(--color-primary)] text-sm uppercase tracking-wider hover:bg-[var(--color-primary)] hover:text-white transition"
            >
              Contact Us
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
