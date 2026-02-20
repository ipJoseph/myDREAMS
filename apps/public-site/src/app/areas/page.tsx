import type { Metadata } from "next";
import { getAreas } from "@/lib/api";
import AreaCard from "@/components/AreaCard";

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
            {cities.map((area, i) => (
              <AreaCard
                key={area.name}
                name={area.name}
                href={`/listings?city=${encodeURIComponent(area.name)}`}
                listingCount={area.listing_count}
                avgPrice={area.avg_price}
                index={i}
              />
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
            {counties.map((area, i) => (
              <AreaCard
                key={area.name}
                name={`${area.name} County`}
                href={`/listings?county=${encodeURIComponent(area.name)}`}
                listingCount={area.listing_count}
                avgPrice={area.avg_price}
                index={i + 3}
              />
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
