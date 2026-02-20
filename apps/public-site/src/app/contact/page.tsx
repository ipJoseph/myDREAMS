import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Contact Us",
  description:
    "Get in touch with Jon Tharp Homes. We are here to help you with your Western NC real estate needs.",
};

interface PageProps {
  searchParams: Promise<Record<string, string | undefined>>;
}

export default async function ContactPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const listingRef = params.listing;
  const addressRef = params.address;

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
      <h1 className="text-3xl font-bold text-gray-900 mb-2">Contact Us</h1>
      <p className="text-gray-600 mb-10">
        Have a question about a property or want to start your home search? Fill
        out the form below and we will get back to you promptly.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-10">
        {/* Contact form */}
        <div>
          <form
            action={`mailto:info@wncmountain.homes?subject=${encodeURIComponent(
              listingRef
                ? `Inquiry about MLS# ${listingRef}`
                : "Website Inquiry"
            )}`}
            method="post"
            encType="text/plain"
            className="space-y-5"
          >
            <div>
              <label
                htmlFor="name"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                Name *
              </label>
              <input
                type="text"
                id="name"
                name="name"
                required
                className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>

            <div>
              <label
                htmlFor="email"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                Email *
              </label>
              <input
                type="email"
                id="email"
                name="email"
                required
                className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>

            <div>
              <label
                htmlFor="phone"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                Phone
              </label>
              <input
                type="tel"
                id="phone"
                name="phone"
                className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>

            <div>
              <label
                htmlFor="message"
                className="block text-sm font-medium text-gray-700 mb-1"
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
                className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>

            <button
              type="submit"
              className="w-full py-3 bg-[var(--color-primary)] text-white rounded-md font-medium hover:bg-[var(--color-primary-light)] transition"
            >
              Send Message
            </button>

            <p className="text-xs text-gray-500">
              Your information is kept private and never shared with third
              parties.
            </p>
          </form>
        </div>

        {/* Contact info */}
        <div>
          <div className="bg-gray-50 rounded-lg p-6 mb-6">
            <h3 className="font-semibold text-gray-900 mb-4">
              Jon Tharp Homes
            </h3>
            <div className="space-y-3 text-sm text-gray-600">
              <div>
                <span className="font-medium text-gray-900">Brokerage:</span>{" "}
                Keller Williams
              </div>
              <div>
                <span className="font-medium text-gray-900">Service Area:</span>{" "}
                Western North Carolina
              </div>
            </div>
          </div>

          <div className="bg-gray-50 rounded-lg p-6">
            <h3 className="font-semibold text-gray-900 mb-4">
              What to Expect
            </h3>
            <ul className="space-y-3 text-sm text-gray-600">
              <li className="flex gap-3">
                <span className="text-green-600 font-bold">1.</span>
                We will respond within one business day.
              </li>
              <li className="flex gap-3">
                <span className="text-green-600 font-bold">2.</span>
                We will discuss your needs and timeline.
              </li>
              <li className="flex gap-3">
                <span className="text-green-600 font-bold">3.</span>
                We will set up a personalized property search based on your
                criteria.
              </li>
              <li className="flex gap-3">
                <span className="text-green-600 font-bold">4.</span>
                You will receive alerts when new matching properties hit the
                market.
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
