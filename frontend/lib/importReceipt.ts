export type ImportKind = "leads" | "bnb" | "restaurants" | "contacts";
export const DESTINATIONS: Record<ImportKind, { href: string; label: string; hint: string }> = {
  leads: { href: "/insurance", label: "Open Insurance Leads", hint: "Clear active filters or look up a company or email. For a tagged list, select its category." },
  bnb: { href: "/bnbglobal", label: "Open B&B Global", hint: "Clear active filters or look up a company or email." },
  restaurants: { href: "/savorymind", label: "Open SavoryMind", hint: "Clear active filters or look up a restaurant or email." },
  contacts: { href: "/crm", label: "Open Universal CRM", hint: "Select Added and search by name or email. Only the reported Personal leads also appear under Insurance." },
};
type Receipt = { status: "confirmed" | "no-changes" | "unconfirmed"; message: string; rows: { label: string; count: number }[] };

function count(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;
}

export function fileProblem(name: string, bytes: number) {
  if (!/\.(csv|vcf)$/i.test(name)) return "Choose a CSV (.csv) or vCard (.vcf) file. XML is not supported.";
  if (bytes === 0) return "This file is empty. Choose an export that contains records.";
  return null;
}

export function importReceipt(kind: ImportKind, payload: unknown): Receipt {
  const data = (payload && typeof payload === "object" ? payload : {}) as Record<string, unknown>;
  const imported = count(data.imported);
  const updated = count(data.updated);
  if (imported === null || (kind !== "contacts" && updated === null)
    || (data.ok === false && (imported > 0 || (updated ?? 0) > 0))) {
    return { status: "unconfirmed", message: "The server did not confirm the outcome. Check the destination before trying again.", rows: [] };
  }

  const rows: Receipt["rows"] = [{ label: "Created", count: imported }];
  const skipped = kind === "contacts" ? count(data.skipped) : count(data.skipped_no_contact) ?? count(data.skipped_no_email);
  if (kind !== "contacts" && updated !== null) rows.push({ label: "Matched existing / updated", count: updated });
  if (skipped !== null) rows.push({ label: kind === "contacts" ? "Skipped (duplicate or unusable)" : kind === "leads" ? "Skipped (no email or phone)" : "Skipped (no email)", count: skipped });
  const leadsAdded = count(data.leads_added);
  if (kind === "contacts" && leadsAdded !== null) rows.push({ label: "Also added as Personal leads", count: leadsAdded });
  if (imported === 0 && (updated ?? 0) === 0) {
    return { status: "no-changes", message: "No records were created or updated. Check for duplicates, missing fields or an empty export.", rows };
  }
  return { status: "confirmed", message: "Import results recorded. This is not an outreach report.", rows };
}

export function importError(status: number, payload: unknown) {
  if (status === 401 || status === 403) return "Import access was denied. Check your sign-in and permissions.";
  if (status === 400 || status === 422) {
    const detail = (payload as { detail?: unknown } | null)?.detail;
    return typeof detail === "string" ? detail : "The server rejected the file. Check its columns or start from the CSV template.";
  }
  return "The import result could not be confirmed. Check the destination before retrying to avoid repeat rows.";
}
