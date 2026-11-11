"use client";

import type { UserRole } from "@intervue/types";
import {
  Activity,
  BarChart3,
  BookOpen,
  Building2,
  CreditCard,
  FileStack,
  History,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Menu,
  PlusCircle,
  Settings,
  UserRound,
  Users,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

import { Logo } from "@/components/brand/logo";
import { LinkButton, Spinner } from "@/components/shared/primitives";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { useSession } from "@/lib/session";
import { cn } from "@/lib/utils";

type NavItem = { href: string; label: string; icon: React.ComponentType<{ className?: string }>; exact?: boolean };

const CANDIDATE_NAV: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/interviews/new", label: "New interview", icon: PlusCircle },
  { href: "/interviews", label: "Interviews", icon: ListChecks, exact: true },
  { href: "/history", label: "Progress", icon: History },
  { href: "/profile", label: "Profile", icon: UserRound },
];
const ORG_NAV: NavItem[] = [
  { href: "/organization", label: "Overview", icon: Building2, exact: true },
  { href: "/organization/candidates", label: "Candidates", icon: Users },
  { href: "/organization/interviews", label: "Templates & links", icon: FileStack },
  { href: "/organization/reports", label: "Reports", icon: BarChart3 },
  { href: "/organization/settings", label: "Settings", icon: Settings },
];
const ADMIN_NAV: NavItem[] = [
  { href: "/admin", label: "Command center", icon: Activity, exact: true },
  { href: "/admin/users", label: "Users", icon: Users },
  { href: "/admin/organizations", label: "Organizations", icon: Building2 },
  { href: "/admin/usage", label: "Usage & cost", icon: BarChart3 },
  { href: "/admin/questions", label: "Question bank", icon: BookOpen },
  { href: "/admin/billing", label: "Plans & pricing", icon: CreditCard },
];

function navFor(role: UserRole | undefined, hasOrg: boolean): { title: string; items: NavItem[] }[] {
  const groups = [{ title: "Practice", items: CANDIDATE_NAV }];
  if (role === "organization_admin" || hasOrg) groups.unshift({ title: "Organization", items: ORG_NAV });
  if (role === "super_admin") groups.unshift({ title: "Platform", items: ADMIN_NAV });
  return groups;
}

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { user } = useSession();
  const groups = navFor(user?.role, !!user?.organizations.some((o) => o.role !== "candidate"));
  return (
    <nav aria-label="App" className="space-y-6">
      {groups.map((g) => (
        <div key={g.title}>
          <p className="px-3 pb-1.5 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">{g.title}</p>
          <ul className="space-y-0.5">
            {g.items.map((item) => {
              const active = item.exact ? pathname === item.href : pathname === item.href || pathname.startsWith(`${item.href}/`);
              const excluded = item.href === "/interviews" && pathname === "/interviews/new";
              const on = active && !excluded;
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    onClick={onNavigate}
                    aria-current={on ? "page" : undefined}
                    className={cn(
                      "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors",
                      on ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground" : "text-sidebar-foreground/75 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground",
                    )}
                  >
                    <item.icon className="size-4" />
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function UserMenu() {
  const { user, logout } = useSession();
  const router = useRouter();
  if (!user) return null;
  const initials = user.full_name
    .split(" ")
    .map((p) => p[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <button className="flex items-center gap-2 rounded-full p-0.5 pr-2 text-sm hover:bg-muted" aria-label="Account menu">
            <span className="grid size-8 place-items-center rounded-full bg-primary/10 text-xs font-semibold text-primary">{initials || "U"}</span>
            <span className="hidden max-w-36 truncate sm:inline">{user.full_name}</span>
          </button>
        }
      />
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel>
          <div className="truncate text-sm font-medium">{user.full_name}</div>
          <div className="truncate text-xs font-normal text-muted-foreground">{user.email}</div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => router.push("/profile")}>
          <UserRound className="size-4" /> Profile
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={async () => {
            await logout();
            router.replace("/");
          }}
        >
          <LogOut className="size-4" /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { user, loading } = useSession();
  const [open, setOpen] = useState(false);

  if (pathname.endsWith("/room")) return <>{children}</>;

  if (loading)
    return (
      <div className="grid min-h-screen place-items-center">
        <Spinner className="size-5 text-muted-foreground" />
      </div>
    );

  if (!user)
    return (
      <div className="grid min-h-screen place-items-center px-4 text-center">
        <div className="space-y-3">
          <p className="font-medium">Your session has ended.</p>
          <LinkButton href={`/auth/login?next=${encodeURIComponent(pathname)}`}>Sign in again</LinkButton>
        </div>
      </div>
    );

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen print:hidden w-60 shrink-0 flex-col border-r bg-sidebar px-3 py-5 lg:flex">
        <Logo href="/" className="px-2" />
        <div className="mt-8 flex-1 overflow-y-auto">
          <NavLinks />
        </div>
        {user.is_demo && (
          <div className="rounded-lg border border-dashed p-3 text-xs text-muted-foreground">
            You&apos;re in demo mode.{" "}
            <Link href="/auth/register" className="font-medium text-foreground underline">
              Create an account
            </Link>{" "}
            to keep your results.
          </div>
        )}
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 print:hidden items-center justify-between border-b bg-background/85 px-4 backdrop-blur sm:px-6">
          <div className="flex items-center gap-2 lg:hidden">
            <Sheet open={open} onOpenChange={setOpen}>
              <SheetTrigger render={<Button variant="ghost" size="icon" aria-label="Open navigation" />}>
                <Menu className="size-5" />
              </SheetTrigger>
              <SheetContent side="left" className="w-72 p-4">
                <SheetTitle className="sr-only">Navigation</SheetTitle>
                <Logo href="/" />
                <div className="mt-6">
                  <NavLinks onNavigate={() => setOpen(false)} />
                </div>
              </SheetContent>
            </Sheet>
            <Logo href="/" className="sm:hidden" />
          </div>
          <div className="hidden lg:block" />
          <UserMenu />
        </header>
        <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">
          {children}
        </main>
      </div>
    </div>
  );
}

export function RequireRole({ roles, children }: { roles: UserRole[]; children: React.ReactNode }) {
  const { user } = useSession();
  if (!user || !roles.includes(user.role))
    return (
      <div className="rounded-xl border p-10 text-center">
        <p className="font-medium">You don&apos;t have access to this area.</p>
        <p className="mt-1 text-sm text-muted-foreground">Ask an administrator if you think this is a mistake.</p>
      </div>
    );
  return <>{children}</>;
}
