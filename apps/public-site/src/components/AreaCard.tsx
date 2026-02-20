import Link from "next/link";
import { formatPrice } from "@/lib/api";

// City-specific photos (local files in public/areas/)
const CITY_IMAGES: Record<string, string> = {
  "Franklin":       "/areas/franklin.jpg",
  "Waynesville":    "/areas/waynesville.jpg",
  "Sylva":          "/areas/sylva.jpg",
  "Bryson City":    "/areas/bryson-city.jpg",
  "Asheville":      "/areas/asheville.jpg",
  "Highlands":      "/areas/highlands.jpg",
  "Murphy":         "/areas/murphy.jpg",
  "Hendersonville": "/areas/hendersonville.jpg",
  "Brevard":        "/areas/brevard.jpg",
  "Cherokee":       "/areas/cherokee.jpg",
  "Maggie Valley":  "/areas/maggie-valley.jpg",
  "Canton":         "/areas/canton.jpg",
};

// County-specific photos (reuse city photos or generics)
const COUNTY_IMAGES: Record<string, string> = {
  "Macon County":        "/areas/franklin.jpg",
  "Haywood County":      "/areas/waynesville.jpg",
  "Jackson County":      "/areas/sylva.jpg",
  "Swain County":        "/areas/bryson-city.jpg",
  "Buncombe County":     "/areas/asheville.jpg",
  "Henderson County":    "/areas/hendersonville.jpg",
  "Transylvania County": "/areas/brevard.jpg",
  "Cherokee County":     "/areas/cherokee.jpg",
  "Clay County":         "/areas/murphy.jpg",
  "Graham County":       "/areas/mountain-river.jpg",
};

// Fallback images for areas without a specific photo
const FALLBACK_IMAGES = [
  "/areas/mountain-vista.jpg",
  "/areas/mountain-river.jpg",
  "/areas/small-town.jpg",
  "/areas/mountain-forest.jpg",
  "/areas/mountain-lake.jpg",
  "/areas/waterfall.jpg",
];

function getAreaImage(name: string, index: number): string {
  // Check city map first, then county map
  if (CITY_IMAGES[name]) return CITY_IMAGES[name];
  if (COUNTY_IMAGES[name]) return COUNTY_IMAGES[name];

  // For county names coming in as just the county name (without "County")
  const countyKey = `${name} County`;
  if (COUNTY_IMAGES[countyKey]) return COUNTY_IMAGES[countyKey];

  // Fallback: cycle through generic images
  return FALLBACK_IMAGES[index % FALLBACK_IMAGES.length];
}

interface AreaCardProps {
  name: string;
  href: string;
  listingCount: number;
  avgPrice?: number | null;
  index?: number;
}

export default function AreaCard({
  name,
  href,
  listingCount,
  avgPrice,
  index = 0,
}: AreaCardProps) {
  const image = getAreaImage(name, index);

  return (
    <Link
      href={href}
      className="group relative block aspect-[4/3] overflow-hidden transition-all duration-300 shadow-[0_4px_12px_rgba(0,0,0,0.15),0_2px_4px_rgba(0,0,0,0.1)] hover:shadow-[0_12px_28px_rgba(0,0,0,0.25),0_4px_10px_rgba(0,0,0,0.15)] hover:-translate-y-1"
    >
      {/* Background image */}
      <div
        className="absolute inset-0 bg-cover bg-center bg-no-repeat group-hover:scale-110 transition-transform duration-700"
        style={{ backgroundImage: `url('${image}')` }}
      />

      {/* Gradient overlay */}
      <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/30 to-black/5" />

      {/* Content at bottom */}
      <div className="absolute inset-0 flex flex-col justify-end p-5">
        <h3
          className="text-white text-xl group-hover:text-[var(--color-accent)] transition-colors duration-300"
          style={{ fontFamily: "Georgia, serif" }}
        >
          {name}
        </h3>
        <div className="flex items-center gap-3 mt-2">
          <span className="text-white/70 text-sm">
            {listingCount} listings
          </span>
          {avgPrice != null && (
            <>
              <span className="text-white/30">|</span>
              <span className="text-white/70 text-sm">
                Avg {formatPrice(avgPrice)}
              </span>
            </>
          )}
        </div>
      </div>
    </Link>
  );
}
