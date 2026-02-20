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
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
      <h1 className="text-3xl font-bold text-gray-900 mb-2">
        Areas We Serve
      </h1>
      <p className="text-gray-600 mb-10 max-w-2xl">
        We cover the mountains of Western North Carolina, from the Great Smoky
        Mountains to the Blue Ridge. Browse listings by city or county below.
      </p>

      {/* Cities */}
      <section className="mb-12">
        <h2 className="text-2xl font-semibold text-gray-900 mb-6">
          By City
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {cities.map((area) => (
            <Link
              key={area.name}
              href={`/listings?city=${encodeURIComponent(area.name)}`}
              className="bg-white border border-gray-200 rounded-lg p-5 hover:shadow-md transition-shadow"
            >
              <h3 className="font-semibold text-gray-900 text-lg">
                {area.name}
              </h3>
              <div className="mt-2 text-sm text-gray-500">
                <span className="font-medium text-gray-700">
                  {area.listing_count}
                </span>{" "}
                active listings
              </div>
              <div className="mt-1 text-sm text-gray-500">
                {formatPrice(area.min_price)} - {formatPrice(area.max_price)}
              </div>
              {area.avg_price && (
                <div className="mt-1 text-sm text-gray-500">
                  Avg: {formatPrice(area.avg_price)}
                </div>
              )}
            </Link>
          ))}
        </div>
      </section>

      {/* Counties */}
      <section>
        <h2 className="text-2xl font-semibold text-gray-900 mb-6">
          By County
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {counties.map((area) => (
            <Link
              key={area.name}
              href={`/listings?county=${encodeURIComponent(area.name)}`}
              className="bg-white border border-gray-200 rounded-lg p-5 hover:shadow-md transition-shadow"
            >
              <h3 className="font-semibold text-gray-900 text-lg">
                {area.name} County
              </h3>
              <div className="mt-2 text-sm text-gray-500">
                <span className="font-medium text-gray-700">
                  {area.listing_count}
                </span>{" "}
                active listings
              </div>
              {area.avg_price && (
                <div className="mt-1 text-sm text-gray-500">
                  Avg: {formatPrice(area.avg_price)}
                </div>
              )}
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
