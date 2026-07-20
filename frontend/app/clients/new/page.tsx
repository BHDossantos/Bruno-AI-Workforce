"use client";

import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { AuthGate, PageHeader, useFetch, LoadState } from "@/components/ui";
import { CrmEditor, type CrmData } from "@/components/CrmEditor";

function NewClient() {
  const router = useRouter();
  const { data, loading, error, reload } = useFetch<CrmData>(
    () => api.get<CrmData>("/leads/crm/schema?module=insurance"), []);
  return (
    <div>
      <PageHeader title="Add Client"
        subtitle="Create a client record — personal, contact, coverage, vehicles, drivers and more. Unlimited custom fields." />
      {(loading || error) && <LoadState loading={loading} error={error} onRetry={reload} />}
      {data && (
        <CrmEditor data={data} mode="create"
          onSaved={(leadId) => leadId && router.push(`/leads/${leadId}`)} />
      )}
    </div>
  );
}

export default function Page() {
  return <AuthGate><NewClient /></AuthGate>;
}
