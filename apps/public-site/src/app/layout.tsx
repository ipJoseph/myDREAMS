import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: {
    default: "WNC Mountain Homes | Western NC Real Estate",
    template: "%s | WNC Mountain Homes",
  },
  description:
    "Search homes for sale in Western North Carolina. Franklin, Waynesville, Sylva, Bryson City, and the Great Smoky Mountains.",
  keywords: [
    "Western NC real estate",
    "homes for sale WNC",
    "Franklin NC homes",
    "Waynesville NC real estate",
    "Smoky Mountain homes",
    "mountain homes for sale",
  ],
};

function Header() {
  return (
    <header className="bg-[var(--color-primary)] text-white border-b border-white/10">
      <nav className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <Link href="/" className="text-xl font-bold tracking-tight">
            WNC Mountain Homes
          </Link>
          {/* Desktop nav */}
          <div className="hidden md:flex items-center gap-6 text-sm">
            <Link href="/listings" className="hover:text-gray-200 transition">
              Search Properties
            </Link>
            <Link href="/areas" className="hover:text-gray-200 transition">
              Areas We Serve
            </Link>
            <Link href="/about" className="hover:text-gray-200 transition">
              About
            </Link>
            <Link
              href="/contact"
              className="bg-white text-[var(--color-primary)] px-4 py-2 rounded-md font-medium hover:bg-gray-100 transition"
            >
              Contact Us
            </Link>
          </div>
          {/* Mobile nav toggle (CSS-only using details/summary) */}
          <details className="md:hidden relative">
            <summary className="list-none cursor-pointer p-2">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </summary>
            <div className="absolute right-0 top-full mt-2 w-56 bg-white rounded-lg shadow-lg py-2 z-50">
              <Link href="/listings" className="block px-4 py-3 text-gray-700 hover:bg-gray-50">
                Search Properties
              </Link>
              <Link href="/areas" className="block px-4 py-3 text-gray-700 hover:bg-gray-50">
                Areas We Serve
              </Link>
              <Link href="/about" className="block px-4 py-3 text-gray-700 hover:bg-gray-50">
                About
              </Link>
              <Link href="/contact" className="block px-4 py-3 text-[var(--color-primary)] font-medium hover:bg-gray-50">
                Contact Us
              </Link>
            </div>
          </details>
        </div>
      </nav>
    </header>
  );
}

function Footer() {
  return (
    <footer className="bg-gray-900 text-gray-400 mt-auto">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          <div>
            <h3 className="text-white font-semibold mb-3">
              WNC Mountain Homes
            </h3>
            <p className="text-sm">
              Jon Tharp Homes | Keller Williams
              <br />
              Serving Western North Carolina
            </p>
          </div>
          <div>
            <h3 className="text-white font-semibold mb-3">Quick Links</h3>
            <ul className="space-y-2 text-sm">
              <li>
                <Link href="/listings" className="hover:text-white transition">
                  Search Properties
                </Link>
              </li>
              <li>
                <Link href="/areas" className="hover:text-white transition">
                  Areas We Serve
                </Link>
              </li>
              <li>
                <Link href="/about" className="hover:text-white transition">
                  About Us
                </Link>
              </li>
              <li>
                <Link href="/contact" className="hover:text-white transition">
                  Contact
                </Link>
              </li>
            </ul>
          </div>
          <div>
            <h3 className="text-white font-semibold mb-3">MLS Disclosure</h3>
            <p className="text-xs leading-relaxed">
              Listing data provided by Carolina Smokies Association of REALTORS.
              All information deemed reliable but not guaranteed.
              Data refreshed regularly throughout the day.
            </p>
          </div>
        </div>
        <div className="border-t border-gray-800 mt-8 pt-8 text-xs text-center">
          &copy; {new Date().getFullYear()} Jon Tharp Homes | Keller Williams.
          All rights reserved.
        </div>
      </div>
    </footer>
  );
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased min-h-screen flex flex-col`}
      >
        <Header />
        <main className="flex-1">{children}</main>
        <Footer />
      </body>
    </html>
  );
}
