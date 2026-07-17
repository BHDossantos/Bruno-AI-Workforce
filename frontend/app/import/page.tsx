"use client";

import { useState } from "react";
import { API_URL, getToken } from "@/lib/api";
import { AuthGate, PageHeader } from "@/components/ui";

function Importer() {
  const [type, setType] = useState("leads");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  async function upload() {
    if (!file) return;
    setBusy(true);
    setResult(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`${API_URL}/import/${type}`, {
        method: "POST",
        headers: getToken() ? { Authorization: `Bearer ${getToken()}` } : {},
        body: fd,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(JSON.stringify(data));
      const imported = data.imported ?? 0;
      const updated = data.updated ?? 0;
      if (imported === 0 && updated === 0 && type !== "contacts") {
        // Don't show a green check for a total no-op — surface why nothing imported.
        setResult(`❌ Imported 0. ${data.reason || "Check the file format — it should be a Google/Outlook/LinkedIn CSV or an iCloud .vcf with email/phone columns."}`);
      } else if (type === "contacts") {
        setResult(`✅ Imported ${imported} contacts (${data.leads_added ?? 0} now show as Personal leads), skipped ${data.skipped}. They'll get a warm insurance intro automatically.`);
      } else {
        const page = type === "bnb" ? "BnB Global" : type === "restaurants" ? "SavoryMind" : "Insurance Leads";
        const dupPart = updated ? ` (${updated} already on file were updated, not duplicated)` : "";
        setResult(`✅ Imported ${imported} new lead${imported === 1 ? "" : "s"}${dupPart}, skipped ${data.skipped_no_email} with no email. The AI writes & sends the outreach automatically, paced under your daily cap — no waiting on this screen. To start a batch now, click “Send all pending” on the ${page} page.`);
      }
    } catch (e) {
      setResult(`❌ ${e}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader title="Import Options" subtitle="Upload a real CSV list — the agents write & send personalized outreach" />
      <div className="card max-w-xl space-y-4">
        <div>
          <label className="text-sm font-medium text-gray-700">List type</label>
          <select value={type} onChange={(e) => setType(e.target.value)} className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2">
            <option value="leads">Import insurance leads (Thrust Insurance)</option>
            <option value="bnb">Import BNB leads (B&amp;B Global — consulting)</option>
            <option value="restaurants">Import SavoryMind leads (restaurants)</option>
            <option value="contacts">Import contacts (Google/iPhone → warm insurance intro)</option>
          </select>
        </div>
        <div>
          <label className="text-sm font-medium text-gray-700">Contact file (CSV or iPhone .vcf)</label>
          <input type="file" accept=".csv,.vcf,text/csv,text/vcard,text/x-vcard"
                 onChange={(e) => setFile(e.target.files?.[0] || null)}
                 className="mt-1 block w-full text-sm" />
          <p className="mt-1 text-xs text-gray-500">
            {type === "contacts"
              ? "Upload a Google/Outlook/LinkedIn CSV export OR an iPhone/iCloud vCard (.vcf — Contacts app → Export). Each contact lands in the CRM AND as a Personal insurance lead, and gets a warm insurance intro automatically (family/opt-out excluded)."
              : <>CSV or .vcf. Required column for CSV: <b>email</b>. Optional: company_name, owner_name, phone, website, linkedin, industry, segment, category.{" "}
                  <a className="text-brand hover:underline" href={`${API_URL}/import/template/${type}.csv`} target="_blank" rel="noreferrer">Download template</a></>}
          </p>
        </div>
        <button className="btn" onClick={upload} disabled={!file || busy}>
          {busy ? "Importing…" : (type === "contacts" ? "Import to CRM" : "Import leads")}
        </button>
        {result && <p className="rounded bg-gray-50 p-3 text-sm">{result}</p>}
        <p className="text-xs text-gray-400">
          Emails are written with AI and sent per your current mode (draft/send), capped per day, and never sent to placeholder addresses. The full follow-up sequence is scheduled automatically.
        </p>
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Importer /></AuthGate>;
}
