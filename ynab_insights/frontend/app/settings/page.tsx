import { Aurora } from "@/components/brand/aurora";
import { DemoBanner } from "@/components/demo/demo-banner";
import { SettingsPanel } from "@/components/settings/settings-panel";
import { requireSession } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const session = await requireSession();
  return (
    <>
      <Aurora variant="quiet" />
      <div className="mx-auto flex max-w-2xl flex-col gap-6">
        {session.is_demo && <DemoBanner />}
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
          <p className="text-sm text-muted-foreground">
            Your session lives only in this server&apos;s memory. Refresh pulls new
            YNAB data; End session wipes everything.
          </p>
        </div>
        <SettingsPanel session={session} />
        <PrivacyNotice />
      </div>
    </>
  );
}

function PrivacyNotice() {
  return (
    <section className="rounded-lg border bg-card/60 backdrop-blur p-5 text-sm">
      <h2 className="text-sm font-semibold tracking-tight">What we store</h2>
      <ul className="mt-2 space-y-1 text-muted-foreground">
        <li>
          <strong className="text-foreground">In memory only:</strong> your tokens, the
          YNAB snapshot, and the insights generated this session.
        </li>
        <li>
          <strong className="text-foreground">On disk:</strong> nothing related to you.
          No accounts. No analytics. No logs of your data.
        </li>
        <li>
          <strong className="text-foreground">In your browser:</strong> a list of
          dismissed-insight identifiers (no money figures), so the same card doesn&apos;t
          come back. Cleared with site data.
        </li>
        <li>
          <strong className="text-foreground">Session expiry:</strong> one hour idle,
          four hours absolute. After that the server forgets everything.
        </li>
        <li>
          <strong className="text-foreground">Switching providers:</strong> end your
          session above and re-onboard with the new key. Provider is fixed for the
          life of a session.
        </li>
      </ul>
    </section>
  );
}
