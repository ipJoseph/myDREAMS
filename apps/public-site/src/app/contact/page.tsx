import type { Metadata } from "next";
import Link from "next/link";

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
            <div className="bg-white border border-gray-200/60 p-8">
              <form
                action={`mailto:Joseph@IntegrityPursuits.com?subject=${encodeURIComponent(
                  listingRef
                    ? `Inquiry about MLS# ${listingRef}`
                    : "Website Inquiry"
                )}`}
                method="post"
                encType="text/plain"
                className="space-y-5"
              >
                {listingRef && (
                  <div className="bg-[var(--color-primary)]/5 border border-[var(--color-primary)]/10 p-4 mb-2">
                    <p className="text-xs text-[var(--color-text-light)] uppercase tracking-wider">Inquiring about</p>
                    <p className="text-sm text-[var(--color-primary)] font-medium mt-1">
                      {addressRef || `MLS# ${listingRef}`}
                    </p>
                  </div>
                )}

                <div>
                  <label
                    htmlFor="name"
                    className="block text-xs font-medium text-[var(--color-text-light)] uppercase tracking-wider mb-2"
                  >
                    Name *
                  </label>
                  <input
                    type="text"
                    id="name"
                    name="name"
                    required
                    className="w-full px-4 py-3 border border-gray-200/60 bg-[var(--color-eggshell)] text-[var(--color-text)] text-sm focus:outline-none focus:border-[var(--color-accent)] transition"
                  />
                </div>

                <div>
                  <label
                    htmlFor="email"
                    className="block text-xs font-medium text-[var(--color-text-light)] uppercase tracking-wider mb-2"
                  >
                    Email *
                  </label>
                  <input
                    type="email"
                    id="email"
                    name="email"
                    required
                    className="w-full px-4 py-3 border border-gray-200/60 bg-[var(--color-eggshell)] text-[var(--color-text)] text-sm focus:outline-none focus:border-[var(--color-accent)] transition"
                  />
                </div>

                <div>
                  <label
                    htmlFor="phone"
                    className="block text-xs font-medium text-[var(--color-text-light)] uppercase tracking-wider mb-2"
                  >
                    Phone
                  </label>
                  <input
                    type="tel"
                    id="phone"
                    name="phone"
                    className="w-full px-4 py-3 border border-gray-200/60 bg-[var(--color-eggshell)] text-[var(--color-text)] text-sm focus:outline-none focus:border-[var(--color-accent)] transition"
                  />
                </div>

                <div>
                  <label
                    htmlFor="message"
                    className="block text-xs font-medium text-[var(--color-text-light)] uppercase tracking-wider mb-2"
                  >
                    Message *
                  </label>
                  <textarea
                    id="message"
                    name="message"
                    rows={5}
                    required
                    defaultValue={
                      listingRef
                        ? `I'm interested in the property at ${addressRef || ""} (MLS# ${listingRef}). Please send me more information.`
                        : ""
                    }
                    className="w-full px-4 py-3 border border-gray-200/60 bg-[var(--color-eggshell)] text-[var(--color-text)] text-sm focus:outline-none focus:border-[var(--color-accent)] transition"
                  />
                </div>

                <button
                  type="submit"
                  className="w-full py-4 bg-[var(--color-accent)] text-[var(--color-primary)] font-semibold text-sm uppercase tracking-wider hover:bg-[var(--color-accent-hover)] transition"
                >
                  Send Message
                </button>

                <p className="text-xs text-[var(--color-text-light)]">
                  Your information is kept private and never shared with third
                  parties.
                </p>
              </form>
            </div>

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
