"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import Link from "next/link";

interface Collection {
  id: string;
  name: string;
  description: string;
  status: string;
  share_token: string;
  property_count: number;
  created_at: string;
  updated_at: string;
}

export default function CollectionsPage() {
  const { data: session, status } = useSession();
  const router = useRouter();
  const [collections, setCollections] = useState<Collection[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    if (status === "unauthenticated") {
      router.push("/listings");
      return;
    }
    if (status !== "authenticated") return;
    fetchCollections();
  }, [status, router]);

  async function fetchCollections() {
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

  const createCollection = async () => {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      const res = await fetch("/api/user/collections", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newName.trim(), description: newDesc.trim() }),
      });
      if (res.ok) {
        setNewName("");
        setNewDesc("");
        setShowCreate(false);
        await fetchCollections();
      }
    } catch {
      // Silently fail
    } finally {
      setCreating(false);
    }
  };

  const deleteCollection = async (id: string) => {
    if (!confirm("Delete this collection? This cannot be undone.")) return;
    await fetch(`/api/user/collections/${id}`, { method: "DELETE" });
    setCollections((prev) => prev.filter((c) => c.id !== id));
  };

  if (status === "loading" || loading) {
    return (
      <div className="bg-[var(--color-eggshell)] min-h-screen">
        <div className="h-20 bg-[var(--color-primary)]" />
        <div className="max-w-7xl mx-auto px-6 py-16 text-center">
          <div className="inline-block w-8 h-8 border-4 border-[var(--color-primary)]/20 border-t-[var(--color-accent)] rounded-full animate-spin" />
        </div>
      </div>
    );
  }

  return (
    <div className="bg-[var(--color-eggshell)] min-h-screen">
      <div className="h-20 bg-[var(--color-primary)]" />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1
              className="text-3xl text-[var(--color-primary)]"
              style={{ fontFamily: "Georgia, serif" }}
            >
              My Collections
            </h1>
            <p className="text-[var(--color-text-light)] mt-2">
              {collections.length} {collections.length === 1 ? "collection" : "collections"}
            </p>
          </div>
          <button
            onClick={() => setShowCreate(true)}
            className="px-5 py-2.5 bg-[var(--color-accent)] text-[var(--color-primary)] font-semibold text-sm uppercase tracking-wider hover:bg-[var(--color-accent-hover)] transition"
          >
            New Collection
          </button>
        </div>

        {/* Create modal */}
        {showCreate && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
            <div className="bg-white w-full max-w-md mx-4 p-6 shadow-xl">
              <h2 className="text-xl text-[var(--color-primary)] mb-4" style={{ fontFamily: "Georgia, serif" }}>
                New Collection
              </h2>
              <input
                type="text"
                placeholder="Collection name"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                className="w-full px-4 py-2.5 border border-gray-300 text-sm focus:outline-none focus:border-[var(--color-accent)] mb-3"
                autoFocus
              />
              <textarea
                placeholder="Description (optional)"
                value={newDesc}
                onChange={(e) => setNewDesc(e.target.value)}
                className="w-full px-4 py-2.5 border border-gray-300 text-sm focus:outline-none focus:border-[var(--color-accent)] mb-4 h-20 resize-none"
              />
              <div className="flex justify-end gap-3">
                <button
                  onClick={() => { setShowCreate(false); setNewName(""); setNewDesc(""); }}
                  className="px-4 py-2 text-sm text-[var(--color-text-light)] hover:text-[var(--color-text)] transition"
                >
                  Cancel
                </button>
                <button
                  onClick={createCollection}
                  disabled={creating || !newName.trim()}
                  className="px-5 py-2 bg-[var(--color-accent)] text-[var(--color-primary)] font-semibold text-sm uppercase tracking-wider hover:bg-[var(--color-accent-hover)] transition disabled:opacity-50"
                >
                  {creating ? "Creating..." : "Create"}
                </button>
              </div>
            </div>
          </div>
        )}

        {collections.length === 0 ? (
          <div className="text-center py-20">
            <svg className="w-16 h-16 text-gray-300 mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
            </svg>
            <h3 className="text-xl text-[var(--color-primary)] mb-2">No collections yet</h3>
            <p className="text-[var(--color-text-light)] mb-6">
              Create a collection to organize properties you are comparing or sharing.
            </p>
            <button
              onClick={() => setShowCreate(true)}
              className="inline-block px-6 py-3 bg-[var(--color-accent)] text-[var(--color-primary)] font-semibold text-sm uppercase tracking-wider hover:bg-[var(--color-accent-hover)] transition"
            >
              Create Your First Collection
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            {collections.map((col) => (
              <div
                key={col.id}
                className="bg-white border border-gray-200/60 p-6 flex items-center justify-between"
              >
                <div className="flex-1 min-w-0">
                  <Link
                    href={`/account/collections/${col.id}`}
                    className="text-lg text-[var(--color-primary)] font-medium hover:text-[var(--color-accent)] transition truncate block"
                  >
                    {col.name}
                  </Link>
                  {col.description && (
                    <p className="text-sm text-[var(--color-text-light)] mt-1 truncate">
                      {col.description}
                    </p>
                  )}
                  <div className="flex items-center gap-4 mt-2 text-xs text-[var(--color-text-light)]">
                    <span>{col.property_count} {col.property_count === 1 ? "property" : "properties"}</span>
                    <span>Created {new Date(col.created_at).toLocaleDateString()}</span>
                  </div>
                </div>
                <div className="flex items-center gap-3 ml-4">
                  <Link
                    href={`/account/collections/${col.id}`}
                    className="px-4 py-2 bg-[var(--color-accent)] text-[var(--color-primary)] text-sm font-semibold uppercase tracking-wider hover:bg-[var(--color-accent-hover)] transition"
                  >
                    View
                  </Link>
                  <button
                    onClick={() => deleteCollection(col.id)}
                    className="px-3 py-2 text-sm text-red-500 hover:text-red-700 transition"
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
