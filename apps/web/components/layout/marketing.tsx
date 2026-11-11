"use client";

import { brand } from "@intervue/config";
import Link from "next/link";

import { Logo } from "@/components/brand/logo";
import { LinkButton } from "@/components/shared/primitives";
import { homeFor, useSession } from "@/lib/session";

export function MarketingHeader() {
  const { user } = useSession();
  return (
    <header className="sticky top-0 z-40 border-b border-transparent bg-background/85 backdrop-blur supports-[backdrop-filter]:bg-background/70">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
        <Logo />
        <nav aria-label="Main" className="hidden items-center gap-6 text-sm text-muted-foreground md:flex">
          <a href="#how" className="hover:text-foreground">How it works</a>
          <a href="#features" className="hover:text-foreground">Features</a>
          <a href="#colleges" className="hover:text-foreground">For colleges</a>
          <a href="#pricing" className="hover:text-foreground">Pricing</a>
          <a href="#faq" className="hover:text-foreground">FAQ</a>
        </nav>
        <div className="flex items-center gap-2">
          {user ? (
            <LinkButton href={homeFor(user)} size="sm">
              Open app
            </LinkButton>
          ) : (
            <>
              <LinkButton href="/auth/login" variant="ghost" size="sm">
                Sign in
              </LinkButton>
              <LinkButton href="/auth/register" size="sm">
                Get started
              </LinkButton>
            </>
          )}
        </div>
      </div>
    </header>
  );
}

export function MarketingFooter() {
  return (
    <footer className="border-t">
      <div className="mx-auto grid max-w-6xl gap-8 px-4 py-12 text-sm sm:grid-cols-4 sm:px-6">
        <div className="space-y-3 sm:col-span-2">
          <Logo />
          <p className="max-w-sm text-muted-foreground">AI-powered, role-specific interview practice and assessment for candidates, colleges and companies.</p>
        </div>
        <div className="space-y-2">
          <p className="font-medium">Product</p>
          <ul className="space-y-1.5 text-muted-foreground">
            <li><Link href="/demo" className="hover:text-foreground">Try a demo</Link></li>
            <li><a href="#pricing" className="hover:text-foreground">Pricing</a></li>
            <li><Link href="/auth/register?type=organization" className="hover:text-foreground">For organizations</Link></li>
          </ul>
        </div>
        <div className="space-y-2">
          <p className="font-medium">Trust</p>
          <ul className="space-y-1.5 text-muted-foreground">
            <li><a href="#privacy" className="hover:text-foreground">Privacy & consent</a></li>
            <li><a href={`mailto:${brand.supportEmail}`} className="hover:text-foreground">Contact</a></li>
          </ul>
        </div>
      </div>
      <div className="border-t py-5 text-center text-xs text-muted-foreground">
        © {new Date().getFullYear()} {brand.name}. AI-assisted assessments support — not replace — human decisions.
      </div>
    </footer>
  );
}
