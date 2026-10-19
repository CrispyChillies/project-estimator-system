import { NextResponse, type NextRequest } from "next/server";

// Optimistic check only: a visitor who already has a session cookie goes straight to the app.
// The app layout still verifies the session with the backend (and sends invalid sessions to /signin).
export function proxy(request: NextRequest) {
  if (request.cookies.has("calibr_session")) return NextResponse.redirect(new URL("/dashboard", request.url));
  return NextResponse.next();
}

export const config = { matcher: "/" };
