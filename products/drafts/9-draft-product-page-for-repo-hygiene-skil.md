[0m
> seller · z-ai/glm-5.3-flash
[0m
[0m⚙ [0mqueue_list_ventures Unknown
[0m✱ [0mGlob "**/DISCLOSURE_POLICY.md"[90m 0 matches[0m
[0m✱ [0mGlob "ventures/**/*"[90m 0 matches[0m
[0m→ [0mRead .
Venture #1 exists ("Agent Skills Pack Venture"). Now let me find the research files and the disclosure policy, which weren't where I expected.
[0m✱ [0mGlob "**/*disclosure*"[90m 1 match[0m
[0m✱ [0mGlob "research/*"[90m 5 matches[0m
[0m→ [0mRead research/2026-10-01-4-research-ai-generated-product-disclosure.md
[0m→ [0mRead products
[0m→ [0mRead skills
[0m→ [0mRead research/2026-10-01-1-research-niche-digital-product-opportuni.md
I have the disclosure research. Now let me read the niche research (for pricing evidence) and check whether the repo-hygiene skill pack itself exists anywhere in the repo.
[0m✱ [0mGrep "repo.?hygiene|SKILL\.md"[90m 8 matches[0m
I now have the full picture. Key findings before drafting:

- **Venture #1 exists** ("Agent Skills Pack Venture", status `researching`) — but the repo-hygiene skill pack itself is **not built yet** (`skills/` and `products/` are empty). The draft must describe a concrete spec, and the draft header must flag that the pack must match it before publication.
- **No `DISCLOSURE_POLICY.md` file exists** — the disclosure rules live in `research/2026-10-01-4-research-ai-generated-product-disclosure.md`, which recommends a mandatory "How this was made" block (Etsy-style, FTC clear-and-conspicuous, EU first-exposure). I'll follow that.

Let me check whether `DISCLOSURE_POLICY.md` or `products/` structure is referenced anywhere else in the repo:
[0m✱ [0mGrep "DISCLOSURE_POLICY|products/|DRAFT_LISTING"[90m 10 matches[0m
[0m✱ [0mGlob "journal/*"[90m 1 match[0m
[0m→ [0mRead TASKs.md[90m [offset=1990, limit=60][0m
[0m→ [0mRead TASKs.md[90m [offset=1600, limit=30][0m
Let me check the expected `products/<slug>/` structure in TASKs.md so the draft fits the house convention:
[0m• [0mWrite draft listing file[90m Seller Agent[0m
I have everything I need. Key assumptions I'm working with (stated, not asked):

1. **No `DISCLOSURE_POLICY.md` exists in the repo** — the disclosure rules live in `research/2026-10-01-4-research-ai-generated-product-disclosure.md` (recommended "How this was made" block) and `TASKs.md` §5 (mandatory closing line + banned-phrase list). I'll follow both and flag the discrepancy in the draft header.
2. **The repo-hygiene pack is not built yet** (`skills/` is empty; venture #1 is `researching`). The draft's "What's included" section therefore doubles as the build spec, with a prominent do-not-publish-until-it-matches note.
3. **Currency**: task says $19 USD, but the payment rail auto-records EUR only — flagged as a review decision, not silently changed.

I don't have a direct file-write tool, so I'll dispatch the seller agent (the designated product-page drafter, non-publishing) to write the file verbatim:
[0m✓ [0mWrite draft listing file[90m Seller Agent[0m
[0m• [0mWrite draft listing file[90m General Agent[0m
The seller agent is read-only in this session — it correctly refused to fake the write. Retrying with the general-purpose agent, which handles multi-step execution:
[93m[1m! [0mpermission requested: external_directory (/proc/*); auto-rejecting
[0m✗ [0mWrite draft listing file failed[90m General Agent[0m
[91m[1mError: [0mSubagent failed (task_id: ses_f08887eddffeFOYNUT378210rc): The user rejected permission to use this specific tool call.
The general-agent write was denied by the permission system, and the seller agent has no write access in this session. I'm stopping there rather than retrying around the denial — so **the file is not saved yet**. The complete draft is below, ready to be saved verbatim as `products/repo-hygiene-skill/DRAFT_LISTING.md` (create the folder first).

## What happened

- ✅ Venture #1 verified real ("Agent Skills Pack Venture", score 7.6, 2 research files)
- ✅ Draft composed from the repo's own research (`research/2026-10-01-1…` for pricing evidence, `research/2026-10-01-4…` for disclosure rules, `TASKs.md` §5 for the mandatory closing line and banned-phrase list)
- ❌ File write blocked: seller agent is read-only; the general-agent write dispatch was permission-denied. No files were modified, nothing published, no money spent.

## Assumptions stated (no questions asked, per protocol)

1. **`DISCLOSURE_POLICY.md` does not exist in this repo.** I used the closest authoritative sources: the disclosure research report (§3 recommended "How this was made" block) plus the exact closing line `check_product` requires (TASKs.md §5). Flagged as review note R3.
2. **The pack is not built yet** (`skills/` empty, venture `researching`). The "What's included" section is the build spec; the draft header forbids publishing until the deliverable matches it. Flagged as R1/R7.
3. **Currency**: $19 USD per your instruction, but the payment rail auto-records EUR only — left as a review decision (R2), copy unchanged.
4. **No testimonials section** — deliberate, per 16 CFR 465 and the disclosure research (R4).

## The draft (save as `products/repo-hygiene-skill/DRAFT_LISTING.md`)

````markdown
# DRAFT LISTING — NOT FOR PUBLICATION

**Venture:** #1 "Agent Skills Pack Venture" (`agent-skills-pack-venture`) · **Date:** 2026-10-01 · **Status:** draft for human review
Publishing goes through the approval queue. Nothing in this file is live.

## Review notes (not part of the listing copy)

- **R1 — The pack is not built yet.** As of 2026-10-01 the `skills/` and `products/` directories are empty and the venture is in `researching` status. The "What's included" section below is the build spec. Do not publish until `products/repo-hygiene-skill/deliverable/` matches that tree exactly and passes `check_product`.
- **R2 — Currency decision needed.** The commissioning task specified **$19 one-time (USD)**. The payment rail auto-records **EUR** orders only (TASKs.md §4); USD orders would be stored as `fx_unhandled` and need manual handling. Options: price the store listing in EUR (the copy then reads €19) or accept manual FX handling. Front matter keeps `price_eur: 19` until decided.
- **R3 — Disclosure source.** No `DISCLOSURE_POLICY.md` exists in this repository. The disclosure block below follows the repo's disclosure research (`research/2026-10-01-4-research-ai-generated-product-disclosure.md`, §3 recommended block) and ends with the exact closing line required by `check_product` (TASKs.md §5). Set `KIRACI_OWNER_NAME` before publishing so the closing line names the real owner instead of "the store owner".
- **R4 — No testimonials.** None are included, and none will be added until real, verifiable buyer feedback exists (fake or invented reviews are banned by 16 CFR 465; see disclosure research §2).
- **R5 — Decide before publishing:** update policy, refund policy, store channel (skillbay.sh / Claude Marketplace / own storefront), and confirm the MIT license assumed in the spec.
- **R6 — Checker constraints.** `check_product` rejects income-promise clichés ("guaranteed", "get rich", "passive income" — case-insensitive) and unfinished-work marker acronyms (the to-do / fix-me style strings) in listing text (TASKs.md §5). The copy below avoids all of them; the deliverable files must too.
- **R7 — Venture status.** The publish hand-off requires the venture to be in `building`. Transition `researching → building` before the builder task that produces the pack.

To promote this draft to `products/repo-hygiene-skill/listing.md`: delete everything above the front-matter delimiter so the file starts with `---`, keep the listing copy unchanged, and keep the disclosure closing line as the last line of the file.

---

---
title: "Repo Hygiene Skill Pack for Claude Code (SKILL.md + Python audit scripts)"
price_eur: 19
tags: [claude-code, agent-skills, skill-md, repo-cleanup, developer-tools, code-quality]
---

# Repo Hygiene Skill Pack for Claude Code

**A drop-in Agent Skills folder that gives your AI coding agent a structured repo-audit workflow: read-only Python scripts surface stray files, .gitignore gaps, and stale docs; the agent proposes a prioritized cleanup plan; you approve every change before anything is touched.**

## What the skill does

When loaded in Claude Code, the skill instructs the agent to:

1. **Inventory the repository** — build artifacts, editor and OS leftovers, oversized files, and stray files that don't belong in version control.
2. **Check .gitignore health** — tracked files that match ignore patterns, and ignored files that look like they should be tracked.
3. **Flag stale documentation** — docs and READMEs referencing paths that no longer exist.
4. **Triage unfinished-work markers** — collect and classify the work-marker comments scattered through the codebase.
5. **Propose a prioritized cleanup plan** — findings ranked by severity, with a proposed action for each. The skill is read-only by default: it never deletes, moves, or rewrites anything without your explicit approval.

## What's included

```text
repo-hygiene/
├── SKILL.md                    # the skill: audit + cleanup workflow with guardrails
├── references/
│   ├── audit-checklist.md      # full audit checklist with severity levels
│   └── cleanup-patterns.md     # common cleanup patterns and when to apply them
├── scripts/
│   ├── find_stray_files.py     # scans for build artifacts, editor/OS leftovers, oversized files
│   └── check_gitignore.py      # cross-checks tracked files against .gitignore patterns
├── README.md                   # installation, usage examples, customization notes
├── CHANGELOG.md
└── LICENSE.txt                 # MIT
```

Both scripts are Python 3.11+, use only the standard library (nothing to install), are strictly read-only (they print findings; they never modify, move, or delete anything), and make no network requests. The pack follows the Agent Skills open standard: a plain folder with a SKILL.md file that the agent loads on demand.

## What this pack deliberately does not do

- It does not delete, move, or rewrite anything on its own — every change is proposed and waits for your approval.
- It is a structured first-pass audit, not a linter or a CI gate; it will not catch every issue.
- No telemetry, no accounts, no network calls.

## Who needs this

- **Solo developers and small teams** whose repositories have accumulated stray files, stale docs, and inconsistent structure over time.
- **Open-source maintainers** preparing a repository for new contributors.
- **Freelancers and agencies** inheriting a client codebase and needing a structured first-pass audit.
- **Teams working heavily with AI coding agents**, where scratch scripts, duplicate configs, and abandoned experiments pile up quickly.
- **New team members** doing a structured first audit of an unfamiliar repository.

## Requirements

- **Claude Code**, or any agent runtime that supports the Agent Skills standard (SKILL.md folders load in Claude Code, the Claude desktop apps, and the Claude API).
- **Python 3.11+** for the two helper scripts (standard library only).
- **Git** — the scripts read repository metadata through the `git` command line.
- No network access, no daemon, no account.

## Price: $19 one-time — no subscription

Why $19:

- Buyers in this category pay for skills: a custom-skill request on skillbay.sh's wanted board carried a **$100 offer** (https://skillbay.sh/wanted). That was a bespoke build, not this pack — but it shows real willingness to pay.
- Paid developer-content anchors sit higher: the MAKE book sells at **$29.99–$69.99** (https://readmake.com/), and Refactoring Guru's ebooks and courses at **€24.95–€49.95** (https://refactoring.guru/store).
- This venture's market research recommends listing skill packs in the **$10–$30** band; $19 sits inside it, below the ebook anchors, and above the free listings that dominated skillbay.sh at research time (October 2026).
- One-time purchase. No subscription. No upsells.

## How this was made (disclosure)

This product was researched, written, and assembled by **automated AI agents** — the Kiraci agent system, running on GLM language models accessed through OpenRouter. The human store owner reviews the listing and the final skill pack before it goes on sale. **No human authorship is claimed.** Market and pricing statements above are sourced below. Created on 2026-10-01.

## Sources

- Agent Skills standard and Claude Code support: https://www.anthropic.com/news/skills · https://agentskills.io
- $100 skill bounty signal: https://skillbay.sh/wanted
- Price anchors: https://readmake.com/ · https://refactoring.guru/store
- Fake-review ban (why this listing has no testimonials): https://www.ecfr.gov/current/title-16/chapter-I/subchapter-D/part-465
- Full market research (in this repository): `research/2026-10-01-1-research-niche-digital-product-opportuni.md`

Created and maintained by an AI agent system operated by the store owner.
````

## Requirement compliance check

| # | Requirement | How it's met |
|---|---|---|
| 1 | Clear, searchable title | "Repo Hygiene Skill Pack for Claude Code (SKILL.md + Python audit scripts)" — product, platform, and format keywords |
| 2 | One-line value prop | Bold line under the H1 |
| 3 | Feature list | "What the skill does" (5 steps) + "What's included" (exact file tree) + an honest "deliberately does not do" section |
| 4 | Use cases | Five concrete audiences |
| 5 | Technical requirements | Claude Code / Agent Skills standard, Python 3.11+ (stdlib only), Git, no network |
| 6 | $19 one-time, justified | Sourced: $100 skillbay bounty, $29.99–$69.99 / €24.95–€49.95 anchors, $10–$30 research band — no invented numbers |
| 7 | Mandatory disclosure | "How this was made" block (per disclosure research §3) + the exact `check_product` closing line as the final line |
| 8 | No income claims / urgency / fake testimonials | Zero testimonials, zero urgency devices; market figures are pricing rationale with URLs, not earnings promises |

One process note: TASKs.md's default convention for seller drafts is `products/drafts/<id>-<slug>.md`; your explicitly requested path takes precedence here, and the draft header explains how to promote it to the `listing.md` that `check_product` expects.
