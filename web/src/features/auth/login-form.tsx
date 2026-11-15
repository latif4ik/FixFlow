"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Wrench } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button, Card, FormField, FormServerError, Input } from "@/components/ui";
import type { LoginResponse } from "@/lib/api/types";
import { useAuth } from "@/lib/auth/auth-context";
import { safeNext } from "@/lib/auth/session";
import { landingFor } from "@/lib/nav";
import { applyServerErrors, useApiMutation } from "@/lib/query/hooks";

const schema = z.object({
  email: z.string().trim().min(1, "Enter your email").email("Enter a valid email address"),
  password: z.string().min(1, "Enter your password"),
});
type Values = z.infer<typeof schema>;

export function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { status, role, completeLogin } = useAuth();
  const next = safeNext(params.get("next"));
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: "", password: "" } });

  // Already signed in: skip the form.
  useEffect(() => {
    if (status === "authenticated") router.replace(role ? landingFor(role, next) : "/select-org");
  }, [status, role, next, router]);

  const login = useApiMutation<LoginResponse, Values>({
    request: (v) => ({ path: "/auth/login", body: { email: v.email, password: v.password }, anonymous: true }),
    errorMessage: false,
    onSuccess: (res) => {
      router.replace(completeLogin(res, next));
    },
    onError: (e) => {
      applyServerErrors(form, e);
    },
  });

  return (
    <Card className="w-full max-w-sm p-6 sm:p-8">
      <div className="mb-6 flex items-center gap-2 font-heading text-xl font-extrabold text-deep">
        <span aria-hidden className="flex size-9 items-center justify-center rounded-md bg-primary text-white">
          <Wrench className="size-5" />
        </span>
        FixFlow
      </div>
      <h1 className="text-2xl font-extrabold">Sign in</h1>
      {params.get("expired") && (
        <p role="status" className="mt-3 rounded-md bg-warning-tint px-3 py-2 text-sm text-warning-dark">
          Your session expired. Sign in again to continue.
        </p>
      )}
      <form noValidate onSubmit={form.handleSubmit((v) => login.mutate(v))} className="mt-5 flex flex-col gap-4">
        <FormField label="Email" required error={form.formState.errors.email?.message}>
          <Input type="email" autoComplete="username" {...form.register("email")} />
        </FormField>
        <FormField label="Password" required error={form.formState.errors.password?.message}>
          <Input type="password" autoComplete="current-password" {...form.register("password")} />
        </FormField>
        <FormServerError form={form} />
        <Button type="submit" size="lg" loading={login.isPending}>
          {login.isPending ? "Signing in" : "Sign in"}
        </Button>
      </form>
    </Card>
  );
}
