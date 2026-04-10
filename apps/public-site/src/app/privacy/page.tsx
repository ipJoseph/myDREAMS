import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description:
    "Privacy policy for WNC Mountain Homes. Learn how we collect, use, and protect your personal information.",
};

export default function PrivacyPolicyPage() {
  return (
    <div>
      {/* Header section */}
      <section className="bg-[var(--color-primary)] text-white pt-32 pb-16">
        <div className="max-w-7xl mx-auto px-6 lg:px-8">
          <p className="text-[var(--color-accent)] text-xs uppercase tracking-[0.2em] mb-3">
            Legal
          </p>
          <h1 className="text-4xl md:text-5xl mb-4">Privacy Policy</h1>
          <p className="text-white/60 max-w-2xl leading-relaxed">
            Effective date: March 28, 2026
          </p>
        </div>
      </section>

      {/* Content */}
      <section className="bg-[var(--color-eggshell)] py-20">
        <div className="max-w-4xl mx-auto px-6 lg:px-8">
          <div className="space-y-12 text-[var(--color-text)] leading-relaxed">

            {/* Introduction */}
            <div>
              <h2 className="text-2xl text-[var(--color-primary)] mb-4" style={{ fontFamily: "Georgia, serif" }}>
                Introduction
              </h2>
              <p className="mb-4">
                WNC Mountain Homes LLC (&quot;we,&quot; &quot;us,&quot; or &quot;our&quot;) operates
                the website at <strong>wncmountain.homes</strong> (the &quot;Site&quot;). This
                Privacy Policy describes how we collect, use, disclose, and protect
                your personal information when you visit our Site or use our services,
                including any integrations with third-party platforms.
              </p>
              <p>
                By using our Site, you agree to the collection and use of information
                in accordance with this policy.
              </p>
            </div>

            {/* Information We Collect */}
            <div>
              <h2 className="text-2xl text-[var(--color-primary)] mb-4" style={{ fontFamily: "Georgia, serif" }}>
                Information We Collect
              </h2>
              <h3 className="text-lg text-[var(--color-primary)] font-medium mb-2">
                Information You Provide
              </h3>
              <ul className="list-disc pl-6 space-y-2 mb-6">
                <li>
                  <strong>Contact information:</strong> name, email address, phone
                  number, and mailing address when you submit a contact form, request
                  a showing, or create an account.
                </li>
                <li>
                  <strong>Property preferences:</strong> search criteria, saved
                  properties, and property inquiries.
                </li>
                <li>
                  <strong>Transaction information:</strong> details related to real
                  estate transactions you conduct through our services, including
                  property addresses, financial terms, and closing documents.
                </li>
                <li>
                  <strong>Communications:</strong> messages you send to us through
                  email, contact forms, or other channels.
                </li>
              </ul>

              <h3 className="text-lg text-[var(--color-primary)] font-medium mb-2">
                Information Collected Automatically
              </h3>
              <ul className="list-disc pl-6 space-y-2">
                <li>
                  <strong>Usage data:</strong> pages visited, search queries, time
                  spent on pages, and referring URLs.
                </li>
                <li>
                  <strong>Device information:</strong> browser type, operating system,
                  IP address, and device identifiers.
                </li>
                <li>
                  <strong>Cookies and similar technologies:</strong> we use cookies to
                  maintain session state, remember your preferences, and improve your
                  experience.
                </li>
              </ul>
            </div>

            {/* How We Use Your Information */}
            <div>
              <h2 className="text-2xl text-[var(--color-primary)] mb-4" style={{ fontFamily: "Georgia, serif" }}>
                How We Use Your Information
              </h2>
              <p className="mb-4">We use the information we collect to:</p>
              <ul className="list-disc pl-6 space-y-2">
                <li>Provide property listings, search results, and real estate services.</li>
                <li>Respond to your inquiries and communicate with you about properties and services.</li>
                <li>Facilitate real estate transactions, including document preparation and management.</li>
                <li>Personalize your experience, such as saving your favorite properties and search preferences.</li>
                <li>Send you updates about properties matching your criteria, market reports, and service notifications (with your consent).</li>
                <li>Improve our Site, services, and user experience.</li>
                <li>Comply with legal obligations and protect our rights.</li>
              </ul>
            </div>

            {/* Third-Party Services */}
            <div>
              <h2 className="text-2xl text-[var(--color-primary)] mb-4" style={{ fontFamily: "Georgia, serif" }}>
                Third-Party Services and Integrations
              </h2>
              <p className="mb-4">
                We use third-party services to operate our business and provide you
                with a better experience. These services may receive or process your
                information as described below:
              </p>
              <ul className="list-disc pl-6 space-y-2">
                <li>
                  <strong>Dotloop (Zillow Group):</strong> We use Dotloop for
                  transaction management, including document storage, e-signatures,
                  and transaction coordination. When you enter a real estate
                  transaction with us, your name, contact information, and
                  transaction-related details may be shared with Dotloop to
                  facilitate the process. Dotloop&apos;s use of your data is governed by
                  their own privacy policy.
                </li>
                <li>
                  <strong>MLS Data Providers:</strong> We receive property listing
                  data from Multiple Listing Services (MLS), including Carolina
                  Smokies Association of REALTORS. We display this data in accordance
                  with MLS rules and IDX guidelines.
                </li>
                <li>
                  <strong>Follow Up Boss:</strong> We use a customer relationship
                  management (CRM) system to manage client communications and track
                  your property interests so we can serve you more effectively.
                </li>
                <li>
                  <strong>Google Services:</strong> We may use Google Analytics to
                  understand how visitors use our Site, and Google Calendar for
                  scheduling appointments.
                </li>
              </ul>
            </div>

            {/* Data Sharing */}
            <div>
              <h2 className="text-2xl text-[var(--color-primary)] mb-4" style={{ fontFamily: "Georgia, serif" }}>
                How We Share Your Information
              </h2>
              <p className="mb-4">
                We do not sell your personal information to third parties. We may share
                your information in the following circumstances:
              </p>
              <ul className="list-disc pl-6 space-y-2">
                <li>
                  <strong>Service providers:</strong> with third-party companies that
                  help us operate our business (transaction management, CRM, hosting,
                  analytics) under appropriate data protection agreements.
                </li>
                <li>
                  <strong>Transaction parties:</strong> with other parties involved in
                  a real estate transaction (buyers, sellers, agents, title companies,
                  lenders) as necessary to complete the transaction.
                </li>
                <li>
                  <strong>Legal requirements:</strong> when required by law, court
                  order, or governmental authority, or to protect our rights and safety.
                </li>
              </ul>
            </div>

            {/* Data Security */}
            <div>
              <h2 className="text-2xl text-[var(--color-primary)] mb-4" style={{ fontFamily: "Georgia, serif" }}>
                Data Security
              </h2>
              <p>
                We take reasonable measures to protect your personal information from
                unauthorized access, alteration, disclosure, or destruction. These
                measures include encryption of data in transit (HTTPS), secure server
                infrastructure, and access controls limiting who can view your
                information. However, no method of transmission over the internet or
                electronic storage is 100% secure, and we cannot guarantee absolute
                security.
              </p>
            </div>

            {/* Data Retention */}
            <div>
              <h2 className="text-2xl text-[var(--color-primary)] mb-4" style={{ fontFamily: "Georgia, serif" }}>
                Data Retention
              </h2>
              <p>
                We retain your personal information for as long as necessary to provide
                our services, comply with legal obligations, resolve disputes, and
                enforce our agreements. If you request deletion of your account or
                personal information, we will process your request within a reasonable
                timeframe, subject to any legal retention requirements.
              </p>
            </div>

            {/* Your Rights */}
            <div>
              <h2 className="text-2xl text-[var(--color-primary)] mb-4" style={{ fontFamily: "Georgia, serif" }}>
                Your Rights
              </h2>
              <p className="mb-4">You have the right to:</p>
              <ul className="list-disc pl-6 space-y-2">
                <li>
                  <strong>Access:</strong> request a copy of the personal information
                  we hold about you.
                </li>
                <li>
                  <strong>Correction:</strong> request that we correct inaccurate or
                  incomplete information.
                </li>
                <li>
                  <strong>Deletion:</strong> request that we delete your personal
                  information, subject to legal retention requirements.
                </li>
                <li>
                  <strong>Opt out:</strong> unsubscribe from marketing communications
                  at any time by using the unsubscribe link in our emails or
                  contacting us directly.
                </li>
                <li>
                  <strong>Revoke third-party access:</strong> request that we
                  disconnect your data from third-party services such as Dotloop.
                </li>
              </ul>
            </div>

            {/* Cookies */}
            <div>
              <h2 className="text-2xl text-[var(--color-primary)] mb-4" style={{ fontFamily: "Georgia, serif" }}>
                Cookies
              </h2>
              <p>
                Our Site uses cookies and similar technologies to maintain your
                session, remember your preferences, and analyze usage patterns. You can
                control cookie settings through your browser preferences. Disabling
                cookies may limit certain features of the Site, such as saved searches
                and account functionality.
              </p>
            </div>

            {/* Children */}
            <div>
              <h2 className="text-2xl text-[var(--color-primary)] mb-4" style={{ fontFamily: "Georgia, serif" }}>
                Children&apos;s Privacy
              </h2>
              <p>
                Our services are not directed to individuals under the age of 18. We
                do not knowingly collect personal information from children. If you
                believe we have collected information from a child, please contact us
                and we will take steps to delete it.
              </p>
            </div>

            {/* Changes */}
            <div>
              <h2 className="text-2xl text-[var(--color-primary)] mb-4" style={{ fontFamily: "Georgia, serif" }}>
                Changes to This Policy
              </h2>
              <p>
                We may update this Privacy Policy from time to time. Changes will be
                posted on this page with an updated effective date. We encourage you to
                review this policy periodically. Your continued use of the Site after
                changes are posted constitutes acceptance of the updated policy.
              </p>
            </div>

            {/* Contact */}
            <div>
              <h2 className="text-2xl text-[var(--color-primary)] mb-4" style={{ fontFamily: "Georgia, serif" }}>
                Contact Us
              </h2>
              <p className="mb-4">
                If you have questions about this Privacy Policy or wish to exercise
                your rights regarding your personal information, please contact us:
              </p>
              <div className="bg-white border border-gray-200/60 p-6">
                <p className="font-medium text-[var(--color-primary)]">WNC Mountain Homes LLC</p>
                <p className="mt-2">Franklin, NC</p>
                <p>
                  Phone:{" "}
                  <a href="tel:8282839003" className="text-[var(--color-primary)] hover:underline">
                    (828) 283-9003
                  </a>
                </p>
                <p>
                  Website:{" "}
                  <a href="https://wncmountain.homes" className="text-[var(--color-primary)] hover:underline">
                    wncmountain.homes
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
            If you have any concerns about how we handle your data, we are happy to discuss them.
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
