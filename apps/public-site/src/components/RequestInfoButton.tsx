"use client";

import { useState, type FormEvent } from "react";
import { submitContactForm } from "@/lib/api";
import { setTrackingEmail } from "@/lib/track";

interface RequestInfoButtonProps {
  listingId: string;
  address: string;
  mlsNumber?: string;
}

/**
 * "Request Info" button + modal for listing detail pages.
 *
 * This is Tier A lead capture: name, email, phone, message. No password.
 * Creates a lead in dreams.db and pushes to FUB as a "Property Inquiry"
 * event. The person doesn't get a login — they're a lead, not a user.
 *
 * If they later register (Tier B), their email matches and the lead
 * record links to their user account automatically.
 */
export default function RequestInfoButton({
  listingId,
  address,
  mlsNumber,
}: RequestInfoButtonProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [status, setStatus] = useState<"idle" | "submitting" | "success" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState("");

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setStatus("submitting");
    setErrorMsg("");

    const form = e.currentTarget;
    const formData = new FormData(form);

    const result = await submitContactForm({
      name: (formData.get("name") as string) || "",
      email: (formData.get("email") as string) || "",
      phone: (formData.get("phone") as string) || undefined,
      message: (formData.get("message") as string) || undefined,
      listing_id: listingId,
      source: "request_info",
    });

    if (result.ok) {
      setStatus("success");
      const email = (formData.get("email") as string) || "";
      if (email) setTrackingEmail(email);
      form.reset();
    } else {
      setStatus("error");
      setErrorMsg(result.error || "Something went wrong. Please try again.");
    }
  }

  return (
    <>
      <button
        onClick={() => { setIsOpen(true); setStatus("idle"); }}
        className="w-full py-3 bg-[var(--color-accent)] text-[var(--color-primary)] font-semibold text-sm uppercase tracking-wider hover:bg-[var(--color-accent-hover)] transition"
      >
        Request Info
      </button>

      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/60" onClick={() => setIsOpen(false)} />
          <div className="relative bg-white w-full max-w-md mx-4 shadow-2xl">
            <button
              onClick={() => setIsOpen(false)}
              className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 transition"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>

            <div className="p-8">
              {status === "success" ? (
                <div className="text-center py-6">
                  <div className="w-14 h-14 mx-auto mb-4 bg-green-100 rounded-full flex items-center justify-center">
                    <svg className="w-7 h-7 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                  <h3 className="text-xl text-[var(--color-primary)] mb-2" style={{ fontFamily: "Georgia, serif" }}>
                    Request Received
                  </h3>
                  <p className="text-sm text-gray-500 leading-relaxed">
                    We will send you information about this property within one business day.
                  </p>
                  <button
                    onClick={() => setIsOpen(false)}
                    className="mt-5 text-sm text-[var(--color-accent)] uppercase tracking-wider"
                  >
                    Close
                  </button>
                </div>
              ) : (
                <>
                  <h2
                    className="text-xl text-[var(--color-primary)] mb-1"
                    style={{ fontFamily: "Georgia, serif" }}
                  >
                    Request Information
                  </h2>
                  <p className="text-sm text-gray-500 mb-5">
                    {address}{mlsNumber ? ` (MLS# ${mlsNumber})` : ""}
                  </p>

                  {status === "error" && (
                    <div className="bg-red-50 border border-red-200 text-red-700 text-sm p-3 mb-4">
                      {errorMsg}
                    </div>
                  )}

                  <form onSubmit={handleSubmit} className="space-y-4">
                    <div>
                      <label className="block text-xs text-gray-500 uppercase tracking-wider mb-1">
                        Name *
                      </label>
                      <input
                        type="text"
                        name="name"
                        required
                        disabled={status === "submitting"}
                        className="w-full px-4 py-3 border border-gray-200 text-sm focus:outline-none focus:border-[var(--color-accent)] transition disabled:opacity-50"
                        placeholder="Your name"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-500 uppercase tracking-wider mb-1">
                        Email *
                      </label>
                      <input
                        type="email"
                        name="email"
                        required
                        disabled={status === "submitting"}
                        className="w-full px-4 py-3 border border-gray-200 text-sm focus:outline-none focus:border-[var(--color-accent)] transition disabled:opacity-50"
                        placeholder="you@example.com"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-500 uppercase tracking-wider mb-1">
                        Phone <span className="normal-case text-gray-400 tracking-normal">(optional, helps us reach you faster)</span>
                      </label>
                      <input
                        type="tel"
                        name="phone"
                        disabled={status === "submitting"}
                        className="w-full px-4 py-3 border border-gray-200 text-sm focus:outline-none focus:border-[var(--color-accent)] transition disabled:opacity-50"
                        placeholder="(828) 555-1234"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-500 uppercase tracking-wider mb-1">
                        Message
                      </label>
                      <textarea
                        name="message"
                        rows={3}
                        disabled={status === "submitting"}
                        defaultValue={`I'd like more information about ${address}.`}
                        className="w-full px-4 py-3 border border-gray-200 text-sm focus:outline-none focus:border-[var(--color-accent)] transition disabled:opacity-50"
                      />
                    </div>
                    <button
                      type="submit"
                      disabled={status === "submitting"}
                      className="w-full py-3 bg-[var(--color-accent)] text-[var(--color-primary)] font-semibold text-sm uppercase tracking-wider hover:bg-[var(--color-accent-hover)] transition disabled:opacity-50"
                    >
                      {status === "submitting" ? "Sending..." : "Send Request"}
                    </button>
                    <p className="text-xs text-gray-400 text-center">
                      No account needed. Your info is never shared.
                    </p>
                  </form>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
