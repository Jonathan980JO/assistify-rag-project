"use client";

import { BarChart3, Clock, RefreshCw, TrendingUp, Users } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useAnalytics } from "@/src/hooks/useAnalytics";
import { Card } from "@/src/components/ui/Card";
import { DataTable, DataTableCell, DataTableRow } from "@/src/components/ui/DataTable";
import { PageHeader } from "@/src/components/ui/PageHeader";
import { StatCard } from "@/src/components/ui/StatCard";

const ROLE_COLORS = ["#10a37f", "#2563eb", "#f6c33c", "#6c63ff", "#ef4444"];

export function AnalyticsPageContent({ title = "Analytics" }: { title?: string }) {
  const { summary, errors, loading, refresh } = useAnalytics();
  const data = summary as {
    total_queries?: number;
    success_rate?: number;
    avg_response_time?: number;
    usage_by_role?: { role: string; count: number; avg_time?: number }[];
    hourly_distribution?: { hour: string; count: number }[];
    daily_trend?: { day: string; total: number; successful: number }[];
    rag_performance?: { rag_hit_rate?: number };
    satisfaction?: { satisfaction_rate?: number };
    top_errors?: { error: string; count: number }[];
  } | null;

  const dailyTrend = [...(data?.daily_trend ?? [])].reverse();
  const usageByRole = data?.usage_by_role ?? [];
  const hourly = data?.hourly_distribution ?? [];
  const modelPerf = usageByRole.map((r) => ({
    role: r.role,
    avg_time: r.avg_time ?? 0,
  }));

  return (
    <div>
      <div className="mb-6 flex items-start justify-between gap-4">
        <PageHeader title={title} subtitle="Performance metrics and monitoring" />
        <button
          type="button"
          onClick={() => refresh().catch(() => {})}
          disabled={loading}
          className="flex items-center gap-2 rounded-lg bg-[#10a37f] px-4 py-2 text-sm font-medium text-white hover:bg-[#0d8a68] disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {loading ? (
        <p className="text-[#9ca3af]">Loading analytics...</p>
      ) : (
        <>
          <div className="mb-8 grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-4">
            <StatCard
              icon={<BarChart3 className="h-6 w-6" />}
              label="Total Queries"
              value={String(data?.total_queries ?? "—")}
              colorClass="text-[#10a37f]"
            />
            <StatCard
              icon={<TrendingUp className="h-6 w-6" />}
              label="Success Rate"
              value={data?.success_rate != null ? `${data.success_rate}%` : "—"}
              colorClass="text-[#2563eb]"
            />
            <StatCard
              icon={<Clock className="h-6 w-6" />}
              label="Avg Response"
              value={data?.avg_response_time != null ? `${data.avg_response_time} ms` : "—"}
              colorClass="text-[#f6c33c]"
            />
            <StatCard
              icon={<Users className="h-6 w-6" />}
              label="User Satisfaction"
              value={
                data?.satisfaction?.satisfaction_rate != null
                  ? `${data.satisfaction.satisfaction_rate}%`
                  : "—"
              }
              colorClass="text-[#6c63ff]"
            />
          </div>

          <div className="mb-8 grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-4">
            <StatCard
              icon={<TrendingUp className="h-6 w-6" />}
              label="RAG Hit Rate"
              value={
                data?.rag_performance?.rag_hit_rate != null
                  ? `${data.rag_performance.rag_hit_rate}%`
                  : "—"
              }
              colorClass="text-[#10a37f]"
            />
            <StatCard
              icon={<BarChart3 className="h-6 w-6" />}
              label="Total Errors"
              value={String(errors.length)}
              colorClass="text-red-400"
            />
            <StatCard
              icon={<BarChart3 className="h-6 w-6" />}
              label="Validation Blocks"
              value={String(data?.top_errors?.length ?? 0)}
              colorClass="text-[#f59e0b]"
            />
          </div>

          <div className="mb-8 grid gap-6 lg:grid-cols-2">
            <Card className="p-6">
              <h2 className="mb-4 text-lg font-semibold text-[#fafaff]">Daily Trend (Last 7 Days)</h2>
              <div className="h-64">
                {dailyTrend.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={dailyTrend}>
                      <CartesianGrid stroke="#333" strokeDasharray="3 3" />
                      <XAxis dataKey="day" stroke="#9ca3af" fontSize={12} />
                      <YAxis stroke="#9ca3af" fontSize={12} />
                      <Tooltip
                        contentStyle={{ background: "#2b2b2b", border: "1px solid #333", borderRadius: 8 }}
                      />
                      <Line type="monotone" dataKey="total" stroke="#10a37f" strokeWidth={2} name="Total" />
                      <Line type="monotone" dataKey="successful" stroke="#2563eb" strokeWidth={2} name="Successful" />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <p className="py-12 text-center text-[#9ca3af]">No trend data yet</p>
                )}
              </div>
            </Card>

            <Card className="p-6">
              <h2 className="mb-4 text-lg font-semibold text-[#fafaff]">Usage by Role</h2>
              <div className="h-64">
                {usageByRole.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={usageByRole}
                        dataKey="count"
                        nameKey="role"
                        cx="50%"
                        cy="50%"
                        outerRadius={80}
                        label={(props) => {
                          const payload = props.payload as { role?: string; count?: number } | undefined;
                          const role = String(payload?.role ?? props.name ?? "");
                          const count = Number(payload?.count ?? props.value ?? 0);
                          return `${role}: ${count}`;
                        }}
                      >
                        {usageByRole.map((_, i) => (
                          <Cell key={i} fill={ROLE_COLORS[i % ROLE_COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip
                        contentStyle={{ background: "#2b2b2b", border: "1px solid #333", borderRadius: 8 }}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                ) : (
                  <p className="py-12 text-center text-[#9ca3af]">No role usage data yet</p>
                )}
              </div>
            </Card>

            <Card className="p-6">
              <h2 className="mb-4 text-lg font-semibold text-[#fafaff]">Hourly Distribution</h2>
              <div className="h-64">
                {hourly.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={hourly}>
                      <CartesianGrid stroke="#333" strokeDasharray="3 3" />
                      <XAxis dataKey="hour" stroke="#9ca3af" fontSize={12} />
                      <YAxis stroke="#9ca3af" fontSize={12} />
                      <Tooltip
                        contentStyle={{ background: "#2b2b2b", border: "1px solid #333", borderRadius: 8 }}
                      />
                      <Bar dataKey="count" fill="#10a37f" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <p className="py-12 text-center text-[#9ca3af]">No hourly data yet</p>
                )}
              </div>
            </Card>

            <Card className="p-6">
              <h2 className="mb-4 text-lg font-semibold text-[#fafaff]">Avg Response by Role</h2>
              <div className="h-64">
                {modelPerf.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={modelPerf} layout="vertical">
                      <CartesianGrid stroke="#333" strokeDasharray="3 3" />
                      <XAxis type="number" stroke="#9ca3af" fontSize={12} />
                      <YAxis type="category" dataKey="role" stroke="#9ca3af" fontSize={12} width={80} />
                      <Tooltip
                        contentStyle={{ background: "#2b2b2b", border: "1px solid #333", borderRadius: 8 }}
                      />
                      <Bar dataKey="avg_time" fill="#6c63ff" radius={[0, 4, 4, 0]} name="Avg ms" />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <p className="py-12 text-center text-[#9ca3af]">No performance data yet</p>
                )}
              </div>
            </Card>
          </div>

          <Card className="p-6">
            <h2 className="mb-4 text-lg font-semibold text-[#fafaff]">Recent Errors</h2>
            <DataTable
              headers={["Timestamp", "User", "Error"]}
              isEmpty={errors.length === 0}
              emptyMessage="No recent errors"
            >
              {errors.map((err, i) => (
                <DataTableRow key={`${err.timestamp}-${i}`}>
                  <DataTableCell className="text-[#9ca3af]">{err.timestamp}</DataTableCell>
                  <DataTableCell>{err.username ?? "—"}</DataTableCell>
                  <DataTableCell className="text-red-400">{err.error}</DataTableCell>
                </DataTableRow>
              ))}
            </DataTable>
          </Card>
        </>
      )}
    </div>
  );
}
