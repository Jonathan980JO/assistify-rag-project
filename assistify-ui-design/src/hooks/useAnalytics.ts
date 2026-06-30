"use client";

import { useCallback, useEffect, useState } from "react";
import { apiClient } from "@/src/lib/apiClient";

export interface AnalyticsError {
  timestamp: string;
  username?: string;
  error: string;
  response_time?: number | null;
}

export interface ComprehensiveAnalytics {
  total_queries?: number;
  success_rate?: number;
  avg_response_time?: number;
  usage_by_role?: { role: string; count: number; avg_time?: number }[];
  hourly_distribution?: { hour: string; count: number }[];
  daily_trend?: { day: string; total: number; successful: number }[];
  rag_performance?: { rag_hit_rate?: number; avg_docs_found?: number };
  satisfaction?: { satisfaction_rate?: number; avg_rating?: number };
  top_errors?: { error: string; count: number }[];
}

export function useAnalytics({ mode = "comprehensive" }: { mode?: "comprehensive" | "employee" } = {}) {
  const [summary, setSummary] = useState<ComprehensiveAnalytics | Record<string, unknown> | null>(null);
  const [errors, setErrors] = useState<AnalyticsError[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      if (mode === "employee") {
        const data = await apiClient.get<Record<string, unknown>>("/api/employee/analytics");
        setSummary(data);
        setErrors([]);
      } else {
        const [comprehensive, errorData] = await Promise.all([
          apiClient.get<ComprehensiveAnalytics>("/api/analytics/comprehensive?days=30"),
          apiClient.get<{ errors: AnalyticsError[] }>("/api/analytics/errors?limit=50"),
        ]);
        setSummary(comprehensive);
        setErrors(errorData.errors ?? []);
      }
    } finally {
      setLoading(false);
    }
  }, [mode]);

  useEffect(() => {
    refresh().catch(() => {});
  }, [refresh]);

  return { summary, errors, loading, refresh };
}
