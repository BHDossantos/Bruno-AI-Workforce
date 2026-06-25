export const metadata = {
  title: "Privacy Policy — Bruno AI Workforce",
  description: "Privacy Policy for the Bruno AI Workforce platform.",
};

export default function PrivacyPage() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-12 text-gray-800">
      <h1 className="text-3xl font-bold">Privacy Policy</h1>
      <p className="mt-2 text-sm text-gray-500">Last updated: June 25, 2026</p>

      <section className="prose mt-8 space-y-6 text-sm leading-relaxed">
        <div>
          <h2 className="text-lg font-semibold">1. Who we are</h2>
          <p>
            Bruno AI Workforce (&quot;the Service&quot;) is a private application operated
            by Bruno Dos Santos. This policy explains what data the Service
            handles and how it is protected.
          </p>
        </div>

        <div>
          <h2 className="text-lg font-semibold">2. Information we handle</h2>
          <ul className="list-disc pl-5">
            <li>
              <strong>Account &amp; profile data:</strong> the email and login
              credentials used to access the Service.
            </li>
            <li>
              <strong>Connected-platform credentials:</strong> access tokens and
              account identifiers for social accounts you choose to connect (e.g.
              TikTok, Instagram, Facebook, LinkedIn). These are used only to read
              the basic account info you authorize and to publish your own content
              to your own accounts.
            </li>
            <li>
              <strong>Content &amp; business data:</strong> the posts, drafts,
              contacts, and records you create or import to run your workflows.
            </li>
            <li>
              <strong>Platform metrics:</strong> engagement and follower figures
              retrieved from connected platforms to show performance in the
              dashboard.
            </li>
          </ul>
        </div>

        <div>
          <h2 className="text-lg font-semibold">3. How we use it</h2>
          <p>
            Data is used solely to operate the Service for its owner: generating
            and scheduling content, publishing to your connected accounts,
            displaying analytics, and managing outreach. We do not sell your data
            or use it for advertising.
          </p>
        </div>

        <div>
          <h2 className="text-lg font-semibold">4. How tokens are stored</h2>
          <p>
            Third-party access tokens are <strong>encrypted at rest</strong> and are
            never displayed back through the interface or shared with other users.
            They are used only to make authorized API calls to the platform they
            belong to.
          </p>
        </div>

        <div>
          <h2 className="text-lg font-semibold">5. Third-party platforms</h2>
          <p>
            When you connect a platform, your use of that platform remains governed
            by its own terms and privacy policy. The Service accesses only the
            permissions (scopes) you grant and acts only on accounts you own or are
            authorized to manage.
          </p>
        </div>

        <div>
          <h2 className="text-lg font-semibold">6. Data retention &amp; deletion</h2>
          <p>
            You can disconnect any connected account at any time, which removes its
            stored credentials and revokes the Service&apos;s access. To request
            deletion of your data, contact us at the address below.
          </p>
        </div>

        <div>
          <h2 className="text-lg font-semibold">7. Security</h2>
          <p>
            We use industry-standard measures including encryption of sensitive
            credentials and access controls. No method of transmission or storage
            is completely secure, but we take reasonable steps to protect your
            information.
          </p>
        </div>

        <div>
          <h2 className="text-lg font-semibold">8. Contact</h2>
          <p>
            For privacy questions or data-deletion requests, contact{" "}
            <a className="text-brand underline" href="mailto:brunodossantos707@gmail.com">
              brunodossantos707@gmail.com
            </a>
            .
          </p>
        </div>
      </section>

      <p className="mt-10 text-xs text-gray-400">
        <a className="underline" href="/terms">Terms of Service</a>
      </p>
    </main>
  );
}
