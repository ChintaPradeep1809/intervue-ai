import { Suspense } from "react";

import { LoginForm } from "@/components/shared/auth-forms";

export const metadata = { title: "Sign in" };

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
