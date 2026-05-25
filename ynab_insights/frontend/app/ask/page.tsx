import Link from "next/link";
import { MessageSquare } from "lucide-react";

import { AskShell } from "@/components/ask/ask-shell";
import { Aurora } from "@/components/brand/aurora";
import { DemoBanner } from "@/components/demo/demo-banner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { requireSession } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function AskPage() {
  const session = await requireSession();
  if (session.is_demo) {
    return (
      <>
        <Aurora variant="quiet" />
        <div className="mx-auto flex max-w-3xl flex-col gap-6">
          <DemoBanner />
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Ask</h1>
            <p className="text-sm text-muted-foreground">
              Questions about your money, in plain language.
            </p>
          </div>
          <Card>
            <CardContent className="flex flex-col items-center gap-4 p-10 text-center">
              <div className="rounded-full bg-muted p-3 text-muted-foreground">
                <MessageSquare className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-sm font-medium">Ask needs your own LLM key.</h2>
                <p className="mt-1 max-w-sm text-xs text-muted-foreground">
                  The demo shows what insights and the explore views look like.
                  Ask runs against a real Claude or OpenAI key against your own
                  YNAB data. Sign in to enable it.
                </p>
              </div>
              <Button asChild>
                <Link href="/welcome">Sign in</Link>
              </Button>
            </CardContent>
          </Card>
        </div>
      </>
    );
  }
  return (
    <>
      <Aurora variant="quiet" />
      <AskShell />
    </>
  );
}
