"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { AuthGate, PageHeader } from "@/components/ui";

type Task = { id: string; title: string; status: string; owner: string | null; due_date: string | null };
type Project = {
  id: string; name: string; business: string; client_name: string | null; description: string | null;
  owner: string | null; status: string; health: string; start_date: string | null; due_date: string | null;
  task_count: number; tasks_done: number; progress: number; tasks?: Task[];
};
type Summary = { total: number; active: number; at_risk: number; overdue: number; done: number };

const HEALTH: Record<string, { label: string; cls: string }> = {
  on_track: { label: "On track", cls: "bg-emerald-100 text-emerald-700" },
  at_risk: { label: "At risk", cls: "bg-amber-100 text-amber-700" },
  overdue: { label: "Overdue", cls: "bg-red-100 text-red-700" },
  done: { label: "Done", cls: "bg-gray-100 text-gray-500" },
};
const NEXT: Record<string, string> = { Todo: "Doing", Doing: "Done", Done: "Todo" };
const TASK_CLS: Record<string, string> = {
  Todo: "bg-gray-100 text-gray-600", Doing: "bg-sky-100 text-sky-700", Done: "bg-emerald-100 text-emerald-700 line-through",
};

function Projects() {
  const [list, setList] = useState<Project[]>([]);
  const [sum, setSum] = useState<Summary | null>(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", client_name: "", business: "insurance", owner: "", due_date: "", description: "" });
  const [expanded, setExpanded] = useState<string | null>(null);
  const [detail, setDetail] = useState<Project | null>(null);
  const [newTask, setNewTask] = useState("");

  async function load() {
    const [p, s] = await Promise.all([
      api.get<Project[]>("/projects"),
      api.get<Summary>("/projects/summary"),
    ]);
    setList(p); setSum(s);
  }
  useEffect(() => { load().catch(() => {}); }, []);

  async function create() {
    if (!form.name.trim()) { alert("Project name is required."); return; }
    await api.post("/projects", form);
    setOpen(false);
    setForm({ name: "", client_name: "", business: "insurance", owner: "", due_date: "", description: "" });
    await load();
  }
  async function expand(id: string) {
    if (expanded === id) { setExpanded(null); setDetail(null); return; }
    setExpanded(id);
    setDetail(await api.get<Project>(`/projects/${id}`));
  }
  async function refreshDetail(id: string) {
    setDetail(await api.get<Project>(`/projects/${id}`));
    await load();
  }
  async function addTask(id: string) {
    if (!newTask.trim()) return;
    await api.post(`/projects/${id}/tasks`, { title: newTask });
    setNewTask("");
    await refreshDetail(id);
  }
  async function cycleTask(pid: string, t: Task) {
    await api.post(`/projects/tasks/${t.id}/status`, { status: NEXT[t.status] });
    await refreshDetail(pid);
  }
  async function delTask(pid: string, tid: string) {
    await api.del(`/projects/tasks/${tid}`);
    await refreshDetail(pid);
  }
  async function setStatus(id: string, status: string) {
    await api.patch(`/projects/${id}`, { status });
    await load();
    if (expanded === id) setDetail(await api.get<Project>(`/projects/${id}`));
  }
  async function remove(id: string) {
    if (!confirm("Delete this project and its tasks?")) return;
    await api.del(`/projects/${id}`);
    if (expanded === id) { setExpanded(null); setDetail(null); }
    await load();
  }

  const stat = (label: string, val: string, tone = "") => (
    <div className="card"><div className={`text-2xl font-bold ${tone}`}>{val}</div><div className="text-xs uppercase text-gray-400">{label}</div></div>
  );

  return (
    <div>
      <PageHeader
        title="Projects & Delivery"
        subtitle="Track client engagements end-to-end — who owns them, what's due, and whether delivery is on track."
        action={<button className="btn" onClick={() => setOpen((v) => !v)}>{open ? "Close" : "+ New project"}</button>}
      />

      {sum && (
        <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {stat("Active", String(sum.active))}
          {stat("At risk", String(sum.at_risk), sum.at_risk > 0 ? "text-amber-600" : "")}
          {stat("Overdue", String(sum.overdue), sum.overdue > 0 ? "text-red-600" : "")}
          {stat("Delivered", String(sum.done), "text-emerald-600")}
        </div>
      )}

      {open && (
        <div className="card mb-4 space-y-3">
          <div className="grid gap-2 sm:grid-cols-2">
            <input className="input" placeholder="Project name *" value={form.name}
                   onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <input className="input" placeholder="Client" value={form.client_name}
                   onChange={(e) => setForm({ ...form, client_name: e.target.value })} />
            <input className="input" placeholder="Owner" value={form.owner}
                   onChange={(e) => setForm({ ...form, owner: e.target.value })} />
            <label className="flex items-center gap-2 text-sm text-gray-500">
              Due<input type="date" className="input flex-1" value={form.due_date}
                        onChange={(e) => setForm({ ...form, due_date: e.target.value })} /></label>
            <select className="input" value={form.business}
                    onChange={(e) => setForm({ ...form, business: e.target.value })}>
              <option value="insurance">Insurance</option>
              <option value="bnbglobal">B&B Global</option>
              <option value="savorymind">SavoryMind</option>
              <option value="music">Music</option>
              <option value="personal">Personal</option>
            </select>
          </div>
          <textarea className="input w-full" rows={2} placeholder="Description (optional)" value={form.description}
                    onChange={(e) => setForm({ ...form, description: e.target.value })} />
          <div className="text-right"><button className="btn" onClick={create}>Create project</button></div>
        </div>
      )}

      <div className="space-y-2">
        {list.length === 0 && <div className="card text-center text-gray-400">No projects yet. Create your first one above.</div>}
        {list.map((p) => {
          const h = HEALTH[p.health] || HEALTH.on_track;
          return (
            <div key={p.id} className="card">
              <div className="flex cursor-pointer items-center justify-between gap-3" onClick={() => expand(p.id)}>
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-semibold text-gray-900">{p.name}</span>
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${h.cls}`}>{h.label}</span>
                  </div>
                  <div className="text-xs text-gray-400">
                    {p.client_name || p.business}{p.owner ? ` · ${p.owner}` : ""}{p.due_date ? ` · due ${p.due_date}` : ""}
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <div className="w-28">
                    <div className="h-1.5 w-full rounded-full bg-gray-100">
                      <div className="h-1.5 rounded-full bg-brand" style={{ width: `${Math.round(p.progress * 100)}%` }} />
                    </div>
                    <div className="mt-0.5 text-right text-[11px] text-gray-400">{p.tasks_done}/{p.task_count}</div>
                  </div>
                  <span className="text-gray-300">{expanded === p.id ? "▲" : "▼"}</span>
                </div>
              </div>

              {expanded === p.id && detail && (
                <div className="mt-3 border-t pt-3">
                  {detail.description && <p className="mb-2 text-sm text-gray-600">{detail.description}</p>}
                  <div className="mb-3 flex flex-wrap gap-2 text-xs">
                    {["Planned", "Active", "Blocked", "Done", "Cancelled"].map((s) => (
                      <button key={s} onClick={() => setStatus(p.id, s)}
                              className={`rounded-full px-2 py-0.5 ${detail.status === s ? "bg-brand text-white" : "bg-gray-100 text-gray-600"}`}>{s}</button>
                    ))}
                    <button onClick={() => remove(p.id)} className="ml-auto text-gray-300 hover:text-red-500">Delete project</button>
                  </div>
                  <ul className="space-y-1">
                    {(detail.tasks || []).map((t) => (
                      <li key={t.id} className="flex items-center gap-2 text-sm">
                        <button onClick={() => cycleTask(p.id, t)} className={`rounded px-2 py-0.5 text-xs ${TASK_CLS[t.status]}`}>{t.status}</button>
                        <span className={t.status === "Done" ? "text-gray-400 line-through" : ""}>{t.title}</span>
                        {t.owner && <span className="text-xs text-gray-400">· {t.owner}</span>}
                        {t.due_date && <span className="text-xs text-gray-400">· {t.due_date}</span>}
                        <button onClick={() => delTask(p.id, t.id)} className="ml-auto text-gray-300 hover:text-red-500">✕</button>
                      </li>
                    ))}
                    {(detail.tasks || []).length === 0 && <li className="text-sm text-gray-400">No tasks yet.</li>}
                  </ul>
                  <div className="mt-2 flex gap-2">
                    <input className="input flex-1" placeholder="Add a deliverable…" value={newTask}
                           onChange={(e) => setNewTask(e.target.value)}
                           onKeyDown={(e) => { if (e.key === "Enter") addTask(p.id); }} />
                    <button className="btn" onClick={() => addTask(p.id)}>Add</button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Projects /></AuthGate>;
}
