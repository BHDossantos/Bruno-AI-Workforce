export const metadata = {
  title: "User Data Deletion — Bruno AI Workforce",
  description: "How to request deletion of your data from the Bruno AI Workforce platform.",
};

export default function DataDeletionPage() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-12 text-gray-800">
      <h1 className="text-3xl font-bold">User Data Deletion</h1>
      <p className="mt-2 text-sm text-gray-500">Last updated: July 10, 2026</p>

      <section className="prose mt-8 space-y-6 text-sm leading-relaxed">
        <div>
          <p>
            Bruno AI Workforce (&quot;the Service&quot;) lets you delete the data it holds
            about you, including any information obtained through connected platforms
            such as Facebook and Instagram. This page explains how.
          </p>
        </div>

        <div>
          <h2 className="text-lg font-semibold">1. Disconnect a platform (instant)</h2>
          <p>
            In the app, go to <strong>Setup &amp; System → Connections</strong> and
            disconnect any linked account (e.g. Facebook, Instagram, LinkedIn, TikTok).
            Disconnecting immediately removes that platform&apos;s stored access tokens
            and revokes the Service&apos;s access to it.
          </p>
        </div>

        <div>
          <h2 className="text-lg font-semibold">2. Request full data deletion</h2>
          <p>
            To have all of your data deleted, email{" "}
            <a className="text-brand underline" href="mailto:brunodossantos707@gmail.com?subject=Data%20Deletion%20Request">
              brunodossantos707@gmail.com
            </a>{" "}
            with the subject line <strong>&quot;Data Deletion Request&quot;</strong> from the
            email associated with your account. Please include the connected account(s)
            you want removed so we can locate your records.
          </p>
        </div>

        <div>
          <h2 className="text-lg font-semibold">3. What gets deleted</h2>
          <ul className="list-disc pl-5">
            <li>Account &amp; profile data and login credentials.</li>
            <li>Access tokens and identifiers for any connected platforms.</li>
            <li>
              Content, contacts, messages, and records created or imported under your
              account, including data retrieved from Facebook or Instagram.
            </li>
          </ul>
        </div>

        <div>
          <h2 className="text-lg font-semibold">4. Timeframe</h2>
          <p>
            We confirm receipt within <strong>7 days</strong> and permanently delete the
            data within <strong>30 days</strong> of the request, except where we are
            required to retain limited records to comply with the law.
          </p>
        </div>

        <div>
          <h2 className="text-lg font-semibold">5. Contact</h2>
          <p>
            Questions about deletion or your data? Contact{" "}
            <a className="text-brand underline" href="mailto:brunodossantos707@gmail.com">
              brunodossantos707@gmail.com
            </a>
            .
          </p>
        </div>
      </section>

      <p className="mt-10 text-xs text-gray-400">
        <a className="underline" href="/privacy">Privacy Policy</a>
        {" · "}
        <a className="underline" href="/terms">Terms of Service</a>
      </p>
    </main>
  );
}
