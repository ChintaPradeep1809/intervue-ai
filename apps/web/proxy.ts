import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

// Lightweight gate: redirect signed-out visitors away from private pages. Real authorization is
// enforced by the API on every request; this only avoids rendering empty private screens.
const PRIVATE = ["/dashboard", "/interviews", "/history", "/profile", "/organization", "/admin", "/onboarding"];

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const isPrivate = PRIVATE.some((p) => pathname === p || pathname.startsWith(`${p}/`));
  if (isPrivate && !request.cookies.has("iv_session")) {
    const url = new URL("/auth/login", request.url);
    url.searchParams.set("next", pathname + search);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|.*\\..*).*)"],
};
