"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { API_URL, getToken } from "@/lib/api";
import { AuthGate, PageHeader } from "@/components/ui";
import { DESTINATIONS, fileProblem, importError, importReceipt, type ImportKind } from "@/lib/importReceipt";

function Importer() {
  // The dropdown value may encode a preset category as "leads|<Category>" so a
  // ready-made list type (e.g. DOT Leads) tags the whole upload with one pick.
  const [sel, setSel] = useState("leads");
  const [file, setFile] = useState<File | null>(null);
  const [category, setCategory] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ReturnType<typeof importReceipt> | null>(null);
  const inFlight = useRef(false);
  const type = sel.split("|")[0] as ImportKind;
  const presetCat = sel.includes("|") ? sel.split("|").slice(1).join("|") : "";
  const effCategory = (presetCat || category).trim();

  async function upload() {
    if (!file || inFlight.current) return;
    const invalid = fileProblem(file.name, file.size);
    if (invalid) {
      setResult({ status: "unconfirmed", message: invalid, rows: [] });
      return;
    }
    inFlight.current = true;
    setBusy(true);
    setResult(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      if (type === "leads" && effCategory) fd.append("category", effCategory);
      const token = getToken();
      const res = await fetch(`${API_URL}/import/${type}`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: fd,
      });
      const data = await res.json().catch(() => null);
      setResult(res.ok ? importReceipt(type, data) : {
        status: "unconfirmed", message: importError(res.status, data), rows: [],
      });
    } catch {
      setResult({ status: "unconfirmed", message: importError(0, null), rows: [] });
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  const destination = DESTINATIONS[type];

  return (
    <div>
      <PageHeader title="Import Options" subtitle="Upload a list and check what was saved, updated or skipped." />
      <div className="card max-w-xl space-y-4">
        <div>
          <label htmlFor="import-kind" className="text-sm font-medium text-gray-700">List type</label>
          <select id="import-kind" disabled={busy} value={sel} onChange={(e) => { setSel(e.target.value); setFile(null); setResult(null); }} className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2">
            <option value="leads">Import insurance leads (Thrust Insurance)</option>
            <option value="leads|DOT Leads MA">Import DOT Leads (MA — trucking / motor carriers)</option>
            <option value="bnb">Import BNB leads (B&amp;B Global — consulting)</option>
            <option value="restaurants">Import SavoryMind leads (restaurants)</option>
            <option value="contacts">Import contacts (Google/iPhone → CRM)</option>
          </select>
        </div>
        {type === "leads" && presetCat && (
          <p className="rounded bg-brand/5 px-3 py-2 text-sm text-gray-700">
            These will be tagged <b>{presetCat}</b> and imported as commercial call leads (phone-only is fine).
            Filter to them anytime with the <b>{presetCat}</b> category on the Call List.
          </p>
        )}
        {type === "leads" && !presetCat && (
          <div>
            <label htmlFor="import-category" className="text-sm font-medium text-gray-700">Category (optional)</label>
            <input id="import-category" disabled={busy} list="lead-categories" value={category} onChange={(e) => setCategory(e.target.value)}
                   placeholder="e.g. DOT Leads MA"
                   className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2" />
            <datalist id="lead-categories">
              <option value="DOT Leads MA" />
              <option value="EverQuote" />
              <option value="Commercial" />
              <option value="Referral Partner" />
            </datalist>
            <p className="mt-1 text-xs text-gray-500">Tags this whole upload so you can filter to it on the Call List. Rows with their own category keep it.</p>
          </div>
        )}
        <div>
          <label htmlFor="import-file" className="text-sm font-medium text-gray-700">Contact file (CSV or vCard)</label>
          <input key={sel} id="import-file" disabled={busy} type="file" accept=".csv,.vcf,text/csv,text/vcard,text/x-vcard"
                 onChange={(e) => { setFile(e.target.files?.[0] || null); setResult(null); }}
                 className="mt-1 block w-full text-sm" />
          <p className="mt-1 text-xs text-gray-500">
            {type === "contacts"
              ? "Import eligible records into Universal CRM. Only some contacts are also added as Personal insurance leads."
              : <>{type === "leads" ? "Each lead row needs an email or phone. Phone-only insurance leads are supported." : "Each row needs an email for this list type."}{" "}
                  <a className="text-brand-dark underline" href={`${API_URL}/import/template/${type}.csv`} target="_blank" rel="noreferrer">Download CSV template</a></>}
          </p>
        </div>
        <button className="btn" onClick={upload} disabled={!file || busy}>
          {busy ? "Importing…" : (type === "contacts" ? "Import to CRM" : "Import leads")}
        </button>
        {result && (
          <section className={`rounded-lg border p-3 text-sm ${result.status === "confirmed" ? "border-gray-200 bg-gray-50" : "border-amber-200 bg-amber-50"}`} aria-label="Import result">
            <p role="status" className="font-medium">{result.message}</p>
            {result.rows.length > 0 && <dl className="mt-2 space-y-1">
              {result.rows.map(row => <div key={row.label} className="flex justify-between gap-3"><dt>{row.label}</dt><dd>{row.count.toLocaleString()}</dd></div>)}
            </dl>}
            <p className="mt-2"><Link href={destination.href} className="text-brand-dark underline">{destination.label}</Link></p>
            <p className="text-xs text-gray-700">{destination.hint}</p>
          </section>
        )}
        <p className="text-xs text-gray-600">
          Lead imports can schedule follow-ups. Depending on existing automation settings, later outreach may run. This screen does not confirm any sends.
        </p>
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Importer /></AuthGate>;
}
