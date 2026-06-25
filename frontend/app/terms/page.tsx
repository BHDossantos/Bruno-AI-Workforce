export const metadata = {
  title: "Terms of Service — Bruno AI Workforce",
  description: "Terms of Service for the Bruno AI Workforce platform.",
};

export default function TermsPage() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-12 text-gray-800">
      <h1 className="text-3xl font-bold">Terms of Service</h1>
      <p className="mt-2 text-sm text-gray-500">Last updated: June 25, 2026</p>

      <section className="prose mt-8 space-y-6 text-sm leading-relaxed">
        <div>
          <h2 className="text-lg font-semibold">1. Overview</h2>
          <p>
            Bruno AI Workforce (&quot;the Service&quot;) is a private marketing and
            productivity application operated by Bruno Dos Santos. It helps the
            account owner plan, generate, schedule, and publish their own content
            to social platforms they have personally connected, and to manage
            related business workflows. By accessing or using the Service you
            agree to these Terms of Service.
          </p>
        </div>

        <div>
          <h2 className="text-lg font-semibold">2. Accounts &amp; access</h2>
          <p>
            The Service is intended for use by its authorized owner. You are
            responsible for safeguarding your login credentials and for all
            activity under your account. You must be at least 18 years old to use
            the Service.
          </p>
        </div>

        <div>
          <h2 className="text-lg font-semibold">3. Connected platforms</h2>
          <p>
            You may connect third-party accounts (for example TikTok, Instagram,
            Facebook, and LinkedIn) using their official APIs. You authorize the
            Service to act on your behalf only within the permissions (scopes) you
            grant, and only on accounts you own or are authorized to manage. The
            Service publishes only your own content to your own connected
            accounts. You remain responsible for complying with each platform&apos;s
            terms and policies. You may disconnect any account at any time, which
            revokes the Service&apos;s access to it.
          </p>
        </div>

        <div>
          <h2 className="text-lg font-semibold">4. Acceptable use</h2>
          <p>
            You agree not to use the Service to publish unlawful, infringing,
            deceptive, or abusive content, to send unsolicited messages in
            violation of applicable law, or to violate the terms of any connected
            platform. You are solely responsible for the content you create,
            schedule, or publish through the Service.
          </p>
        </div>

        <div>
          <h2 className="text-lg font-semibold">5. AI-generated content</h2>
          <p>
            The Service uses AI to assist in generating content. You are
            responsible for reviewing AI-generated output before it is published
            and for ensuring it is accurate and appropriate.
          </p>
        </div>

        <div>
          <h2 className="text-lg font-semibold">6. Disclaimer &amp; liability</h2>
          <p>
            The Service is provided &quot;as is&quot; without warranties of any kind. To
            the maximum extent permitted by law, the operator is not liable for
            any indirect, incidental, or consequential damages arising from your
            use of the Service.
          </p>
        </div>

        <div>
          <h2 className="text-lg font-semibold">7. Changes</h2>
          <p>
            We may update these Terms from time to time. Continued use of the
            Service after changes take effect constitutes acceptance of the
            revised Terms.
          </p>
        </div>

        <div>
          <h2 className="text-lg font-semibold">8. Contact</h2>
          <p>
            Questions about these Terms can be sent to{" "}
            <a className="text-brand underline" href="mailto:brunodossantos707@gmail.com">
              brunodossantos707@gmail.com
            </a>
            .
          </p>
        </div>
      </section>

      <p className="mt-10 text-xs text-gray-400">
        <a className="underline" href="/privacy">Privacy Policy</a>
      </p>
    </main>
  );
}
