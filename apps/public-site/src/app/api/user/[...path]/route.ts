/**
 * Proxy for /api/user/* requests.
 *
 * Auth.js stores the session in an HTTP-only cookie that Flask cannot
 * read. This route handler decodes the session server-side, signs a
 * short-lived JWT with the user ID, and forwards the request to the
 * Flask API with an Authorization header.
 *
 * All requests are forwarded to Flask. Flask decides which endpoints
 * require authentication and which don't.
 */

import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { SignJWT } from "jose";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";
const AUTH_SECRET = process.env.AUTH_SECRET || "";

async function createUserJWT(userId: string): Promise<string> {
  const secret = new TextEncoder().encode(AUTH_SECRET);
  return new SignJWT({ id: userId, sub: userId })
    .setProtectedHeader({ alg: "HS256" })
    .setExpirationTime("5m")
    .sign(secret);
}

async function proxyToFlask(
  req: NextRequest,
  pathSegments: string[],
): Promise<NextResponse> {
  const session = await auth();
  const flaskPath = `/api/user/${pathSegments.join("/")}`;
  const url = `${API_BASE}${flaskPath}`;

  // Build headers to forward
  const headers: Record<string, string> = {
    "Content-Type": req.headers.get("content-type") || "application/json",
  };

  // Add auth header if we have a session; otherwise forward without it
  // and let Flask decide whether to return 401
  if (session?.user?.id) {
    const token = await createUserJWT(session.user.id);
    headers["Authorization"] = `Bearer ${token}`;
  }

  // Forward the request body for non-GET methods
  let body: string | undefined;
  if (req.method !== "GET" && req.method !== "HEAD") {
    try {
      body = await req.text();
    } catch {
      // No body
    }
  }

  // Forward query string
  const queryString = req.nextUrl.search;
  const fullUrl = queryString ? `${url}${queryString}` : url;

  try {
    const flaskRes = await fetch(fullUrl, {
      method: req.method,
      headers,
      body,
    });

    // Check if response is JSON or binary (PDF)
    const contentType = flaskRes.headers.get("content-type") || "";

    if (contentType.includes("application/pdf")) {
      const pdfBuffer = await flaskRes.arrayBuffer();
      return new NextResponse(pdfBuffer, {
        status: flaskRes.status,
        headers: {
          "Content-Type": "application/pdf",
          "Content-Disposition":
            flaskRes.headers.get("content-disposition") || "attachment",
        },
      });
    }

    const data = await flaskRes.json();
    return NextResponse.json(data, { status: flaskRes.status });
  } catch {
    return NextResponse.json(
      { success: false, error: "API unavailable" },
      { status: 502 },
    );
  }
}

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  return proxyToFlask(req, path);
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  return proxyToFlask(req, path);
}

export async function PUT(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  return proxyToFlask(req, path);
}

export async function DELETE(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  return proxyToFlask(req, path);
}
