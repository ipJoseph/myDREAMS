import Link from "next/link";
import { formatPrice } from "@/lib/api";

// Placeholder background images (cycle through these)
// Each uses our mountain hero with a different crop position + tinted overlay
const AREA_THEMES = [
  { position: "center 30%", overlay: "from-[#082d40]/90 via-[#082d40]/50 to-[#082d40]/20" },   // mountain peaks
  { position: "center 70%", overlay: "from-[#0a3d56]/90 via-[#0a3d56]/50 to-[#0a3d56]/20" },   // lower valley
  { position: "left 40%",   overlay: "from-[#1a3a2a]/90 via-[#1a3a2a]/50 to-[#1a3a2a]/20" },   // forest green
  { position: "right 30%",  overlay: "from-[#2d1f0e]/90 via-[#2d1f0e]/50 to-[#2d1f0e]/15" },   // warm earth
  { position: "center 20%", overlay: "from-[#0e2a3d]/90 via-[#0e2a3d]/50 to-[#0e2a3d]/20" },   // dusky blue
  { position: "center 50%", overlay: "from-[#1e3328]/90 via-[#1e3328]/50 to-[#1e3328]/15" },   // deep green
  { position: "left 60%",   overlay: "from-[#3d2e1a]/90 via-[#3d2e1a]/50 to-[#3d2e1a]/15" },   // amber dusk
  { position: "right 45%",  overlay: "from-[#082d40]/90 via-[#082d40]/50 to-[#082d40]/15" },   // teal classic
];

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
  const theme = AREA_THEMES[index % AREA_THEMES.length];

  return (
    <Link
      href={href}
      className="group relative block aspect-[4/3] overflow-hidden transition-all duration-300 shadow-[0_4px_12px_rgba(0,0,0,0.15),0_2px_4px_rgba(0,0,0,0.1)] hover:shadow-[0_12px_28px_rgba(0,0,0,0.25),0_4px_10px_rgba(0,0,0,0.15)] hover:-translate-y-1"
    >
      {/* Background image */}
      <div
        className="absolute inset-0 bg-cover bg-no-repeat group-hover:scale-110 transition-transform duration-700"
        style={{
          backgroundImage: "url('/hero-mountains.jpg')",
          backgroundPosition: theme.position,
        }}
      />

      {/* Gradient overlay */}
      <div className={`absolute inset-0 bg-gradient-to-t ${theme.overlay}`} />

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
