"use client";

import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch, LoadState } from "@/components/ui";
import { CrmEditor, type CrmData } from "@/components/CrmEditor";

function NewRestaurant() {
  const router = useRouter();
  const { data, loading, error, reload } = useFetch<CrmData>(
    () => api.get<CrmData>("/restaurants/crm/schema"), []);
  return (
    <div>
      <PageHeader title="Add Restaurant"
        subtitle="SavoryMind prospect record — restaurant profile, owner, intelligence, finance, and menu / employees / customers / inventory. Unlimited custom fields." />
      {(loading || error) && <LoadState loading={loading} error={error} onRetry={reload} />}
      {data && (
        <CrmEditor data={data} mode="create" entity="restaurant"
          onSaved={() => router.push("/savorymind")} />
      )}
    </div>
  );
}

export default function Page() {
  return <AuthGate><NewRestaurant /></AuthGate>;
}
