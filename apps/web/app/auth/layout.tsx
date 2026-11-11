import { brand } from "@intervue/config";

import { Logo } from "@/components/brand/logo";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="flex flex-col px-6 py-8 sm:px-10">
        <Logo />
        <main id="main" className="flex flex-1 items-center justify-center py-10">
          <div className="w-full max-w-sm">{children}</div>
        </main>
      </div>
      <aside className="relative hidden overflow-hidden bg-studio p-12 text-studio-foreground lg:flex lg:flex-col lg:justify-end">
        <div className="bg-grid absolute inset-0 opacity-30" />
        <div className="relative max-w-md space-y-4">
          <p className="text-3xl font-semibold leading-tight">“The follow-ups felt like a real interviewer pushing on exactly what I said.”</p>
          <p className="text-sm text-studio-foreground/60">
            {brand.name} plans each interview from your resume and target role, asks one question at a time, and grounds every score in evidence.
          </p>
        </div>
      </aside>
    </div>
  );
}
