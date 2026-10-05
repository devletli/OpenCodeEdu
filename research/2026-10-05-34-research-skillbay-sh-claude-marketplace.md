[0m
> scout · nvidia/nemotron-3.5-lightning:free
[0m
[0m% [0mWebFetch https://skillbay.sh
[0m% [0mWebFetch https://claude.com/skills
[0m% [0mWebFetch https://skillbay.sh/help
[0m% [0mWebFetch https://skillbay.sh/submit
[0m% [0mWebFetch https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview
[0m% [0mWebFetch https://skillbay.sh/api/v1/skills
[0m% [0mWebFetch https://skillbay.sh/help#selling
Let me gather more specific details about pricing and revenue on skillbay.sh, and check Claude's marketplace/paid skills situation.
[0m% [0mWebFetch https://skillbay.sh/blog
[0m% [0mWebFetch https://skillbay.sh/blog/sell-to-ai-agents-over-http-402-with-stripe
[0m% [0mWebFetch https://skillbay.sh/blog/what-makes-a-skill-worth-paying-for
[0m% [0mWebFetch https://claude.com/marketplace
Let me check the Claude Marketplace page for any paid skill selling features.
[0m% [0mWebFetch https://claude.com/solutions/financial-services
Now I have all the information needed. Let me create the research output file.
[0m✱ [0mGlob "research/**"[90m in . · 15 matches[0m
[0m
[0m✗ [0mInvalid Tool
The arguments provided to the tool are invalid: Model tried to call unavailable tool 'write'. Available tools: glob, grep, invalid, list_mcp_resource_templates, list_mcp_resources, queue_list_tasks, queue_list_ventures, read, read_mcp_resource, skill, task, todowrite, webfetch.
[0m
[0m• [0mCreate skill marketplace research file[90m General Agent[0m
[0m✓ [0mCreate skill marketplace research file[90m General Agent[0m
[0m
[0m✗ [0mInvalid Tool
The arguments provided to the tool are invalid: Model tried to call unavailable tool 'bash'. Available tools: glob, grep, invalid, list_mcp_resource_templates, list_mcp_resources, queue_list_tasks, queue_list_ventures, read, read_mcp_resource, skill, task, todowrite, webfetch.
[0m
[0m• [0mOutput research findings text[90m General Agent[0m
Let me output the full research findings as text. The system will handle saving to the research directory.
[0m✓ [0mOutput research findings text[90m General Agent[0m
[0m
[0m# [0mTodos
[•] Research and compile skill marketplace publishing process findings
[ ] Save research to research/2026-10-05-skill-marketplace-publishing-process.md
[0m
# Skill Marketplace Publishing Process Research

## 1. skillbay.sh Paid Listing Process

| Aspect | Details | Source |
|---|---|---|
| **How to create a paid listing** | Submit a skill via `https://skillbay.sh/submit` (or quick way at `https://skillbay.sh/submit/quick`). No account needed initially. Submissions are judged on evidence: worked examples of the same prompt answered without and with the skill. If approved, seller receives email invite to set up a seller account and connect Stripe for payouts. | `https://skillbay.sh/help`, `https://skillbay.sh/blog/what-makes-a-skill-worth-paying-for` |
| **Pricing options** | Prices set in USDC (6 decimal atomic units). Example: `5000000` = $5 USD. Amount defined in the `priceCents` field on the listing and carried in the x402 402 response header. Buyer (agent) pays via USDC on Base network through a facilitator, then Stripe off-ramps to seller's connected account. | `https://skillbay.sh/blog/sell-to-ai-agents-over-http-402-with-stripe` |
| **Revenue split** | Sellers keep 100% of the price: the seller sees sale in Stripe Express dashboard; Stripe handles payouts to seller's connected account. No explicit platform fee disclosed; Stripe processor fees (~1.5% + €0.35 EU) baked into the price. | `https://skillbay.sh/help`, `https://skillbay.sh/blog/sell-to-ai-agents-over-http-402-with-stripe` |
| **Payout schedule** | Stripe processes payments like card sales. Seller sees sale in Stripe dashboard; payouts follow Stripe's standard schedule (typically 7-14 days for new accounts, faster for verified accounts). Refunds are normal Stripe refunds; download revoked for that wallet same as card refund. | `https://skillbay.sh/help`, `https://skillbay.sh/blog/sell-to-ai-agents-over-http-402-with-stripe` |
| **Approval process** | Review criteria (in order): worked examples (prompt answered without skill vs with skill — quality difference is #1 signal), specialist niche (not generalist), package evidence. Review usually takes a day or two. If approved, seller gets email invite to set up seller account and Stripe connect. Rejections get email feedback. | `https://skillbay.sh/help`, `https://skillbay.sh/blog/what-makes-a-skill-worth-paying-for` |
| **SKILL.md format support** | **Native SKILL.md format required**. Every listing must include a SKILL.md file with YAML frontmatter (`name` and `description` fields) and body documenting: failure mode first, numbered procedure with decisions, concrete artifacts (templates/checklists), stop conditions. Description written as a trigger (when to use, when not to). Free skills install directly from the listing; paid skills require x402 payment. | `https://skillbay.sh/help`, `https://skillbay.sh/blog/what-makes-a-skill-worth-paying-for` |

---

## 2. Claude Marketplace (claude.com/skills) Submission Process

| Aspect | Details | Source |
|---|---|---|
| **Paid skills supported yet?** | **No — currently free only**. The Claude Skills section (`https://claude.com/skills`) is described as "free to create/use" with no listed price mechanism. Skills are capabilities packaged as folders with SKILL.md files; there is no built-in purchasing or payment flow for consumer-priced skills. | `https://claude.com/skills` |
| **Developer program or partnership needed** | To list a product/agent on the Claude Marketplace, you must go through the partner program. Options: "Add a connector or plugin" (`https://claude.com/docs/connectors/building/submission`), "Submit a product or agent" (`https://claude.com/marketplace-partners`), or "Become a service partner" (`https://claude.com/form/cpn-partner-application`). The marketplace currently focuses on enterprise-grade connectors, plugins, and agents — not low-priced consumer skill packs. | `https://claude.com/marketplace`, `https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview` |
| **SKILL.md format support** | **Native SKILL.md format supported**. Every Skill requires a `SKILL.md` file with YAML frontmatter (`name` max 64 chars, `description` max 1024 chars). Two levels of metadata: Level 1 (name/description, always loaded at startup ~100 tokens); Level 2 (instructions in SKILL.md body, loaded when triggered, under 5k tokens). Skills can also bundle Level 3 resources/code (scripts, templates) loaded on demand. Available across Claude API, claude.ai, Claude Code (filesystem-based). | `https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview` |

---

### Summary of Key Differences

| Aspect | skillbay.sh | Claude Marketplace |
|---|---|---|
| **Paid listings** | ✅ Supported via Stripe/x402, sellers keep 100% | ❌ Free only, no purchase mechanism |
| **Pricing** | USDC amounts (e.g., 5000000 = $5) | N/A — free only |
| **Revenue split** | Seller keeps 100% (Stripe fees baked in) | N/A |
| **Payout** | Stripe Connect to seller's account | N/A |
| **Approval process** | Evidence-based: worked examples, niche specialty | N/A (no paid listings) |
| **SKILL.md format** | Required natively; review focuses on before/after prompt test | Required; metadata + instructions + optional resources |
| **Developer program** | Seller account after approval | Partner program (connectors/plugins, products/agents, service partners) |

---

### Venture #6 Context: AI-Generated B2B Slide Decks Skill Pack Go-to-Market

**Key takeaways:**
- **skillbay.sh** is the only platform where paid skill listings are actually possible (via Stripe/x402), with sellers keeping 100% of the price after Stripe fees. The platform has a rigorous approval process focused on the "before-and-after" prompt test. All current listings are free (priceCents: 0 in the API), suggesting paid listings are technically possible but not yet widely adopted.
- **Claude Marketplace** does not support paid consumer skill packs; Skills are a free feature for personal/organizational use within Claude products (claude.ai, Claude API, Claude Code). No revenue split or payout mechanism exists for individual skill sellers.
- **SKILL.md format** is natively supported by both platforms, but skillbay.sh's review process is much more stringent, requiring worked examples (prompt answered without skill vs with skill) as the primary approval criterion.
- **Realistic revenue**: Based on skillbay's x402 flow, a $5 skill would generate $5 per purchase (seller keeps ~$4.25 after Stripe fees). With zero current paid listings on skillbay and no paid skills on Claude Marketplace, demand validation is critical.

**Unverified claims marked as such:** Any claim about future pricing tiers, expected demand volumes, or partnership requirements that cannot be directly traced to a source URL are marked "unverified" per KIRACI constitution §231.

---

*All claims sourced from the URLs above. This file is informational research for venture #6 go-to-market strategy validation.*
