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
      setResult(`✅ Imported ${data.imported}, sent ${data.sent}, skipped (no email) ${data.skipped_no_email}.`);
    } catch (e) {
      setResult(`❌ ${e}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader title="Import Contacts" subtitle="Upload a real CSV list — the agents write & send personalized outreach" />
      <div className="card max-w-xl space-y-4">
        <div>
          <label className="text-sm font-medium text-gray-700">List type</label>
          <select value={type} onChange={(e) => setType(e.target.value)} className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2">
            <option value="leads">Insurance leads (sent from Thrust Insurance)</option>
            <option value="restaurants">Restaurants / SavoryMind (sent from personal)</option>
          </select>
        </div>
        <div>
          <label className="text-sm font-medium text-gray-700">CSV file</label>
          <input type="file" accept=".csv" onChange={(e) => setFile(e.target.files?.[0] || null)}
                 className="mt-1 block w-full text-sm" />
          <p className="mt-1 text-xs text-gray-500">
            Required column: <b>email</b>. Optional: company_name, owner_name, phone, website, linkedin, industry, segment, category.
            {" "}
            <a className="text-brand hover:underline" href={`${API_URL}/import/template/${type}.csv`} target="_blank" rel="noreferrer">Download template</a>
          </p>
        </div>
        <button className="btn" onClick={upload} disabled={!file || busy}>
          {busy ? "Importing & sending…" : "Import & send"}
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
