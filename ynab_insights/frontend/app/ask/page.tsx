import { AskShell } from "@/components/ask/ask-shell";
import { Aurora } from "@/components/brand/aurora";
import { requireSession } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function AskPage() {
  await requireSession();
  return (
    <>
      <Aurora variant="quiet" />
      <AskShell />
    </>
  );
}
