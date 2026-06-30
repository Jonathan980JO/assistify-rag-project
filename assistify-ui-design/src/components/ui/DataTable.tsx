import { ReactNode } from "react";
import { Card } from "./Card";

export function DataTable({
  headers,
  children,
  emptyMessage = "No data",
  isEmpty,
}: {
  headers: string[];
  children: ReactNode;
  emptyMessage?: string;
  isEmpty?: boolean;
}) {
  return (
    <Card className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-[#333333] bg-[#232323]">
              {headers.map((h) => (
                <th key={h} className="px-6 py-4 text-left text-sm font-semibold text-[#9ca3af]">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isEmpty ? (
              <tr>
                <td colSpan={headers.length} className="px-6 py-8 text-center text-sm text-[#9ca3af]">
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              children
            )}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export function DataTableRow({ children }: { children: ReactNode }) {
  return (
    <tr className="border-b border-[#333333] transition-colors hover:bg-[#2b2b2b]/80">{children}</tr>
  );
}

export function DataTableCell({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <td className={`px-6 py-4 text-sm text-[#fafaff] ${className ?? ""}`}>{children}</td>;
}
