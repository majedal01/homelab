import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export default function AccountsLoading() {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Skeleton className="h-6 w-32" />
        <Skeleton className="h-4 w-56" />
      </div>
      <Card>
        <CardContent className="flex items-baseline justify-between p-6">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-8 w-40" />
        </CardContent>
      </Card>
      {Array.from({ length: 3 }).map((_, s) => (
        <div key={s} className="space-y-3">
          <Card>
            <CardContent className="flex items-center justify-between p-4">
              <Skeleton className="h-5 w-28" />
              <Skeleton className="h-5 w-24" />
            </CardContent>
          </Card>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 3 }).map((_, j) => (
              <Card key={j}>
                <CardContent className="space-y-2 p-4">
                  <Skeleton className="h-4 w-40" />
                  <Skeleton className="h-7 w-28" />
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
