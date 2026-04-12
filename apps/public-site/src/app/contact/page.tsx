import type { Metadata } from "next";
import Link from "next/link";
import ContactForm from "@/components/ContactForm";

export const metadata: Metadata = {
  title: "Contact Us",
  description:
    "Get in touch with WNC Mountain Homes. We are here to help you with your Western NC real estate needs.",
};

interface PageProps {
  searchParams: Promise<Record<string, string | undefined>>;
}

export default async function ContactPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const listingRef = params.listing;
  const addressRef = params.address;

  return (
    <div>
      {/* Header section */}
      <section className="bg-[var(--color-primary)] text-white pt-32 pb-16">
        <div className="max-w-7xl mx-auto px-6 lg:px-8">
          <p className="text-[var(--color-accent)] text-xs uppercase tracking-[0.2em] mb-3">
            Get in Touch
          </p>
          <h1 className="text-4xl md:text-5xl mb-4">
            Contact Us
          </h1>
          <p className="text-white/60 max-w-2xl leading-relaxed">
            Have a question about a property or want to start your home search? We
            would love to hear from you.
          </p>
        </div>
      </section>

      {/* Form section */}
      <section className="bg-[var(--color-eggshell)] py-16">
        <div className="max-w-7xl mx-auto px-6 lg:px-8">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-12">
            {/* Contact form */}
            <ContactForm listingRef={listingRef} addressRef={addressRef} />

            {/* Contact info sidebar */}
            <div className="space-y-6">
              <div className="bg-[var(--color-primary)] text-white p-8">
                <h3 className="text-[var(--color-accent)] text-xs uppercase tracking-widest mb-5">
                  Contact Info
                </h3>
                <div className="space-y-4">
                  <div>
                    <p className="text-white/40 text-xs uppercase tracking-wider">Phone</p>
                    <a href="tel:8282839003" className="text-white hover:text-[var(--color-accent)] transition text-lg">
                      (828) 283-9003
                    </a>
                  </div>
                  <div>
                    <p className="text-white/40 text-xs uppercase tracking-wider">Address</p>
                    <p className="text-white/80 text-sm leading-relaxed mt-1">
                      WNC Mountain Homes<br />
                      1573 Highlands Rd<br />
                      Franklin, NC 28734
                    </p>
                  </div>
                </div>
              </div>

              <div className="bg-white border border-gray-200/60 p-8">
                <h3 className="text-[var(--color-primary)] mb-5" style={{ fontFamily: "Georgia, serif" }}>
                  What to Expect
                </h3>
                <ul className="space-y-4 text-sm text-[var(--color-text)]">
                  <li className="flex gap-3">
                    <span className="text-[var(--color-accent)] font-bold flex-shrink-0">1.</span>
                    We will respond within one business day.
                  </li>
                  <li className="flex gap-3">
                    <span className="text-[var(--color-accent)] font-bold flex-shrink-0">2.</span>
                    We will discuss your needs and timeline.
                  </li>
                  <li className="flex gap-3">
                    <span className="text-[var(--color-accent)] font-bold flex-shrink-0">3.</span>
                    We will set up a personalized property search based on your criteria.
                  </li>
                  <li className="flex gap-3">
                    <span className="text-[var(--color-accent)] font-bold flex-shrink-0">4.</span>
                    You will receive alerts when new matching properties hit the market.
                  </li>
                </ul>
              </div>

              <div className="text-center">
                <Link
                  href="/listings"
                  className="text-[var(--color-primary)] text-sm uppercase tracking-wider border-b border-[var(--color-primary)]/30 pb-1 hover:border-[var(--color-primary)] transition"
                >
                  Browse Properties Instead
                </Link>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
