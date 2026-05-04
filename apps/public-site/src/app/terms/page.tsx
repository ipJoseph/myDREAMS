import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Terms of Service",
  description:
    "Terms of Service for WNC Mountain Homes. Rules and conditions for using our website and services, including SMS messaging terms.",
};

export default function TermsPage() {
  return (
    <div>
      {/* Header section */}
      <section className="bg-[var(--color-primary)] text-white pt-32 pb-16">
        <div className="max-w-7xl mx-auto px-6 lg:px-8">
          <p className="text-[var(--color-accent)] text-xs uppercase tracking-[0.2em] mb-3">
            Legal
          </p>
          <h1 className="text-4xl md:text-5xl mb-4">Terms of Service</h1>
          <p className="text-white/60 max-w-2xl leading-relaxed">
            Effective date: May 4, 2026
          </p>
        </div>
      </section>

      {/* Content */}
      <section className="bg-[var(--color-eggshell)] py-20">
        <div className="max-w-4xl mx-auto px-6 lg:px-8">
          <div className="space-y-12 text-[var(--color-text)] leading-relaxed">

            <div>
              <h2 className="text-2xl text-[var(--color-primary)] mb-4" style={{ fontFamily: "Georgia, serif" }}>
                Acceptance of Terms
              </h2>
              <p>
                These Terms of Service (&quot;Terms&quot;) govern your access to and use
                of the website at <strong>wncmountain.homes</strong> (the
                &quot;Site&quot;) and any services offered by WNC Mountain Homes LLC
                (&quot;we,&quot; &quot;us,&quot; or &quot;our&quot;). By using the Site,
                you agree to these Terms. If you do not agree, please do not use the
                Site.
              </p>
            </div>

            <div>
              <h2 className="text-2xl text-[var(--color-primary)] mb-4" style={{ fontFamily: "Georgia, serif" }}>
                Services
              </h2>
              <p className="mb-4">
                The Site provides real estate information including property listings,
                saved searches, area guides, and the ability to contact us about
                specific properties or services. Listing data is provided by Multiple
                Listing Services (MLS) and is deemed reliable but not guaranteed.
              </p>
              <p>
                WNC Mountain Homes LLC is a licensed real estate brokerage operating in
                Western North Carolina. Real estate services described on the Site are
                subject to separate written agreements between you and us.
              </p>
            </div>

            <div>
              <h2 className="text-2xl text-[var(--color-primary)] mb-4" style={{ fontFamily: "Georgia, serif" }}>
                User Accounts
              </h2>
              <p>
                Some features (saving listings, creating collections, saving searches)
                require an account. You agree to provide accurate information and to
                keep your credentials confidential. You are responsible for activity
                that occurs under your account.
              </p>
            </div>

            <div id="sms">
              <h2 className="text-2xl text-[var(--color-primary)] mb-4" style={{ fontFamily: "Georgia, serif" }}>
                SMS / Text Messaging Terms
              </h2>
              <p className="mb-4">
                These SMS Terms apply when you provide a mobile number to WNC Mountain
                Homes LLC and affirmatively opt in to receive text messages from us
                (typically by checking an SMS consent box on a contact, request-info, or
                registration form on this Site).
              </p>
              <h3 className="text-lg text-[var(--color-primary)] font-medium mb-2 mt-4">
                Program Description
              </h3>
              <p className="mb-4">
                The WNC Mountain Homes SMS program sends recurring messages including:
                property listing updates and saved-search alerts; showing requests,
                confirmations, and reminders; market reports and area-specific updates;
                customer-care replies to inquiries you submit; and account-related
                notifications.
              </p>
              <h3 className="text-lg text-[var(--color-primary)] font-medium mb-2 mt-4">
                Message Frequency
              </h3>
              <p className="mb-4">
                Message frequency varies based on your activity, saved searches, and any
                ongoing real estate engagement with us.
              </p>
              <h3 className="text-lg text-[var(--color-primary)] font-medium mb-2 mt-4">
                Message and Data Rates
              </h3>
              <p className="mb-4">
                Message and data rates may apply per your mobile carrier&apos;s plan. We
                are not responsible for charges from your carrier.
              </p>
              <h3 className="text-lg text-[var(--color-primary)] font-medium mb-2 mt-4">
                Help and Opt-Out
              </h3>
              <p className="mb-4">
                Reply <strong>HELP</strong> to any message for help, or contact us at{" "}
                <a href="tel:8282839003" className="text-[var(--color-primary)] underline">
                  (828) 283-9003
                </a>{" "}
                or{" "}
                <a href="mailto:eug.williams@gmail.com" className="text-[var(--color-primary)] underline">
                  eug.williams@gmail.com
                </a>
                . Reply <strong>STOP</strong> at any time to unsubscribe. You will
                receive one confirmation message that you have been unsubscribed, and no
                further messages will be sent.
              </p>
              <h3 className="text-lg text-[var(--color-primary)] font-medium mb-2 mt-4">
                Privacy of Mobile Information
              </h3>
              <p className="mb-4 p-4 bg-white border-l-4 border-[var(--color-accent)]">
                <strong>
                  No mobile information will be shared with third parties or affiliates
                  for marketing or promotional purposes.
                </strong>{" "}
                Information sharing is permitted only with subcontractors (such as our
                SMS aggregator and telephony provider, JustCall) strictly to deliver
                messages you have opted in to receive.
              </p>
              <h3 className="text-lg text-[var(--color-primary)] font-medium mb-2 mt-4">
                Eligibility
              </h3>
              <p className="mb-4">
                You must be at least 18 years old, the account holder or authorized user
                of the mobile number provided, and located in the United States to opt
                in. SMS consent is not a condition of any purchase or service.
              </p>
              <h3 className="text-lg text-[var(--color-primary)] font-medium mb-2 mt-4">
                Carrier Disclaimer
              </h3>
              <p>
                Carriers are not liable for delayed or undelivered messages. We make no
                warranty that messages will be delivered without delay or interruption.
              </p>
            </div>

            <div>
              <h2 className="text-2xl text-[var(--color-primary)] mb-4" style={{ fontFamily: "Georgia, serif" }}>
                Acceptable Use
              </h2>
              <p>
                You agree not to use the Site to violate any law, infringe on
                intellectual property, transmit harmful code, scrape or copy listing
                data in violation of MLS rules, impersonate others, or interfere with
                the Site&apos;s operation.
              </p>
            </div>

            <div>
              <h2 className="text-2xl text-[var(--color-primary)] mb-4" style={{ fontFamily: "Georgia, serif" }}>
                MLS and Listing Data
              </h2>
              <p>
                Property listing information displayed on the Site is provided by
                participating MLSs and the listing brokerages. All information is deemed
                reliable but not guaranteed and should be independently verified.
                Listings may be removed, updated, or modified at any time.
              </p>
            </div>

            <div>
              <h2 className="text-2xl text-[var(--color-primary)] mb-4" style={{ fontFamily: "Georgia, serif" }}>
                Disclaimers
              </h2>
              <p>
                The Site is provided &quot;as is&quot; without warranties of any kind.
                We do not warrant that the Site will be uninterrupted, secure, or
                error-free. Property values, school information, taxes, and other
                third-party data are estimates only.
              </p>
            </div>

            <div>
              <h2 className="text-2xl text-[var(--color-primary)] mb-4" style={{ fontFamily: "Georgia, serif" }}>
                Limitation of Liability
              </h2>
              <p>
                To the fullest extent permitted by law, WNC Mountain Homes LLC will not
                be liable for indirect, incidental, special, consequential, or punitive
                damages arising from your use of the Site.
              </p>
            </div>

            <div>
              <h2 className="text-2xl text-[var(--color-primary)] mb-4" style={{ fontFamily: "Georgia, serif" }}>
                Changes to These Terms
              </h2>
              <p>
                We may update these Terms from time to time. Material changes will be
                posted on this page with an updated effective date. Continued use of
                the Site after changes are posted constitutes acceptance.
              </p>
            </div>

            <div>
              <h2 className="text-2xl text-[var(--color-primary)] mb-4" style={{ fontFamily: "Georgia, serif" }}>
                Contact Us
              </h2>
              <div className="bg-white border border-gray-200/60 p-6">
                <p className="font-medium text-[var(--color-primary)]">WNC Mountain Homes LLC</p>
                <p className="mt-2">1573 Highlands Rd, Franklin, NC 28734</p>
                <p>
                  Phone:{" "}
                  <a href="tel:8282839003" className="text-[var(--color-primary)] hover:underline">
                    (828) 283-9003
                  </a>
                </p>
                <p>
                  Email:{" "}
                  <a href="mailto:eug.williams@gmail.com" className="text-[var(--color-primary)] hover:underline">
                    eug.williams@gmail.com
                  </a>
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="bg-[var(--color-primary)] text-white py-16">
        <div className="max-w-3xl mx-auto px-6 lg:px-8 text-center">
          <h2 className="text-2xl mb-4" style={{ fontFamily: "Georgia, serif" }}>
            Questions?
          </h2>
          <p className="text-white/60 mb-8">
            If anything here is unclear, reach out and we will walk through it with you.
          </p>
          <Link
            href="/contact"
            className="px-10 py-4 border border-[var(--color-accent)] text-[var(--color-accent)] text-sm uppercase tracking-wider hover:bg-[var(--color-accent)] hover:text-[var(--color-primary)] transition"
          >
            Contact Us
          </Link>
        </div>
      </section>
    </div>
  );
}
