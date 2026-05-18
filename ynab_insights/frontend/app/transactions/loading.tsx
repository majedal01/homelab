import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export default function TransactionsLoading() {
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-2">
          <Skeleton className="h-6 w-36" />
          <Skeleton className="h-4 w-64" />
        </div>
        <Skeleton className="h-9 w-40" />
      </div>
      <Card>
        <CardContent className="flex flex-wrap items-end gap-3 p-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-9 w-32" />
          ))}
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-0">
          {Array.from({ length: 10 }).map((_, i) => (
            <div
              key={i}
              className="flex items-center justify-between gap-4 border-b px-4 py-3 last:border-b-0"
            >
              <div className="flex flex-1 gap-4">
                <Skeleton className="h-4 w-20" />
                <Skeleton className="h-4 w-40" />
                <Skeleton className="h-4 w-32" />
              </div>
              <Skeleton className="h-4 w-20" />
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
