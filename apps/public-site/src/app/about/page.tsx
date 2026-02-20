import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "About",
  description:
    "Meet your Western NC real estate team. WNC Mountain Homes, serving the mountain communities of Western North Carolina.",
};

export default function AboutPage() {
  return (
    <div>
      {/* Header section */}
      <section className="bg-[var(--color-primary)] text-white pt-32 pb-16">
        <div className="max-w-7xl mx-auto px-6 lg:px-8">
          <p className="text-[var(--color-accent)] text-xs uppercase tracking-[0.2em] mb-3">
            Who We Are
          </p>
          <h1 className="text-4xl md:text-5xl mb-4">
            About WNC Mountain Homes
          </h1>
          <p className="text-white/60 max-w-2xl leading-relaxed">
            Dedicated to Western North Carolina. We specialize
            in residential homes, mountain land, farms, and investment properties
            across the Great Smoky Mountains and Blue Ridge regions.
          </p>
        </div>
      </section>

      {/* Coverage area */}
      <section className="bg-[var(--color-eggshell)] py-20">
        <div className="max-w-7xl mx-auto px-6 lg:px-8">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-16">
            <div>
              <p className="text-[var(--color-accent)] text-xs uppercase tracking-[0.2em] mb-3">
                Our Coverage
              </p>
              <h2 className="text-3xl text-[var(--color-primary)] mb-6">
                Mountain Communities<br />We Call Home
              </h2>
              <p className="text-[var(--color-text)] leading-relaxed mb-6">
                We serve communities across multiple counties in Western North Carolina.
                Whether you are looking for a cabin in the Smokies, a homestead in
                the Blue Ridge, or a commercial investment in a growing mountain town,
                we know these communities inside and out.
              </p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {[
                { county: "Macon", towns: "Franklin, Highlands" },
                { county: "Haywood", towns: "Waynesville, Maggie Valley, Canton" },
                { county: "Jackson", towns: "Sylva, Cashiers, Dillsboro" },
                { county: "Swain", towns: "Bryson City" },
                { county: "Buncombe", towns: "Asheville, Weaverville, Black Mountain" },
                { county: "Henderson", towns: "Hendersonville, Flat Rock" },
                { county: "Transylvania", towns: "Brevard, Lake Toxaway" },
                { county: "Cherokee", towns: "Murphy, Andrews" },
              ].map((area) => (
                <div key={area.county} className="bg-white border border-gray-200/60 p-5">
                  <h3 className="text-[var(--color-primary)] font-medium" style={{ fontFamily: "Georgia, serif" }}>
                    {area.county} County
                  </h3>
                  <p className="text-sm text-[var(--color-text-light)] mt-1">
                    {area.towns}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Why work with us */}
      <section className="bg-[var(--color-primary)] text-white py-20">
        <div className="max-w-7xl mx-auto px-6 lg:px-8">
          <div className="text-center mb-14">
            <p className="text-[var(--color-accent)] text-xs uppercase tracking-[0.2em] mb-3">
              Our Approach
            </p>
            <h2 className="text-3xl md:text-4xl">
              Why Work With Us
            </h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8 max-w-4xl mx-auto">
            {[
              {
                title: "Local Expertise",
                text: "We live and work in these mountains. We know the neighborhoods, the schools, the best hiking trails, and which roads get icy in winter.",
              },
              {
                title: "MLS Access",
                text: "We pull listings from Carolina Smokies MLS, giving you a comprehensive view of available properties across the region.",
              },
              {
                title: "Data-Driven",
                text: "Our property search and market analysis tools help you make informed decisions based on real data, not just gut feelings.",
              },
              {
                title: "Responsive",
                text: "Real estate moves fast. We prioritize quick, clear communication so you never miss an opportunity.",
              },
            ].map((item) => (
              <div key={item.title} className="border border-white/10 p-8">
                <h3 className="text-[var(--color-accent)] text-lg mb-3" style={{ fontFamily: "Georgia, serif" }}>
                  {item.title}
                </h3>
                <p className="text-white/60 leading-relaxed">
                  {item.text}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="bg-[var(--color-eggshell)] py-24">
        <div className="max-w-3xl mx-auto px-6 lg:px-8 text-center">
          <p className="text-[var(--color-accent)] text-xs uppercase tracking-[0.2em] mb-4">
            Get Started
          </p>
          <h2 className="text-3xl md:text-4xl text-[var(--color-primary)] mb-6">
            Ready to Get Started?
          </h2>
          <p className="text-[var(--color-text-light)] mb-10 max-w-xl mx-auto leading-relaxed">
            Whether you are buying, selling, or just exploring your options in
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
