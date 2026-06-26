"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await api.login(email, password);
      router.push("/");
    } catch (e) {
      const msg = String(e);
      // Distinguish "wrong password" from "can't reach the backend" so the user
      // isn't told their password is wrong when the API is actually down.
      setError(/failed to fetch|networkerror|load failed/i.test(msg)
        ? "Can't reach the server — it may be starting up. Try again in a moment."
        : "Invalid email or password");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen w-full items-center justify-center bg-brand-dark">
      <form onSubmit={submit} className="w-full max-w-sm rounded-2xl bg-white p-8 shadow-xl">
        <h1 className="text-xl font-bold">Bruno AI Workforce</h1>
        <p className="mb-6 text-sm text-gray-500">Sign in to your dashboard</p>
        {error && <p className="mb-3 rounded bg-red-50 p-2 text-sm text-red-600">{error}</p>}
        <label className="mb-3 block">
          <span className="text-sm font-medium text-gray-700">Email</span>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2"
            required
          />
        </label>
        <label className="mb-5 block">
          <span className="text-sm font-medium text-gray-700">Password</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2"
            required
          />
        </label>
        <button className="btn w-full" disabled={loading}>
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
