// Login entry → Auth0 Universal Login via the SDK route handler.
export default function LoginPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6">
      <div className="text-center">
        <h1 className="text-2xl font-bold">Terzo Cost Intelligence</h1>
        <p className="mt-2 text-sm text-slate-500">
          Sign in with your organization account.
        </p>
      </div>
      <a
        href="/api/auth/login?returnTo=/dashboard"
        className="rounded-md bg-brand px-5 py-2.5 text-sm font-medium text-brand-fg"
      >
        Sign in with SSO
      </a>
    </main>
  );
}
