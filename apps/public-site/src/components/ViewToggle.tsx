"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";

export default function ViewToggle() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const currentView = searchParams.get("view") || "grid";

  const setView = useCallback(
    (view: string) => {
      const params = new URLSearchParams(searchParams.toString());
      if (view === "grid") {
        params.delete("view");
      } else {
        params.set("view", view);
      }
      params.delete("page");
      router.push(`/listings?${params.toString()}`);
    },
    [router, searchParams]
  );

  return (
    <div className="flex border border-white/20 rounded overflow-hidden">
      <button
        onClick={() => setView("grid")}
        className={`px-3 py-2 text-xs font-medium uppercase tracking-wider transition ${
          currentView === "grid"
            ? "bg-[var(--color-accent)] text-[var(--color-primary)]"
            : "bg-white/10 text-white/70 hover:text-white"
        }`}
        title="Grid view"
      >
        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
          <path d="M5 3a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2V5a2 2 0 00-2-2H5zM5 11a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2v-2a2 2 0 00-2-2H5zM11 5a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V5zM11 13a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
        </svg>
      </button>
      <button
        onClick={() => setView("map")}
        className={`px-3 py-2 text-xs font-medium uppercase tracking-wider transition ${
          currentView === "map"
            ? "bg-[var(--color-accent)] text-[var(--color-primary)]"
            : "bg-white/10 text-white/70 hover:text-white"
        }`}
        title="Map view"
      >
        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
          <path fillRule="evenodd" d="M12 1.586l-4 4v12.828l4-4V1.586zM3.707 3.293A1 1 0 002 4v10a1 1 0 00.293.707L6 18.414V5.586L3.707 3.293zM17.707 5.293L14 1.586v12.828l2.293 2.293A1 1 0 0018 16V6a1 1 0 00-.293-.707z" clipRule="evenodd" />
        </svg>
      </button>
    </div>
  );
}
