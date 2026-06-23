"use client";

import { api } from "@/lib/api";
import { AuthGate, Expandable, PageHeader, StatusBadge, useFetch } from "@/components/ui";

type Job = {
  id: string;
  title: string;
  company: string;
  location: string;
  remote: boolean;
  salary_min: number | null;
  salary_max: number | null;
  source: string;
  url: string;
  score: number;
  resume_match: string | null;
  cover_letter: string | null;
  recruiter_msg: string | null;
  hiring_msg: string | null;
};

function Jobs() {
  const { data, loading } = useFetch<Job[]>(() => api.get<Job[]>("/jobs?limit=100"));
  return (
    <div>
      <PageHeader title="Jobs" subtitle="Scored executive opportunities with application artifacts" />
      {loading && <p className="text-gray-400">Loading…</p>}
      <div className="card overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr>
              <th className="th">Score</th>
              <th className="th">Title</th>
              <th className="th">Company</th>
              <th className="th">Location</th>
              <th className="th">Salary</th>
              <th className="th">Source</th>
              <th className="th">Artifacts</th>
            </tr>
          </thead>
          <tbody>
            {(data || []).map((j) => (
              <tr key={j.id} className="border-t border-gray-100">
                <td className="td">
                  <span className="badge bg-brand/10 text-brand-dark">{j.score}</span>
                </td>
                <td className="td font-medium">
                  <a href={j.url} target="_blank" className="hover:underline">{j.title}</a>
                  {j.remote && <span className="ml-2 badge bg-green-100 text-green-700">Remote</span>}
                </td>
                <td className="td">{j.company}</td>
                <td className="td">{j.location}</td>
                <td className="td">{j.salary_min ? `$${(j.salary_min / 1000).toFixed(0)}k+` : "—"}</td>
                <td className="td capitalize">{j.source}</td>
                <td className="td space-y-1">
                  <Expandable label="Resume match" text={j.resume_match} />
                  <Expandable label="Cover letter" text={j.cover_letter} />
                  <Expandable label="Recruiter msg" text={j.recruiter_msg} />
                  <Expandable label="Hiring msg" text={j.hiring_msg} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function Page() {
  return <AuthGate><Jobs /></AuthGate>;
}
