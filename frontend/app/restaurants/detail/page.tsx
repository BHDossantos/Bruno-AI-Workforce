"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch, LoadState } from "@/components/ui";
import { CrmEditor, type CrmData } from "@/components/CrmEditor";

function RestaurantProfile() {
  const id = useSearchParams().get("id") || "";
  const { data, loading, error, reload } = useFetch<CrmData>(
    () => api.get<CrmData>(`/restaurants/${id}/crm`), [id]);
  const name = (data?.profile?.restaurant_profile as Record<string, unknown> | undefined)?.name as string | undefined;
  return (
    <div>
      <PageHeader title={name || "Restaurant"}
        subtitle="SavoryMind CRM — profile, owner, intelligence, finance, menu, employees and more." />
      {(loading || error) && <LoadState loading={loading} error={error} onRetry={reload} />}
      {data && <CrmEditor data={data} mode="edit" entity="restaurant" onSaved={reload} />}
    </div>
  );
}

export default function Page() {
  // See the note in app/leads/detail — same static-route pattern.
  return (
    <Suspense fallback={null}>
      <AuthGate><RestaurantProfile /></AuthGate>
    </Suspense>
  );
}
