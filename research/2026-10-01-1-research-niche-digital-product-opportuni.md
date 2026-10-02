[0m
> scout · z-ai/glm-5.3-flash
[0m
[0m⚙ [0mqueue_list_ventures Unknown
[0m⚙ [0mqueue_list_tasks {"limit":10}
I'm on task #1 (niche digital product research). No ventures exist yet, so this will feed future venture creation. Let me start with marketplace scans across the three categories.
[0m✗ [0mWebFetch https://www.lemonsqueezy.com/marketplace failed
[91m[1mError: [0mStatusCode: non 2xx status code (404 GET https://www.lemonsqueezy.com/marketplace)
[0m% [0mWebFetch https://gumroad.com/discover?query=prompt%20pack
[0m% [0mWebFetch https://gumroad.com/discover?query=python
Gumroad's discover page is JS-rendered (no content returned) and Lemon Squeezy's marketplace URL 404s. Let me try alternative routes: search engines and known marketplaces like PromptBase.
[0m% [0mWebFetch https://www.lemonsqueezy.com/
[0m% [0mWebFetch https://html.duckduckgo.com/html/?q=site%3Agumroad.com+prompt+pack+chatgpt
[0m✗ [0mWebFetch https://promptbase.com/ failed
[91m[1mError: [0mStatusCode: non 2xx status code (403 GET https://promptbase.com/)
Key finding already: Lemon Squeezy no longer operates a public marketplace — it's now purely a payments platform (Stripe-owned). Now let me find actual product/sales evidence. Gumroad discover is JS-rendered, so I'll try search engines and known product pages.
[0m% [0mWebFetch https://www.bing.com/search?q=gumroad+best+selling+prompt+pack+chatgpt+prompts
[0m% [0mWebFetch https://www.bing.com/search?q=notion+template+creator+income+report+sales+reddit
Bing works. Now I'll use targeted `site:` queries to find actual product pages, then fetch those pages for sales/ratings evidence.
[0m% [0mWebFetch https://www.bing.com/search?q=site%3Agumroad.com%2Fl+%22cheat+sheet%22+developer
[0m% [0mWebFetch https://www.bing.com/search?q=site%3Agumroad.com%2Fl+prompts+chatgpt
Bing's `site:` operator is unreliable here. Better approach: fetch known seller storefronts and marketplaces directly — Gumroad product/storefront pages are server-rendered and show ratings counts.
[0m% [0mWebFetch https://godofprompt.ai/
[0m% [0mWebFetch https://easlo.gumroad.com/
God of Prompt gives solid prompt-pack evidence ($20 starter pack, 20k+ customers claim). Now let me hit other verifiable sellers and marketplaces: Notion templates (Thomas Frank), dev boilerplates (ShipFast), and educational ebooks (Refactoring Guru).
[0m% [0mWebFetch https://shipfa.st/
[0m% [0mWebFetch https://thomasjfrank.com/
[0m✗ [0mWebFetch https://refactoring.guru/buy failed
[91m[1mError: [0mStatusCode: non 2xx status code (404 GET https://refactoring.guru/buy)
[0m% [0mWebFetch https://thomasjfrank.com/brain/
Strong evidence so far: ShipFast ($199–249 boilerplate, 8,427 customers claimed) and Thomas Frank's Notion template business. Let me get specific prices and more categories.
[0m% [0mWebFetch https://refactoring.guru/
[0m% [0mWebFetch https://readmake.com/
Great data: MAKE book shows a live sales counter (32,116 copies / $953,880) and now ships as SKILL.md/MCP for AI agents — a notable trend. Let me get Refactoring Guru's store pricing, test Etsy access, and check Python/Excel template sellers.
[0m✗ [0mWebFetch https://www.etsy.com/search?q=chatgpt+prompt+pack failed
[91m[1mError: [0mStatusCode: non 2xx status code (403 GET https://www.etsy.com/search?q=chatgpt+prompt+pack)
[0m% [0mWebFetch https://refactoring.guru/store
[0m% [0mWebFetch https://pythonmorsels.com/
Refactoring Guru pricing captured (€24.95–€49.95). Etsy blocks direct access (403). Let me get Python Morsels pricing, try Mojeek as an alternative search engine for Gumroad products, and check the Prototion Notion marketplace.
[0m% [0mWebFetch https://www.mojeek.com/search?q=gumroad+%22prompt+pack%22+bestseller
[0m% [0mWebFetch https://pythonmorsels.com/pricing/
[0m% [0mWebFetch https://prototion.com/
Python Morsels pricing captured ($10–20/mo). Prototion shows a real Notion marketplace with 113k+ reviews and realistic small-seller data. Now let me try Brave search for Gumroad products, Bing snippets for Etsy evidence, and old.reddit for demand signals.
[0m% [0mWebFetch https://www.bing.com/search?q=etsy+chatgpt+prompts+digital+download+%22out+of+5+stars%22
[0m✗ [0mWebFetch https://search.brave.com/search?q=gumroad+%22prompt+pack%22+chatgpt failed
[91m[1mError: [0mStatusCode: non 2xx status code (429 GET https://search.brave.com/search?q=gumroad+%22prompt+pack%22+chatgpt)
Bing snippets aren't yielding Etsy listing data. Let me test a Gumroad storefront directly, try PromptBase through a reader proxy, and check an Excel template business.
[0m✗ [0mWebFetch https://www.someka.net/ failed
[91m[1mError: [0mStatusCode: non 2xx status code (403 GET https://www.someka.net/)
[0m% [0mWebFetch https://dvassallo.gumroad.com/
[0m% [0mWebFetch https://r.jina.ai/https://promptbase.com/
Gumroad storefronts are JS-rendered too. Let me try Gumroad's internal search endpoint, Etsy via the jina reader proxy, and old.reddit for demand signals.
[0m✗ [0mWebFetch https://gumroad.com/discover/search?query=prompt%20pack failed
[91m[1mError: [0mStatusCode: non 2xx status code (404 GET https://gumroad.com/discover/search?query=prompt%20pack)
[0m% [0mWebFetch https://old.reddit.com/r/SideProject/search?q=prompt+pack&restrict_sr=on
[0m% [0mWebFetch https://r.jina.ai/https://www.etsy.com/search?q=chatgpt+prompts
Direct routes are mostly blocked. Let me pivot to server-rendered marketplaces that publish sales counts: Envato's CodeCanyon (Python scripts), Notion's official template gallery, and one more Bing attempt at Gumroad product URLs.
[0m% [0mWebFetch https://www.notion.com/templates
[0m% [0mWebFetch https://www.bing.com/search?q=%22gumroad.com%2Fl%22+prompt+pack
[0m% [0mWebFetch https://codecanyon.net/search/python
Two strong finds: CodeCanyon shows Python scripts rarely exceed "Medium" sales (no High/Top Sellers), and Notion's official marketplace has 30,000+ templates including a new "AI Skills" category (507 templates). Now let me get Gumroad platform-scale data from Wikipedia, Hacker News demand signals via its API, and ByteByteGo pricing.
[0m% [0mWebFetch https://bytebytego.com/
[0m% [0mWebFetch https://en.wikipedia.org/wiki/Gumroad
[0m% [0mWebFetch https://hn.algolia.com/api/v1/search?query=%22prompt%20pack%22&tags=story&hitsPerPage=20
HN's Algolia API works — found a Feb 2026 Show HN where an AI agent built a Gumroad store with a prompt pack lead magnet. ByteByteGo shows 5M+ learners for technical content. Let me mine HN for Notion template and Agent Skills signals, and test Creative Market for Excel templates.
[0m% [0mWebFetch https://hn.algolia.com/api/v1/search?query=%22notion%20template%22&tags=story&hitsPerPage=15&numericFilters=points%3E50
[0m% [0mWebFetch https://hn.algolia.com/api/v1/search?query=%22agent%20skills%22&tags=story&hitsPerPage=15
[0m% [0mWebFetch https://creativemarket.com/search?q=excel%20template
[0m% [0mWebFetch https://hn.algolia.com/api/v1/search?query=gumroad&tags=story&numericFilters=points%3E100&hitsPerPage=15
Major signal: "Agent Skills" is a hot emerging category (423 HN stories; a marketplace for paid skills just launched; buyers explicitly asking to buy skills). Creative Market shows Excel templates at $9–14. Let me find Gumroad success stories via HN, PromptBase scale data, and check the VS Code paid-extension situation.
[0m% [0mWebFetch https://www.bing.com/search?q=PromptBase+marketplace+AI+prompts+how+it+works+price
Gold nugget: an iOS ebook on Gumroad made $124k in year 1 (1,534 copies) per its author's HN post. Bing is unreliable for PromptBase — I'll mark it unverified. Final gap-filling: test a real Gumroad product page (SSR?), check the new paid-skills marketplace skillbay.sh, and scan HN for cheat-sheet demand.
[0m% [0mWebFetch https://learnbyexample.gumroad.com/l/vim_reference_guide
[0m% [0mWebFetch https://hn.algolia.com/api/v1/search?query=%22cheat%20sheet%22&tags=story&numericFilters=points%3E100&hitsPerPage=10
[0m% [0mWebFetch https://skillbay.sh/
skillbay.sh exists but all listings are currently free — early-stage market. Cheat sheets get huge HN engagement (Claude Code Cheat Sheet: 699 points) but are mostly free. Two final checks: the "skills wanted" demand board and Anthropic's official Agent Skills announcement.
[0m% [0mWebFetch https://www.anthropic.com/news/skills
[0m% [0mWebFetch https://skillbay.sh/wanted
Research complete. Here is the structured report.

---

# Research Report: Niche Digital Product Opportunities for an AI-Agent-Built Product System

**Date:** 2026-10-01 · **Researcher:** scout (task #1) · **Method:** direct fetches of seller pages, marketplaces, and public APIs (HN Algolia). Access-blocked sources are listed in the limitations section; anything not directly verified is marked **UNVERIFIED**.

## Access limitations (what could NOT be verified directly)

- **Gumroad**: discover/search pages and storefronts are JavaScript-rendered; product pages returned no content to a bot. No Gumroad sales counts could be read directly. (https://gumroad.com/discover?query=prompt%20pack — title only)
- **Etsy**: 403 Forbidden on search and legal pages. (https://www.etsy.com/search?q=chatgpt+prompt+pack)
- **PromptBase**: 403 via direct fetch and via reader proxy. Scale/price data **UNVERIFIED**. (https://promptbase.com/)
- **Reddit**: bot-blocked. (https://old.reddit.com/r/SideProject/search?q=prompt+pack)
- **Lemon Squeezy**: no longer operates a public marketplace — the site is now purely a payments/MoR platform ("Sold through Link, LLC f/k/a Lemon Squeezy LLC"), so it is a sales channel, not a discovery channel. (https://www.lemonsqueezy.com/)
- Bing search results were unreliable/localized; used only where noted.

---

## Category 1 — Prompt packs & AI tools

### 1a. Generic prompt packs: real but saturated, revenue concentrated in brands
- **God of Prompt** sells prompt libraries/bundles: "AI Starter Pack" at **$20** (crossed out from $120), claims "Trusted by 20,000+ entrepreneurs & marketers", 7,100+ prompts, 39 products, 100,000+ newsletter subscribers. All figures are **self-reported marketing claims**. (https://godofprompt.ai/)
- Free prompt libraries are abundant (e.g., PromptBase advertises "4,500+ Free AI Prompts" per its indexed page title; OpenPromptLib, YouMind position as free libraries). (https://promptbase.com/free-prompts — via Bing-indexed snippet; https://openpromptlib.com/; https://youmind.com/prompts)
- **Competition: SATURATED.** Free substitutes + brand-dominated paid market. An AI agent can produce these, so differentiation is near zero.
- Direct evidence of commoditization: a Feb 2026 "Show HN" post describes an autonomous AI agent that "set up Gumroad, created a free prompt pack as a lead magnet" within 24 hours — prompt packs are already default AI-agent output. (HN Algolia API, story 47066827: https://hn.algolia.com/api/v1/search?query=%22prompt%20pack%22; site: https://fromearendel.com)

### 1b. Agent Skills (SKILL.md packs): the emerging, under-supplied niche ⭐
- **Anthropic launched Agent Skills** Oct 16, 2025 (folders with SKILL.md instructions, scripts, resources that Claude loads on demand; work across Claude apps, Claude Code, API). On **Dec 18, 2025** Anthropic published Agent Skills as an **open standard** (agentskills.io) with a partner-skills directory. (https://www.anthropic.com/news/skills)
- **Anthropic opened an official marketplace** for plugins/agents/services in Sep 2026 ("Claude Marketplace: one place to discover plugins, agents, and services from our partners", Sep 23, 2026; "Build plugins for Claude", Sep 25, 2026). (https://www.anthropic.com/news/skills — related-posts section)
- **HN interest is large and recent**: 423 stories match "agent skills". Top: "Agent Skills" 544 pts/260 comments (Feb 2026, https://agentskills.io/home); Addy Osmani's "Agent Skills" 376 pts/212 comments (May 2026, https://addyosmani.com/blog/agent-skills/); SkillsBench arXiv benchmark 364 pts (https://arxiv.org/abs/2602.12670); "Agent Skills Leaderboard" 135 pts (https://skills.sh). (All via https://hn.algolia.com/api/v1/search?query=%22agent%20skills%22)
- **A paid-skills marketplace just launched**: skillbay.sh ("high quality AI skills marketplace", Sep 2026) with categories (coding & dev tools, data & spreadsheets, legal, sales & marketing…). Notably, **all current listings are free** — paid supply hasn't arrived yet. (https://skillbay.sh/)
- **Direct willingness-to-pay signal**: skillbay's "skills wanted" board shows a buyer request "Garbage-free Google Slides decks for enterprise B2B sales" with a **$100** offer and 24 replies. (https://skillbay.sh/wanted)
- The skillbay founder's Show HN post states the thesis explicitly: "thought it would be nice to try and **buy paid skills** for helping it accomplish those tasks more efficiently… redlining contracts, creating AI generated videos, different website designs". (HN story 49743459 via https://hn.algolia.com/api/v1/search?query=%22agent%20skills%22; https://skillbay.sh/)
- **Precedent for paid skill-format content**: Pieter Levels' MAKE book now ships "as a skill you can feed your AI coding agent" (SKILL.md + personal MCP server, watermarked per buyer). (https://readmake.com/)
- **Notion added an "AI Skills" template category** — 507 templates already, inside a 30,000+ template marketplace. (https://www.notion.com/templates)
- **Competition: LOW.** Marketplaces are weeks old, listings mostly free, and an AI agent is structurally the ideal producer/tester of SKILL.md packs.

---

## Category 2 — Developer tools & templates

### 2a. SaaS boilerplates (high ticket, proven)
- **ShipFast** (NextJS boilerplate by Marc Lou): **$199–$249** (listed $299/$349 crossed out), claims "8427 makers ship faster" and maker earnings of "$45,000 a month" — self-reported. (https://shipfa.st/)
- **Competition: moderate** in NextJS; many clones exist. A Python/FastAPI equivalent is a plausible gap: CodeCanyon's "FastAPI Backend Starter Kit" shows only **8 sales at $29** — small supply, but also small proven demand there. (https://codecanyon.net/item/fastapi-backend-starter-kit-readytouse-template/59320254, listed on https://codecanyon.net/search/python)

### 2b. Python scripts/tools on CodeCanyon: weak demand signal
- CodeCanyon search "python" returns **86 items**; the site's own sales-tier filter shows **No Sales: 13, Low: 41, Medium: 32, High: 0, Top Sellers: 0** — i.e., **no Python script reaches the high-sales tiers**. Best observed: "TCG AGENCY" Django script, $29, **69 sales**; "ChatBizz" AI chatbot, $22, **38 sales**; "Vhato" Django chat template, $15, **23 sales**. (https://codecanyon.net/search/python)
- **Competition: low supply but also LOW demonstrated demand** on this channel. Distribution, not production, is the bottleneck.

### 2c. Notion templates: big market, saturated at the generic end
- **Official Notion Marketplace**: "Choose from 30,000+ Notion templates", 22,401 creators; category counts: Personal Productivity 24,953; Personal Planner 9,647; Study Planner 5,555; **AI Skills 507**. A featured creator claims "44,000+ downloads" across 54 budgeting templates (self-reported). (https://www.notion.com/templates)
- **Prototion** (third-party marketplace): 1,812 templates, 853 makers, **113,636 reviews** at 4.6 avg; observed price points **$1–$39** (typical $7–$15), bundles $18–$119. (https://prototion.com/)
- **Realistic small-seller outcome** (from a maker testimonial embedded on Prototion): "2 templates listed… 557 views – 55 sales – **5€ generated**" in 3 months. (https://prototion.com/ — testimonials section, tweet by @LouisMunos)
- **Top end**: Thomas Frank's "Ultimate Brain" Notion template: **$79** (from $129) one-time, claims "40,000+ people use Ultimate Brain"; bundle with Creator's Companion $228. Self-reported. (https://thomasjfrank.com/brain/)
- **Competition: SATURATED** for generic productivity/planner templates; viable only with an audience or a narrow vertical.

### 2d. Excel/Sheets templates: high volume, low prices
- Creative Market search "excel template": **591,985 assets** (loose match, mostly invoice/budget templates); observed prices **$9–$14** (e.g., BRANDcontent Excel budget templates $14, discounted $9.80). (https://creativemarket.com/search?q=excel%20template)
- Etsy (the biggest channel for this) was inaccessible (403) — Etsy-side demand **UNVERIFIED**.
- **Competition: SATURATED**, low unit prices, design-heavy (weaker fit for an agent without design tooling).

### 2e. VS Code snippets: no visible paid market
- No paid snippet packs surfaced in any search; VS Code Marketplace extensions are distributed free. **UNVERIFIED** — no authoritative source fetched confirming paid-extension policy. Treat as "no evidence of a market" rather than "gap".

### 2f. Python education subscriptions (adjacent, proven willingness to pay)
- **Python Morsels** (Trey Hunner): **$10/mo Lite, $20/mo All-Access** ($120/$240 annual), claims "Trusted by 30,000+ Python Developers" (self-reported). Shows developers pay recurring for structured Python depth. (https://pythonmorsels.com/pricing/)

---

## Category 3 — Niche educational content

### 3a. Technical ebooks with living updates: proven, strong price points ⭐
- **MAKE book (Pieter Levels)**: live counter on the sales page reads "**32,116 copies (or $953,880) sold. 2 copies sold ($68) today**"; price **$29.99–$69.99**; continuously updated; now distributed as web/PDF/ePub/Kindle/**SKILL.md/MCP**. (https://readmake.com/)
- **Independent case study (self-reported but detailed, public HN post)**: iOS dev ebook series sold on Gumroad: "**1,534 copies and has made over $124,000**" in year 1, then "~$2k a month on average"; stack was "Gumroad for sales, Netlify for deploys". (HN "Tell HN: My early access eBook over iOS made $120k in 1 year", 316 pts: https://news.ycombinator.com/item?id=31534988 via https://hn.algolia.com/api/v1/search?query=gumroad)
- **Niche technical guides get HN traction**: "Vim Reference Guide" (244 pts, sold on Gumroad/Leanpub: https://learnbyexample.gumroad.com/l/vim_reference_guide) and "The Cyber Plumber's Handbook" — SSH tunneling guide (277 pts: https://news.ycombinator.com/item?id=19946941). (Both via https://hn.algolia.com/api/v1/search?query=gumroad)
- **Competition: MODERATE.** Topic selection is the lever; "continuously updated" is a differentiator AI agents are uniquely suited to deliver.

### 3b. Structured courses/reference content
- **Refactoring Guru** (one-person educational product business): Design Patterns eBook **€24.95** (from €40), Refactoring Course **€49.95** (from €80), GitByBit PRO €29.95. (https://refactoring.guru/store)
- **ByteByteGo** (Alex Xu): claims "over 5 million people learning", 1M+ newsletter subscribers, "Over 4,000 4.6/5 book reviews" on Amazon; text-based courses on system design/interviews. Self-reported figures. (https://bytebytego.com/)
- **Competition: MODERATE-HIGH** in broad topics (system design, patterns); **LOWER** in narrow, fast-moving niches (e.g., specific agent frameworks).

### 3c. Cheat sheets: enormous free demand, weak direct monetization
- HN engagement for cheat sheets is huge but the products are free: "Claude Code Cheat Sheet" **699 pts / 188 comments** (Mar 2026, https://cc.storyfox.cz); "Mathematics all-in-one cheat-sheet" 1,060 pts; "USB Cheat Sheet" 514 pts. (All via https://hn.algolia.com/api/v1/search?query=%22cheat%20sheet%22&numericFilters=points%3E100)
- **Implication:** cheat sheets work as lead magnets/audience-builders (the God of Prompt and AI-agent-Gumroad patterns both use free packs this way), not as standalone paid products.

---

## Opportunity summary (ranked)

| # | Opportunity | Evidence strength | Price range observed | Competition | Fit for AI-agent production |
|---|---|---|---|---|---|
| 1 | **Agent Skills packs (SKILL.md)** for coding/dev & business workflows | Strong & recent (official standard + marketplace; $100 bounty request) | $100 bounty observed; paid benchmarks missing (market is days old) | **Low** | Excellent — agents write/test skills natively |
| 2 | **Niche technical ebooks/guides, continuously updated** | Strong (32k copies/$954k; $124k/yr case study) | $24.95–$69.99 | Moderate | Good — research + updates are agent-shaped |
| 3 | **SaaS boilerplate/starter kits (non-JS stack)** | Moderate (ShipFast $199–249 ×8,427 claimed; FastAPI kit only 8 sales) | $29–$249 | Moderate | Good |
| 4 | **Notion templates (narrow verticals only)** | Strong market size, weak small-seller economics | $1–$39 (bundles to $119) | Saturated | Moderate |
| 5 | **Generic prompt packs** | Strong sales at top brands only | $20 (bundle anchor $120) | **Saturated** | Trivially easy = commoditized |
| 6 | **Python scripts on CodeCanyon / Excel templates** | Weak/low-price | $8–$29 / $9–$14 | Low supply but low demand / saturated | Moderate |

## Risks
- **Distribution is the bottleneck, not production**: every blocked channel (Etsy, PromptBase, Reddit) is also where demand concentrates; an agent-run shop needs a channel it can actually reach (HN, GitHub, its own site, Claude Marketplace).
- **Self-reported numbers**: God of Prompt, ShipFast, Python Morsels, Thomas Frank, and Notion-creator figures are seller claims, not audited data.
- **Platform risk on Skills**: the open standard is months old; Anthropic controls the dominant marketplace; skills are plaintext and easily copied/pirated.
- **Free substitutes** compress prices for prompts and cheat sheets.

## Recommended next step
Prototype 2–3 **Agent Skills** in a narrow dev-workflow niche (e.g., repo hygiene, changelog/release automation, data-cleanup), publish free versions on GitHub + skills.sh for distribution, and list paid bundles on skillbay.sh and the Claude Marketplace at **$10–$30** — while monitoring skillbay.sh/wanted for $100-style bounties to fulfill directly. This is the only category found where competition is demonstrably low, the format matches what an AI agent can build and verify itself, and a buyer explicitly posted money for a deliverable.

**Source index (primary):** godofprompt.ai · readmake.com · shipfa.st · thomasjfrank.com/brain · refactoring.guru/store · bytebytego.com · pythonmorsels.com/pricing · prototion.com · notion.com/templates · codecanyon.net/search/python · creativemarket.com/search?q=excel+template · skillbay.sh (+/wanted) · anthropic.com/news/skills · hn.algolia.com API (stories 47066827, 49743459, 31534988, 19946941, 30684232, 47495527, 46871173, 48015397, 47040430, 46697908) · lemonsqueezy.com · promptbase.com (403) · etsy.com (403)
