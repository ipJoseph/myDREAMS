"use client";

import { useCallback, useEffect, useState } from "react";
import Image from "next/image";

interface PhotoBrowserProps {
  photos: string[];
  address: string;
  city: string;
}

export default function PhotoBrowser({ photos, address, city }: PhotoBrowserProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [current, setCurrent] = useState(0);

  const open = useCallback((index: number = 0) => {
    setCurrent(index);
    setIsOpen(true);
  }, []);

  const close = useCallback(() => {
    setIsOpen(false);
  }, []);

  const prev = useCallback(() => {
    setCurrent((c) => (c > 0 ? c - 1 : photos.length - 1));
  }, [photos.length]);

  const next = useCallback(() => {
    setCurrent((c) => (c < photos.length - 1 ? c + 1 : 0));
  }, [photos.length]);

  // Keyboard navigation
  useEffect(() => {
    if (!isOpen) return;

    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        prev();
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        next();
      } else if (e.key === "Escape") {
        e.preventDefault();
        close();
      }
    };

    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", handleKey);
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", handleKey);
    };
  }, [isOpen, prev, next, close]);

  if (photos.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-white/30">
        <svg className="w-16 h-16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0h4" />
        </svg>
      </div>
    );
  }

  return (
    <>
      {/* Photo grid */}
      <div className="max-w-7xl mx-auto">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-1 max-h-[500px] overflow-hidden">
          {/* Main photo */}
          <button
            onClick={() => open(0)}
            className="aspect-[4/3] md:aspect-auto md:row-span-2 relative cursor-pointer group"
          >
            <Image
              src={photos[0]}
              alt={`${address}, ${city}`}
              fill
              sizes="(max-width: 768px) 100vw, 50vw"
              className="object-cover group-hover:brightness-90 transition-all duration-300"
              priority
            />
          </button>

          {/* Secondary photos */}
          <div className="hidden md:grid grid-cols-2 gap-1">
            {photos.slice(1, 5).map((photo, i) => (
              <button
                key={i}
                onClick={() => open(i + 1)}
                className="aspect-[4/3] relative cursor-pointer group"
              >
                <Image
                  src={photo}
                  alt={`Photo ${i + 2}`}
                  fill
                  sizes="25vw"
                  className="object-cover group-hover:brightness-90 transition-all duration-300"
                  loading="lazy"
                />
                {/* "All Photos" button on the last visible thumbnail */}
                {i === 3 && photos.length > 5 && (
                  <div className="absolute inset-0 bg-black/50 flex items-center justify-center group-hover:bg-black/60 transition">
                    <span
                      className="bg-white/85 text-[var(--color-primary)] text-sm font-semibold px-5 py-2.5 uppercase tracking-wider backdrop-blur-sm"
                      style={{ boxShadow: "0 4px 12px rgba(0,0,0,0.3), 0 1px 3px rgba(0,0,0,0.2), inset 0 1px 0 rgba(255,255,255,0.4)" }}
                    >
                      All {photos.length} Photos
                    </span>
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Mobile "All Photos" button */}
        {photos.length > 1 && (
          <button
            onClick={() => open(0)}
            className="md:hidden w-full py-3 bg-white/10 text-white text-sm uppercase tracking-wider hover:bg-white/20 transition"
          >
            View All {photos.length} Photos
          </button>
        )}
      </div>

      {/* Lightbox modal */}
      {isOpen && (
        <div
          className="fixed inset-0 z-[100] bg-black/95 flex flex-col"
          onClick={(e) => {
            if (e.target === e.currentTarget) close();
          }}
        >
          {/* Top bar */}
          <div className="flex items-center justify-between px-6 py-4 text-white">
            <span className="text-sm text-white/60">
              {current + 1} of {photos.length}
            </span>
            <span className="text-sm text-white/40 hidden sm:block">
              {address}, {city}
            </span>
            <button
              onClick={close}
              className="w-10 h-10 flex items-center justify-center text-white/60 hover:text-white transition"
              aria-label="Close"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Photo area */}
          <div className="flex-1 flex items-center justify-center relative px-4 min-h-0">
            {/* Previous button */}
            <button
              onClick={prev}
              className="absolute left-4 z-10 w-12 h-12 flex items-center justify-center bg-white/10 hover:bg-white/20 text-white transition"
              aria-label="Previous photo"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </button>

            {/* Current photo */}
            <div className="relative w-full h-full max-w-5xl mx-16">
              <Image
                key={current}
                src={photos[current]}
                alt={`Photo ${current + 1} of ${photos.length}`}
                fill
                sizes="90vw"
                className="object-contain"
                priority
              />
            </div>

            {/* Next button */}
            <button
              onClick={next}
              className="absolute right-4 z-10 w-12 h-12 flex items-center justify-center bg-white/10 hover:bg-white/20 text-white transition"
              aria-label="Next photo"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </button>
          </div>

          {/* Thumbnail strip */}
          {photos.length > 1 && (
            <div className="px-6 py-4 overflow-x-auto">
              <div className="flex gap-2 justify-center">
                {photos.map((photo, i) => (
                  <button
                    key={i}
                    onClick={() => setCurrent(i)}
                    className={`relative w-16 h-12 flex-shrink-0 overflow-hidden transition ${
                      i === current
                        ? "ring-2 ring-[var(--color-accent)]"
                        : "opacity-40 hover:opacity-70"
                    }`}
                  >
                    <Image
                      src={photo}
                      alt={`Thumbnail ${i + 1}`}
                      fill
                      sizes="64px"
                      className="object-cover"
                    />
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </>
  );
}
