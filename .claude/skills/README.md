# Marketing Skills

A library of **45 marketing [Agent Skills](https://docs.claude.com/en/docs/claude-code/skills)**
covering conversion optimization, copywriting, cold email, prospecting, SEO/AI SEO,
paid ads, ad creative, social, SMS, pricing, churn prevention, referrals, revenue
operations, customer research, PR, and more.

Because they live under `.claude/skills/`, Claude Code automatically discovers
them when working in this repo — invoke one by asking for the task (e.g. "write
landing page copy", "draft a cold email sequence", "do an SEO audit") or via its
name. They pair naturally with the Bruno AI Workforce agents (music marketing,
Instagram growth, insurance/restaurant outreach): use a skill to craft or sharpen
the messaging the agents generate.

Each skill is a folder with a `SKILL.md` (plus optional `references/` and `evals/`).

## Attribution

These skills are vendored from the **Marketing Skills** project by **Corey Haines**:

- Source: https://github.com/coreyhaines31/marketingskills
- Author: Corey Haines (https://corey.co)
- Upstream version: 2.5.1
- License: **MIT** (see [`LICENSE`](./LICENSE) — Copyright (c) 2025 Corey Haines)

Vendored unmodified for use within this repo. To update, re-copy the `skills/`
directory from the upstream repository. All credit for the skill content goes to
the original author; the MIT license terms are retained in `LICENSE`.

## Second source: awesome-claude-skills (Apache-2.0)

32 additional general-purpose skills are vendored from **ComposioHQ/awesome-claude-skills**
(e.g. `lead-research-assistant`, `content-research-writer`, `competitive-ads-extractor`,
`twitter-algorithm-optimizer`, `brand-guidelines`, `tailored-resume-generator`,
`docx`/`pdf`/`pptx`/`xlsx`, and more).

- Source: https://github.com/ComposioHQ/awesome-claude-skills
- License: **Apache-2.0** for the collection; several skills include their own
  `LICENSE.txt` (preserved inside each skill folder) and those terms govern them.
- The upstream repo's **832 Composio SaaS-connector automation skills** were *not*
  placed here (they would flood skill discovery); they're vendored for reference
  under [`vendor/awesome-claude-skills/`](../../vendor/awesome-claude-skills/).
  Promote any you want into this directory to make them discoverable.
