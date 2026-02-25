import type { Metadata } from "next";
import Link from "next/link";
import SessionWrapper from "@/components/SessionWrapper";
import UserMenu from "@/components/UserMenu";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "WNC Mountain Homes | Western NC Real Estate",
    template: "%s | WNC Mountain Homes",
  },
  description:
    "Search homes, land, and investment properties for sale in Western North Carolina. Franklin, Waynesville, Sylva, Bryson City, and the Great Smoky Mountains.",
  keywords: [
    "Western NC real estate",
    "homes for sale WNC",
    "Franklin NC homes",
    "Waynesville NC real estate",
    "Smoky Mountain homes",
    "mountain homes for sale",
    "WNC Mountain Homes",
    "Western NC mountain real estate",
  ],
};

function Header() {
  return (
    <header className="absolute top-0 left-0 right-0 z-50">
      <nav className="max-w-7xl mx-auto px-6 lg:px-8">
        <div className="flex items-center justify-between h-20">
          <Link href="/" className="text-white">
            <span className="text-2xl font-bold tracking-tight" style={{ fontFamily: "Georgia, serif" }}>
              WNC Mountain Homes
            </span>
          </Link>
          {/* Desktop nav */}
          <div className="hidden md:flex items-center gap-8 text-sm tracking-wide uppercase">
            <Link href="/listings" className="text-white/80 hover:text-[var(--color-accent)] transition">
              Properties
            </Link>
            <Link href="/areas" className="text-white/80 hover:text-[var(--color-accent)] transition">
              Areas
            </Link>
            <Link href="/about" className="text-white/80 hover:text-[var(--color-accent)] transition">
              About
            </Link>
            <Link
              href="/contact"
              className="text-[var(--color-accent)] border border-[var(--color-accent)] px-5 py-2 hover:bg-[var(--color-accent)] hover:text-[var(--color-primary)] transition"
            >
              Contact
            </Link>
            <UserMenu />
          </div>
          {/* Mobile nav */}
          <details className="md:hidden relative">
            <summary className="list-none cursor-pointer p-2 text-white">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </summary>
            <div className="absolute right-0 top-full mt-2 w-60 bg-[var(--color-primary)] border border-white/10 shadow-2xl py-2 z-50">
              <Link href="/listings" className="block px-6 py-3 text-white/80 hover:text-[var(--color-accent)] text-sm uppercase tracking-wide">
                Properties
              </Link>
              <Link href="/areas" className="block px-6 py-3 text-white/80 hover:text-[var(--color-accent)] text-sm uppercase tracking-wide">
                Areas
              </Link>
              <Link href="/about" className="block px-6 py-3 text-white/80 hover:text-[var(--color-accent)] text-sm uppercase tracking-wide">
                About
              </Link>
              <Link href="/contact" className="block px-6 py-3 text-[var(--color-accent)] text-sm uppercase tracking-wide">
                Contact
              </Link>
              <Link href="/account/favorites" className="block px-6 py-3 text-white/80 hover:text-[var(--color-accent)] text-sm uppercase tracking-wide border-t border-white/10">
                My Account
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
    <footer className="bg-[var(--color-primary)] text-white/70">
      <div className="max-w-7xl mx-auto px-6 lg:px-8 py-16">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-10">
          {/* Brand */}
          <div className="md:col-span-1">
            <h3 className="text-white text-xl mb-4" style={{ fontFamily: "Georgia, serif" }}>
              WNC Mountain Homes
            </h3>
            <p className="text-sm leading-relaxed">
              Western North Carolina Real Estate
              <br />
              Franklin, NC
            </p>
          </div>

          {/* Contact */}
          <div>
            <h4 className="text-[var(--color-accent)] text-xs uppercase tracking-widest mb-4">
              Contact
            </h4>
            <ul className="space-y-2 text-sm">
              <li>
                <a href="tel:8282839003" className="hover:text-white transition">
                  (828) 283-9003
                </a>
              </li>
              <li>
                <a href="https://wncmountain.homes" className="hover:text-white transition">
                  wncmountain.homes
                </a>
              </li>
            </ul>
          </div>

          {/* Quick Links */}
          <div>
            <h4 className="text-[var(--color-accent)] text-xs uppercase tracking-widest mb-4">
              Explore
            </h4>
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

          {/* Social + MLS */}
          <div>
            <h4 className="text-[var(--color-accent)] text-xs uppercase tracking-widest mb-4">
              Follow Us
            </h4>
            <div className="flex gap-4 mb-6">
              <a href="https://facebook.com/wncmountainhomes" target="_blank" rel="noopener noreferrer"
                className="w-9 h-9 border border-white/20 flex items-center justify-center hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] transition">
                <span className="text-xs font-bold">f</span>
              </a>
              <a href="https://instagram.com/wncmountainhomes" target="_blank" rel="noopener noreferrer"
                className="w-9 h-9 border border-white/20 flex items-center justify-center hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] transition">
                <span className="text-xs font-bold">ig</span>
              </a>
              <a href="https://youtube.com/@wncmountainhomes" target="_blank" rel="noopener noreferrer"
                className="w-9 h-9 border border-white/20 flex items-center justify-center hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] transition">
                <span className="text-xs font-bold">yt</span>
              </a>
            </div>
            <p className="text-xs leading-relaxed">
              Listing data provided by Carolina Smokies Association of REALTORS.
              All information deemed reliable but not guaranteed.
            </p>
          </div>
        </div>

        <div className="border-t border-white/10 mt-12 pt-8 flex flex-col md:flex-row items-center justify-between text-xs">
          <span>&copy; {new Date().getFullYear()} WNC Mountain Homes. All rights reserved.</span>
          <span className="mt-2 md:mt-0 uppercase tracking-widest text-white/40">
            Residential &middot; Land &middot; Investment &middot; Commercial
          </span>
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
      <body className="antialiased min-h-screen flex flex-col">
        <SessionWrapper>
          <Header />
          <main className="flex-1">{children}</main>
          <Footer />
        </SessionWrapper>
      </body>
    </html>
  );
}
