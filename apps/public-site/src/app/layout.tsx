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
    <header className="bg-[var(--color-primary)] text-white">
      <nav className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <Link href="/" className="text-xl font-bold tracking-tight">
            WNC Mountain Homes
          </Link>
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
              Listing data provided by Carolina Smokies Association of REALTORS
              and Canopy MLS. All information deemed reliable but not guaranteed.
              Last updated data refresh occurs regularly throughout the day.
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
