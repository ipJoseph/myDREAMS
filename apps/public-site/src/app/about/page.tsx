import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "About",
  description:
    "Meet your Western NC real estate agent. Jon Tharp Homes at Keller Williams, serving the mountain communities of Western North Carolina.",
};

export default function AboutPage() {
  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
      <h1 className="text-3xl font-bold text-gray-900 mb-6">
        About Jon Tharp Homes
      </h1>

      <div className="prose prose-lg max-w-none text-gray-600">
        <p>
          Jon Tharp Homes is a real estate team at Keller Williams, dedicated to
          helping buyers and sellers in Western North Carolina. We specialize in
          residential homes, mountain land, farms, and investment properties
          across the Great Smoky Mountains and Blue Ridge regions.
        </p>

        <h2 className="text-2xl font-semibold text-gray-900 mt-8 mb-4">
          Our Coverage Area
        </h2>
        <p>
          We serve communities across multiple counties in Western NC, including:
        </p>
        <ul className="list-disc pl-6 space-y-1">
          <li>Macon County (Franklin, Highlands)</li>
          <li>Haywood County (Waynesville, Maggie Valley, Canton)</li>
          <li>Jackson County (Sylva, Cashiers, Dillsboro)</li>
          <li>Swain County (Bryson City)</li>
          <li>Buncombe County (Asheville, Weaverville, Black Mountain)</li>
          <li>Henderson County (Hendersonville, Flat Rock)</li>
          <li>Transylvania County (Brevard, Lake Toxaway)</li>
        </ul>

        <h2 className="text-2xl font-semibold text-gray-900 mt-8 mb-4">
          Why Work With Us
        </h2>
        <ul className="list-disc pl-6 space-y-2">
          <li>
            <strong>Local expertise:</strong> We live and work in these
            mountains. We know the neighborhoods, the schools, the best hiking
            trails, and which roads get icy in winter.
          </li>
          <li>
            <strong>Multi-MLS access:</strong> We pull listings from Carolina
            Smokies MLS and Canopy MLS, giving you the widest possible view of
            available properties.
          </li>
          <li>
            <strong>Data-driven:</strong> Our property search and market analysis
            tools help you make informed decisions based on real data, not just
            gut feelings.
          </li>
          <li>
            <strong>Responsive communication:</strong> Real estate moves fast. We
            prioritize quick, clear communication so you never miss an
            opportunity.
          </li>
        </ul>
      </div>

      <div className="mt-12 p-8 bg-gray-50 rounded-lg text-center">
        <h3 className="text-xl font-semibold text-gray-900 mb-3">
          Ready to Get Started?
        </h3>
        <p className="text-gray-600 mb-6">
          Whether you are buying, selling, or just exploring your options, we
          would love to hear from you.
        </p>
        <Link
          href="/contact"
          className="inline-block px-8 py-3 bg-[var(--color-primary)] text-white rounded-lg font-medium hover:bg-[var(--color-primary-light)] transition"
        >
          Contact Us
        </Link>
      </div>
    </div>
  );
}
