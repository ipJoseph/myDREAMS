import type { Metadata } from "next";
import Link from "next/link";
import { getAreas, formatPrice } from "@/lib/api";

export const metadata: Metadata = {
  title: "Areas We Serve",
  description:
    "Explore homes for sale by city and county across Western North Carolina.",
};

export default async function AreasPage() {
  const [cities, counties] = await Promise.all([
    getAreas("city").catch(() => []),
    getAreas("county").catch(() => []),
  ]);

  return (
    <div className="bg-[var(--color-eggshell)]">
      {/* Header section */}
      <section className="bg-[var(--color-primary)] text-white pt-32 pb-16">
        <div className="max-w-7xl mx-auto px-6 lg:px-8">
          <p className="text-[var(--color-accent)] text-xs uppercase tracking-[0.2em] mb-3">
            Our Territory
          </p>
          <h1 className="text-4xl md:text-5xl mb-4">
            Areas We Serve
          </h1>
          <p className="text-white/60 max-w-2xl leading-relaxed">
            We cover the mountains of Western North Carolina, from the Great Smoky
            Mountains to the Blue Ridge. Browse listings by city or county below.
          </p>
        </div>
      </section>

      {/* Cities */}
      <section className="py-16">
        <div className="max-w-7xl mx-auto px-6 lg:px-8">
          <h2 className="text-2xl text-[var(--color-primary)] mb-8">
            By City
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
            {cities.map((area) => (
              <Link
                key={area.name}
                href={`/listings?city=${encodeURIComponent(area.name)}`}
                className="group bg-white border border-gray-200/60 p-6 hover:border-[var(--color-accent)] transition-all duration-300"
              >
                <h3 className="text-lg text-[var(--color-primary)] group-hover:text-[var(--color-accent)] transition-colors"
                  style={{ fontFamily: "Georgia, serif" }}>
                  {area.name}
                </h3>
                <div className="mt-3 text-sm text-[var(--color-text-light)]">
                  <span className="font-medium text-[var(--color-text)]">
                    {area.listing_count}
                  </span>{" "}
                  active listings
                </div>
                <div className="mt-1 text-sm text-[var(--color-text-light)]">
                  {formatPrice(area.min_price)} &ndash; {formatPrice(area.max_price)}
                </div>
                {area.avg_price && (
                  <div className="mt-1 text-sm text-[var(--color-text)]">
                    Avg: {formatPrice(area.avg_price)}
                  </div>
                )}
              </Link>
            ))}
          </div>
        </div>
      </section>

      {/* Counties */}
      <section className="pb-20">
        <div className="max-w-7xl mx-auto px-6 lg:px-8">
          <h2 className="text-2xl text-[var(--color-primary)] mb-8">
            By County
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
            {counties.map((area) => (
              <Link
                key={area.name}
                href={`/listings?county=${encodeURIComponent(area.name)}`}
                className="group bg-white border border-gray-200/60 p-6 hover:border-[var(--color-accent)] transition-all duration-300"
              >
                <h3 className="text-lg text-[var(--color-primary)] group-hover:text-[var(--color-accent)] transition-colors"
                  style={{ fontFamily: "Georgia, serif" }}>
                  {area.name} County
                </h3>
                <div className="mt-3 text-sm text-[var(--color-text-light)]">
                  <span className="font-medium text-[var(--color-text)]">
                    {area.listing_count}
                  </span>{" "}
                  active listings
                </div>
                {area.avg_price && (
                  <div className="mt-1 text-sm text-[var(--color-text)]">
                    Avg: {formatPrice(area.avg_price)}
                  </div>
                )}
              </Link>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
