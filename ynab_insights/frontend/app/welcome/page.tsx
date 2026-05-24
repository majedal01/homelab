import { Suspense } from "react";
import { Aurora } from "@/components/brand/aurora";
import { LogoMark } from "@/components/brand/logo";
import { OnboardingCard } from "@/components/welcome/onboarding-card";

export const dynamic = "force-dynamic";

export default async function WelcomePage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const params = await searchParams;
  return (
    <>
      <Aurora variant="primary" />
      <div className="relative flex min-h-[calc(100vh-3.5rem)] items-center justify-center px-4 py-12">
        <div className="w-full max-w-md">
          <div className="mb-6 flex items-center gap-3">
            <LogoMark size={28} className="text-foreground" />
            <span className="font-semibold tracking-tight text-lg">YNAB Insights</span>
          </div>
          <Suspense fallback={null}>
            <OnboardingCard next={params.next} />
          </Suspense>
          <p className="mt-6 text-center text-xs text-muted-foreground">
            Anonymous by design. Tokens stay in server memory; nothing is written to disk.
            Close the tab or hit End session and the slate is wiped.
          </p>
        </div>
      </div>
    </>
  );
}
