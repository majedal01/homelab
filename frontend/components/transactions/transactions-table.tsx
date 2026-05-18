"use client";

import * as React from "react";
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
  type ColumnFiltersState,
} from "@tanstack/react-table";
import { ArrowUpDown, ChevronLeft, ChevronRight } from "lucide-react";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { formatDollars } from "@/lib/utils";
import type { TransactionResponse } from "@/lib/api-types";

interface Row extends TransactionResponse {}

const columns: ColumnDef<Row>[] = [
  {
    accessorKey: "date",
    header: ({ column }) => (
      <SortableHeader
        label="Date"
        onSort={() => column.toggleSorting()}
        sorted={column.getIsSorted()}
      />
    ),
    cell: ({ row }) => (
      <span className="whitespace-nowrap text-muted-foreground tabular-nums">
        {row.original.date}
      </span>
    ),
  },
  {
    accessorKey: "payee_name",
    header: ({ column }) => (
      <SortableHeader
        label="Payee"
        onSort={() => column.toggleSorting()}
        sorted={column.getIsSorted()}
      />
    ),
    cell: ({ row }) => (
      <span className="truncate">{row.original.payee_name ?? "—"}</span>
    ),
    filterFn: (row, _id, value) => {
      if (!value) return true;
      const lower = String(value).toLowerCase();
      const p = row.original.payee_name?.toLowerCase() ?? "";
      const cat = row.original.category_name?.toLowerCase() ?? "";
      const memo = row.original.memo?.toLowerCase() ?? "";
      return p.includes(lower) || cat.includes(lower) || memo.includes(lower);
    },
  },
  {
    accessorKey: "category_name",
    header: "Category",
    cell: ({ row }) => (
      <span className="text-muted-foreground">
        {row.original.category_name ?? "Uncategorized"}
      </span>
    ),
  },
  {
    accessorKey: "account_name",
    header: "Account",
    cell: ({ row }) => (
      <span className="text-muted-foreground">{row.original.account_name}</span>
    ),
  },
  {
    accessorKey: "amount_cents",
    header: ({ column }) => (
      <div className="text-right">
        <SortableHeader
          label="Amount"
          onSort={() => column.toggleSorting()}
          sorted={column.getIsSorted()}
          align="right"
        />
      </div>
    ),
    cell: ({ row }) => (
      <div
        className={cn(
          "text-right font-mono tabular-nums",
          row.original.amount_cents < 0
            ? "text-destructive"
            : "text-emerald-600 dark:text-emerald-400",
        )}
      >
        {formatDollars(row.original.amount_cents)}
      </div>
    ),
  },
];

function SortableHeader({
  label,
  onSort,
  sorted,
  align = "left",
}: {
  label: string;
  onSort: () => void;
  sorted: false | "asc" | "desc";
  align?: "left" | "right";
}) {
  return (
    <button
      onClick={onSort}
      className={cn(
        "inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground",
        align === "right" && "flex-row-reverse",
      )}
    >
      {label}
      <ArrowUpDown
        className={cn("h-3 w-3 opacity-50", sorted ? "opacity-100" : "")}
      />
    </button>
  );
}

const PAGE_SIZE = 50;

export function TransactionsTable({ data }: { data: TransactionResponse[] }) {
  const [sorting, setSorting] = React.useState<SortingState>([
    { id: "date", desc: true },
  ]);
  const [columnFilters, setColumnFilters] = React.useState<ColumnFiltersState>([]);
  const [search, setSearch] = React.useState("");

  React.useEffect(() => {
    setColumnFilters((prev) => {
      const others = prev.filter((f) => f.id !== "payee_name");
      return search ? [...others, { id: "payee_name", value: search }] : others;
    });
  }, [search]);

  const table = useReactTable({
    data,
    columns,
    state: { sorting, columnFilters },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: PAGE_SIZE } },
  });

  const total = table.getFilteredRowModel().rows.length;
  const pageIndex = table.getState().pagination.pageIndex;
  const pageCount = table.getPageCount();

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <Input
          placeholder="Search payee, category, or memo…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="h-9 max-w-sm"
        />
        <span className="text-xs text-muted-foreground">
          {total} {total === 1 ? "row" : "rows"}
        </span>
      </div>

      <div className="overflow-hidden rounded-md border">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((hg) => (
              <TableRow key={hg.id}>
                {hg.headers.map((h) => (
                  <TableHead key={h.id}>
                    {h.isPlaceholder
                      ? null
                      : flexRender(h.column.columnDef.header, h.getContext())}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.length ? (
              table.getRowModel().rows.map((row) => (
                <TableRow key={row.id} className="hover:bg-accent/40">
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell
                  colSpan={columns.length}
                  className="py-10 text-center text-sm text-muted-foreground"
                >
                  No transactions match the current filters.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      {pageCount > 1 ? (
        <div className="flex items-center justify-end gap-2">
          <span className="text-xs text-muted-foreground tabular-nums">
            Page {pageIndex + 1} of {pageCount}
          </span>
          <Button
            variant="outline"
            size="icon"
            className="h-8 w-8"
            disabled={!table.getCanPreviousPage()}
            onClick={() => table.previousPage()}
            aria-label="Previous page"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            size="icon"
            className="h-8 w-8"
            disabled={!table.getCanNextPage()}
            onClick={() => table.nextPage()}
            aria-label="Next page"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      ) : null}
    </div>
  );
}
