"use client";

import { useState, useEffect } from "react";
import { useSession } from "next-auth/react";
import AuthModal from "./AuthModal";

interface Collection {
  id: string;
  name: string;
  property_count: number;
}

interface AddToCollectionButtonProps {
  listingId: string;
  variant?: "icon" | "button";
}

export default function AddToCollectionButton({
  listingId,
  variant = "icon",
}: AddToCollectionButtonProps) {
  const { data: session } = useSession();
  const [showDropdown, setShowDropdown] = useState(false);
  const [showAuth, setShowAuth] = useState(false);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [loading, setLoading] = useState(false);
  const [added, setAdded] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    if (showDropdown && session) {
      fetchCollections();
    }
  }, [showDropdown, session]);

  async function fetchCollections() {
    setLoading(true);
    try {
      const res = await fetch("/api/user/collections");
      if (res.ok) {
        const data = await res.json();
        if (data.success) setCollections(data.data);
      }
    } catch {
      // Silently fail
    } finally {
      setLoading(false);
    }
  }

  const handleClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!session) {
      setShowAuth(true);
      return;
    }
    setShowDropdown(!showDropdown);
  };

  const addToCollection = async (collectionId: string) => {
    try {
      const res = await fetch(`/api/user/collections/${collectionId}/items`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ listing_id: listingId }),
      });
      if (res.ok) {
        setAdded(collectionId);
        setTimeout(() => {
          setAdded(null);
          setShowDropdown(false);
        }, 1000);
      }
    } catch {
      // Silently fail
    }
  };

  const createAndAdd = async () => {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      const res = await fetch("/api/user/collections", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newName.trim() }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.success) {
          await addToCollection(data.data.id);
          setNewName("");
          await fetchCollections();
        }
      }
    } catch {
      // Silently fail
    } finally {
      setCreating(false);
    }
  };

  return (
    <>
      <div className="relative">
        {variant === "icon" ? (
          <button
            onClick={handleClick}
            className="p-2 bg-black/40 hover:bg-black/60 text-white transition rounded-full"
            title="Add to collection"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M12 9v3m0 0v3m0-3h3m-3 0H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </button>
        ) : (
          <button
            onClick={handleClick}
            className="flex items-center gap-2 px-4 py-2 border border-gray-300 text-sm text-[var(--color-text)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] transition"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M12 9v3m0 0v3m0-3h3m-3 0H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            Add to Collection
          </button>
        )}

        {showDropdown && (
          <>
            <div className="fixed inset-0 z-40" onClick={() => setShowDropdown(false)} />
            <div className="absolute bottom-full mb-2 right-0 w-64 bg-white border border-gray-200 shadow-xl z-50">
              <div className="px-4 py-2 border-b border-gray-100">
                <span className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-light)]">
                  Add to Collection
                </span>
              </div>

              {loading ? (
                <div className="px-4 py-6 text-center">
                  <div className="inline-block w-5 h-5 border-2 border-gray-200 border-t-[var(--color-accent)] rounded-full animate-spin" />
                </div>
              ) : (
                <div className="max-h-48 overflow-y-auto">
                  {collections.map((col) => (
                    <button
                      key={col.id}
                      onClick={() => addToCollection(col.id)}
                      disabled={added === col.id}
                      className="w-full text-left px-4 py-2.5 text-sm hover:bg-gray-50 transition flex items-center justify-between"
                    >
                      <span className="truncate text-[var(--color-text)]">{col.name}</span>
                      {added === col.id ? (
                        <svg className="w-4 h-4 text-green-500 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                        </svg>
                      ) : (
                        <span className="text-xs text-[var(--color-text-light)] flex-shrink-0">
                          {col.property_count}
                        </span>
                      )}
                    </button>
                  ))}
                </div>
              )}

              {/* Create new */}
              <div className="border-t border-gray-100 p-3">
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    placeholder="New collection..."
                    className="flex-1 px-3 py-1.5 text-sm border border-gray-200 focus:outline-none focus:border-[var(--color-accent)]"
                    onKeyDown={(e) => e.key === "Enter" && createAndAdd()}
                  />
                  <button
                    onClick={createAndAdd}
                    disabled={creating || !newName.trim()}
                    className="px-3 py-1.5 bg-[var(--color-accent)] text-[var(--color-primary)] text-xs font-semibold disabled:opacity-50"
                  >
                    {creating ? "..." : "Add"}
                  </button>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
      <AuthModal isOpen={showAuth} onClose={() => setShowAuth(false)} />
    </>
  );
}
