"use client";

import { useState, type FormEvent } from "react";
import { submitContactForm } from "@/lib/api";
import { setTrackingEmail } from "@/lib/track";

interface ContactFormProps {
  listingRef?: string;
  addressRef?: string;
}

const SMS_CONSENT_TEXT =
  "I agree to receive SMS text messages from WNC Mountain Homes LLC about property listings, showing requests, market updates, and account-related notifications. Message frequency varies. Message and data rates may apply. Reply HELP for help, STOP to unsubscribe.";

export default function ContactForm({ listingRef, addressRef }: ContactFormProps) {
  const [status, setStatus] = useState<"idle" | "submitting" | "success" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const [smsConsent, setSmsConsent] = useState(false);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setStatus("submitting");
    setErrorMsg("");

    const form = e.currentTarget;
    const formData = new FormData(form);
    const phoneValue = ((formData.get("phone") as string) || "").trim();

    const result = await submitContactForm({
      name: (formData.get("name") as string) || "",
      email: (formData.get("email") as string) || "",
      phone: phoneValue || undefined,
      message: (formData.get("message") as string) || undefined,
      listing_id: listingRef || undefined,
      source: listingRef ? "request_info" : "contact_form",
      sms_consent: phoneValue ? smsConsent : false,
      sms_consent_text: phoneValue && smsConsent ? SMS_CONSENT_TEXT : undefined,
    });

    if (result.ok) {
      setStatus("success");
      // Store email so future page views in this session are tracked
      const submittedEmail = (formData.get("email") as string) || "";
      if (submittedEmail) setTrackingEmail(submittedEmail);
      form.reset();
      setSmsConsent(false);
    } else {
      setStatus("error");
      setErrorMsg(result.error || "Something went wrong. Please try again.");
    }
  }

  if (status === "success") {
    return (
      <div className="bg-white border border-gray-200/60 p-8">
        <div className="text-center py-8">
          <div className="w-16 h-16 mx-auto mb-4 bg-green-100 rounded-full flex items-center justify-center">
            <svg className="w-8 h-8 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <h3 className="text-xl text-[var(--color-primary)] mb-2" style={{ fontFamily: "Georgia, serif" }}>
            Message Received
          </h3>
          <p className="text-sm text-[var(--color-text-light)] leading-relaxed max-w-sm mx-auto">
            Thank you for reaching out. We will get back to you within one business day.
          </p>
          <button
            onClick={() => setStatus("idle")}
            className="mt-6 text-sm text-[var(--color-accent)] uppercase tracking-wider border-b border-[var(--color-accent)]/30 pb-1 hover:border-[var(--color-accent)] transition"
          >
            Send Another Message
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white border border-gray-200/60 p-8">
      <form onSubmit={handleSubmit} className="space-y-5">
        {listingRef && (
          <div className="bg-[var(--color-primary)]/5 border border-[var(--color-primary)]/10 p-4 mb-2">
            <p className="text-xs text-[var(--color-text-light)] uppercase tracking-wider">Inquiring about</p>
            <p className="text-sm text-[var(--color-primary)] font-medium mt-1">
              {addressRef || `MLS# ${listingRef}`}
            </p>
          </div>
        )}

        {status === "error" && (
          <div className="bg-red-50 border border-red-200 text-red-700 text-sm p-4">
            {errorMsg}
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
            disabled={status === "submitting"}
            className="w-full px-4 py-3 border border-gray-200/60 bg-[var(--color-eggshell)] text-[var(--color-text)] text-sm focus:outline-none focus:border-[var(--color-accent)] transition disabled:opacity-50"
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
            disabled={status === "submitting"}
            className="w-full px-4 py-3 border border-gray-200/60 bg-[var(--color-eggshell)] text-[var(--color-text)] text-sm focus:outline-none focus:border-[var(--color-accent)] transition disabled:opacity-50"
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
            disabled={status === "submitting"}
            className="w-full px-4 py-3 border border-gray-200/60 bg-[var(--color-eggshell)] text-[var(--color-text)] text-sm focus:outline-none focus:border-[var(--color-accent)] transition disabled:opacity-50"
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
            disabled={status === "submitting"}
            defaultValue={
              listingRef
                ? `I'm interested in the property at ${addressRef || ""} (MLS# ${listingRef}). Please send me more information.`
                : ""
            }
            className="w-full px-4 py-3 border border-gray-200/60 bg-[var(--color-eggshell)] text-[var(--color-text)] text-sm focus:outline-none focus:border-[var(--color-accent)] transition disabled:opacity-50"
          />
        </div>

        {/* A2P 10DLC: SMS consent must be express, with the 6 disclosure elements visible at point of capture. */}
        <label className="flex items-start gap-3 text-xs text-[var(--color-text-light)] leading-relaxed cursor-pointer">
          <input
            type="checkbox"
            name="sms_consent"
            checked={smsConsent}
            onChange={(e) => setSmsConsent(e.target.checked)}
            disabled={status === "submitting"}
            className="mt-0.5 flex-shrink-0"
          />
          <span>
            I agree to receive SMS text messages from <strong>WNC Mountain Homes LLC</strong> at the
            phone number provided about property listings, showing requests, market updates, and
            account-related notifications. Message frequency varies. Message and data rates may
            apply. Reply HELP for help, STOP to unsubscribe. See our{" "}
            <a href="/privacy" className="underline hover:text-[var(--color-accent)]">Privacy Policy</a>{" "}
            and{" "}
            <a href="/terms" className="underline hover:text-[var(--color-accent)]">Terms of Service</a>.
            Consent is not a condition of any purchase.
          </span>
        </label>

        <p className="text-xs text-[var(--color-text-light)] leading-relaxed">
          Your information is kept private. We do not share, sell, or rent your mobile number or
          consent to any third party or affiliate for their marketing or promotional purposes.
        </p>

        <button
          type="submit"
          disabled={status === "submitting"}
          className="w-full py-4 bg-[var(--color-accent)] text-[var(--color-primary)] font-semibold text-sm uppercase tracking-wider hover:bg-[var(--color-accent-hover)] transition disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {status === "submitting" ? "Sending..." : "Send Message"}
        </button>
      </form>
    </div>
  );
}
