import { Suspense } from "react";

import { RegisterForm } from "@/components/shared/auth-forms";

export const metadata = { title: "Create account" };

export default function RegisterPage() {
  return (
    <Suspense>
      <RegisterForm />
    </Suspense>
  );
}
