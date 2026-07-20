"use client";

import { useState } from "react";
import { api } from "@/lib/api";

// A field definition from the backend schema (crm_profile.schema_for).
type Field = { key: string; label: string; type: string; options?: string[] };
type Section = { key: string; label: string; fields: Field[] };
type Schema = {
  module: string; module_label: string;
  core_sections: Section[]; module_sections: Section[]; lists: Section[];
};
export type CrmData = {
  lead_id?: string; module?: string; schema: Schema;
  profile: Record<string, Record<string, unknown> | Record<string, unknown>[]>;
  custom?: Record<string, string>;
};

type Values = Record<string, Record<string, unknown> | Record<string, unknown>[]>;

function Input({ field, value, onChange }: {
  field: Field; value: unknown; onChange: (v: unknown) => void;
}) {
  const v = value ?? "";
  if (field.type === "bool") {
    return (
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={!!value} onChange={(e) => onChange(e.target.checked)} />
        {field.label}
      </label>
    );
  }
  return (
    <label className="block text-xs font-medium text-gray-500">
      {field.label}
      {field.type === "select" ? (
        <select className="input mt-1 w-full" value={String(v)} onChange={(e) => onChange(e.target.value)}>
          {(field.options || []).map((o) => <option key={o} value={o}>{o || "—"}</option>)}
        </select>
      ) : field.type === "textarea" ? (
        <textarea className="input mt-1 w-full" rows={2} value={String(v)} onChange={(e) => onChange(e.target.value)} />
      ) : (
        <input className="input mt-1 w-full"
          type={field.type === "number" ? "number" : field.type === "date" ? "date" : "text"}
          value={String(v)} onChange={(e) => onChange(e.target.value)} />
      )}
    </label>
  );
}

function GroupSection({ section, values, setField }: {
  section: Section; values: Values; setField: (s: string, k: string, v: unknown) => void;
}) {
  const group = (values[section.key] as Record<string, unknown>) || {};
  return (
    <div className="card mb-3">
      <h3 className="mb-2 text-sm font-semibold">{section.label}</h3>
      <div className="grid gap-2 sm:grid-cols-2">
        {section.fields.map((f) => (
          <Input key={f.key} field={f} value={group[f.key]}
            onChange={(v) => setField(section.key, f.key, v)} />
        ))}
      </div>
    </div>
  );
}

function ListSection({ section, rows, setRows }: {
  section: Section; rows: Record<string, unknown>[]; setRows: (rows: Record<string, unknown>[]) => void;
}) {
  return (
    <div className="card mb-3">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold">{section.label}</h3>
        <button type="button" className="btn-ghost text-xs"
          onClick={() => setRows([...(rows || []), {}])}>+ Add {section.label.replace(/s$/, "")}</button>
      </div>
      {(rows || []).length === 0 && <p className="text-xs text-gray-400">None yet.</p>}
      {(rows || []).map((row, i) => (
        <div key={i} className="mb-2 rounded-lg border border-gray-100 p-2">
          <div className="mb-1 flex justify-end">
            <button type="button" className="text-xs text-gray-400 hover:text-red-600"
              onClick={() => setRows(rows.filter((_, j) => j !== i))}>Remove</button>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            {section.fields.map((f) => (
              <Input key={f.key} field={f} value={row[f.key]}
                onChange={(v) => setRows(rows.map((r, j) => j === i ? { ...r, [f.key]: v } : r))} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * Schema-driven CRM editor. In "edit" mode it PATCHes an existing lead; in
 * "create" mode it POSTs a new client. The whole form is rendered from the
 * backend schema, so new fields/modules appear here with no code change.
 */
export function CrmEditor({ data, mode, onSaved, entity = "lead" }: {
  data: CrmData; mode: "edit" | "create"; onSaved?: (id: string) => void;
  entity?: "lead" | "restaurant";
}) {
  const base = entity === "restaurant" ? "/restaurants" : "/leads";
  const idKey = entity === "restaurant" ? "restaurant_id" : "lead_id";
  const [values, setValues] = useState<Values>(() => JSON.parse(JSON.stringify(data.profile || {})));
  const [custom, setCustom] = useState<Record<string, string>>(data.custom || {});
  const [newKey, setNewKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const setField = (s: string, k: string, v: unknown) =>
    setValues((prev) => ({ ...prev, [s]: { ...(prev[s] as Record<string, unknown> || {}), [k]: v } }));
  const setRows = (s: string, rows: Record<string, unknown>[]) =>
    setValues((prev) => ({ ...prev, [s]: rows }));

  const groups = [...(data.schema.core_sections || []), ...(data.schema.module_sections || [])];

  async function save() {
    setBusy(true); setMsg("");
    try {
      if (mode === "create") {
        const body: Record<string, unknown> = { profile: values, custom };
        if (entity === "lead") body.segment = "personal";
        const r = await api.post<Record<string, string>>(`${base}/crm`, body);
        setMsg(entity === "restaurant" ? "Restaurant created." : "Client created.");
        onSaved?.(r[idKey]);
      } else {
        await api.patch(`${base}/${data.lead_id}/crm`, { profile: values, custom });
        setMsg("Saved.");
        onSaved?.(data.lead_id || "");
      }
    } catch (e) {
      setMsg(`Couldn't save: ${e instanceof Error ? e.message : "error"}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <span className="badge bg-blue-100 text-blue-700">{data.schema.module_label} module</span>
        <div className="flex items-center gap-3">
          {msg && <span className="text-xs text-gray-600">{msg}</span>}
          <button type="button" className="btn text-sm" disabled={busy} onClick={save}>
            {busy ? "Saving…" : mode === "create" ? "Create client" : "Save changes"}
          </button>
        </div>
      </div>

      {groups.map((s) => (
        <GroupSection key={s.key} section={s} values={values} setField={setField} />
      ))}
      {(data.schema.lists || []).map((s) => (
        <ListSection key={s.key} section={s}
          rows={(values[s.key] as Record<string, unknown>[]) || []}
          setRows={(rows) => setRows(s.key, rows)} />
      ))}

      {/* Custom fields — unlimited user-defined key/value pairs */}
      <div className="card mb-3">
        <h3 className="mb-2 text-sm font-semibold">Custom Fields</h3>
        {Object.entries(custom).map(([k, v]) => (
          <div key={k} className="mb-2 flex items-center gap-2">
            <span className="w-40 text-xs font-medium text-gray-500">{k}</span>
            <input className="input flex-1" value={v}
              onChange={(e) => setCustom({ ...custom, [k]: e.target.value })} />
            <button type="button" className="text-xs text-gray-400 hover:text-red-600"
              onClick={() => { const c = { ...custom }; delete c[k]; setCustom(c); }}>✕</button>
          </div>
        ))}
        <div className="mt-2 flex items-center gap-2">
          <input className="input flex-1" placeholder="New field name" value={newKey}
            onChange={(e) => setNewKey(e.target.value)} />
          <button type="button" className="btn-ghost text-xs" disabled={!newKey.trim()}
            onClick={() => { setCustom({ ...custom, [newKey.trim()]: "" }); setNewKey(""); }}>
            + Add field
          </button>
        </div>
      </div>
    </div>
  );
}
