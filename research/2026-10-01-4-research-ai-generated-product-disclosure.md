[0m
> scout · z-ai/glm-5.3-flash
[0m
[0m⚙ [0mqueue_list_ventures Unknown
[0m⚙ [0mqueue_list_tasks {"limit":10}
Task #4 received. No ventures exist yet, so this research will inform future product labeling policy. Let me research platform policies first.
[0m✗ [0mWebFetch https://www.etsy.com/legal/creativity-standards/ failed
[91m[1mError: [0mStatusCode: non 2xx status code (403 GET https://www.etsy.com/legal/creativity-standards/)
[0m% [0mWebFetch https://gumroad.com/terms
[0m✗ [0mWebFetch https://www.lemonsqueezy.com/terms-of-service failed
[91m[1mError: [0mStatusCode: non 2xx status code (404 GET https://www.lemonsqueezy.com/terms-of-service)
[0m✗ [0mWebFetch https://kdp.amazon.com/en_US/help/topic/G200227210 failed
[91m[1mError: [0mStatusCode: non 2xx status code (404 GET https://kdp.amazon.com/en_US/help/topic/G200227210)
[0m% [0mWebFetch https://www.lemonsqueezy.com/terms
Gumroad ToS fetched (saved to file). Etsy blocked, Lemon Squeezy and KDP URLs wrong. Let me grep the Gumroad file for AI mentions and retry the others.
[0m% [0mWebFetch https://html.duckduckgo.com/html/?q=Amazon+KDP+AI+content+guidelines+disclosure+help+page
[0m✱ [0mGrep "(?i)(artificial intelligence|\bAI\b|machine.?learn|generative)"[90m in /home/sandbox/.local/share/opencode/tool-output/tool_0f7257e46001BtgG1JKtg5LITC · 0 matches[0m
[0m✗ [0mWebFetch https://help.etsy.com/hc/en-us/articles/12721026676375-Etsy-s-Creativity-Standards failed
[91m[1mError: [0mStatusCode: non 2xx status code (404 GET https://help.etsy.com/hc/en-us/articles/12721026676375-Etsy-s-Creativity-Standards)
Lemon Squeezy ToS fetched. DuckDuckGo blocked. Let me grep both saved files for AI mentions and try Bing for the blocked pages.
[0m✱ [0mGrep "(?i)(artificial intelligence|generative|machine.?learn)"[90m in /home/sandbox/.local/share/opencode/tool-output · 0 matches[0m
[0m✱ [0mGrep "(?i)(artificial intelligence|generative|machine.?learn|\bAI\b)"[90m in /home/sandbox/.local/share/opencode/tool-output · 0 matches[0m
[0m% [0mWebFetch https://www.bing.com/search?q=Etsy+creativity+standards+AI+generated+content+disclosure+policy
[0m% [0mWebFetch https://www.bing.com/search?q=Amazon+KDP+%22AI+content%22+guidelines+disclosure+books
[0m% [0mWebFetch https://gumroad.com/prohibited
Bing results were unhelpful (localized, no policy pages). Let me try Gumroad's prohibited products page, the Wayback Machine for Etsy, and start on the legal sources (FTC, EU AI Act).
[0m% [0mWebFetch https://artificialintelligenceact.eu/article/50/
[0m✗ [0mWebFetch https://www.ftc.gov/business-guidance/blog/2023/02/keep-your-ai-claims-check failed
[91m[1mError: [0mStatusCode: non 2xx status code (404 GET https://www.ftc.gov/business-guidance/blog/2023/02/keep-your-ai-claims-check)
[0m% [0mWebFetch https://web.archive.org/web/2025/https://www.etsy.com/legal/creativity-standards/
[0m✗ [0mRead /home/sandbox/.local/share/opencode/tool-output/tool_0f725aca9001oHX6dPFC2yNd3E failed[90m [offset=700, limit=300][0m
[91m[1mError: [0mOffset 700 is out of range for this file (635 lines)
[0m% [0mWebFetch https://web.archive.org/web/2024/https://www.etsy.com/legal/creativity-standards/
[0m✗ [0mWebFetch https://web.archive.org/web/2024/https://kdp.amazon.com/en_US/help/topic/G200227210 failed
[91m[1mError: [0mStatusCode: non 2xx status code (404 GET https://web.archive.org/web/2024/https://kdp.amazon.com/en_US/help/topic/G200227210)
Good progress: Gumroad prohibits selling AI *services* (access to AI tools) but not AI-created digital files; EU AI Act Art. 50 is now in force (since 2 Aug 2026). Now let me get the Lemon Squeezy prohibited-products appendix, Etsy's archived creativity standards, Amazon KDP's AI guidelines, and the FTC source.
[0m% [0mWebFetch https://www.bing.com/search?q=site%3Aftc.gov+%22AI+claims%22+business+guidance+blog
[0m→ [0mRead /home/sandbox/.local/share/opencode/tool-output/tool_0f725aca9001oHX6dPFC2yNd3E[90m [limit=140, offset=495][0m
Let me read the Lemon Squeezy file tail, fetch the archived Etsy legal page, and try direct FTC URLs.
[0m% [0mWebFetch https://www.ftc.gov/news-events/news/press-releases/2024/09/ftc-announces-crackdown-deceptive-ai-claims-schemes
[0m% [0mWebFetch https://web.archive.org/web/20260611230007/https://www.etsy.com/legal?archived=true
[0m✗ [0mWebFetch https://www.ftc.gov/legal-library/browse/rules/fake-reviews-testimonials-rule failed
[91m[1mError: [0mStatusCode: non 2xx status code (404 GET https://www.ftc.gov/legal-library/browse/rules/fake-reviews-testimonials-rule)
[0m→ [0mRead /home/sandbox/.local/share/opencode/tool-output/tool_0f725aca9001oHX6dPFC2yNd3E[90m [limit=115, offset=380][0m
[0m% [0mWebFetch https://web.archive.org/web/20241001000000/https://www.etsy.com/legal/creativity-standards/
FTC Operation AI Comply captured — strong source. Now: Lemon Squeezy appendix, Etsy creativity standards (2024 archive), FTC fake-reviews rule, and the FTC AI-claims blog post.
[0m✗ [0mWebFetch https://www.ftc.gov/news-events/news/press-releases/2024/08/ftc-announces-final-rule-banning-fake-reviews-testimonials failed
[91m[1mError: [0mStatusCode: non 2xx status code (404 GET https://www.ftc.gov/news-events/news/press-releases/2024/08/ftc-announces-final-rule-banning-fake-reviews-testimonials)
[0m✗ [0mWebFetch https://www.ftc.gov/business-guidance/blog/2023/02/keep-your-ai-claims-in-check failed
[91m[1mError: [0mStatusCode: non 2xx status code (404 GET https://www.ftc.gov/business-guidance/blog/2023/02/keep-your-ai-claims-in-check)
Lemon Squeezy Appendix A captured (no AI-specific rule; seller bears all disclosure responsibility). Now let me locate Etsy's creativity standards via the Wayback CDX API and fix the FTC URLs.
[0m% [0mWebFetch https://search.usa.gov/search?affiliate=ftc_prod&query=%22keep+your+AI+claims%22
[0m✗ [0mWebFetch https://www.ftc.gov/news-events/news/press-releases/2024/08/ftc-announces-final-rule-banning-fake-reviews-and-testimonials failed
[91m[1mError: [0mStatusCode: non 2xx status code (404 GET https://www.ftc.gov/news-events/news/press-releases/2024/08/ftc-announces-final-rule-banning-fake-reviews-and-testimonials)
[0m✗ [0mWebFetch http://web.archive.org/cdx/search/cdx?url=etsy.com/legal/creativity-standards&output=json&limit=15&collapse=digest failed
[91m[1mError: [0mStatusCode: non 2xx status code (503 GET http://web.archive.org/cdx/search/cdx?url=etsy.com/legal/creativity-standards&output=json&limit=15&collapse=digest)
[0m% [0mWebFetch https://www.ftc.gov/industry/technology/artificial-intelligence
Let me try the FTC's AI topic page (linked from the press release), the eCFR for the fake-reviews rule, and Etsy's archived seller policies.
[0m% [0mWebFetch https://www.ecfr.gov/current/title-16/chapter-I/subchapter-B/part-465
[0m% [0mWebFetch https://web.archive.org/web/20260611230007/https://www.etsy.com/legal/section/sellers
Strong FTC sources captured (16 CFR 465 with "clear and conspicuous" definition is gold for disclosure formatting). Now: Etsy's Creativity Standards (correct URL found: /legal/creativity/), the FTC AI-claims post via Wayback, Utah's AI disclosure law, and buyer-sentiment searches.
[0m% [0mWebFetch https://www.bing.com/search?q=survey+consumers+attitudes+AI-generated+products+disclosure+trust+percentage
[0m% [0mWebFetch https://le.utah.gov/~2024/bills/static/SB0149.html
[0m% [0mWebFetch https://web.archive.org/web/2023/https://www.ftc.gov/business-guidance/blog/2023/02/keep-your-ai-claims-check
[0m% [0mWebFetch https://web.archive.org/web/20260617040657/https://www.etsy.com/legal/creativity/
Etsy's AI disclosure requirement captured verbatim ("Sellers must disclose within their listing description if an item is created with the use of AI"), plus the FTC AI-claims post. Now: Utah bill text, Amazon KDP policy via Mojeek, Gumroad product-labeling examples, and the FTC "Luring Test" post.
[0m% [0mWebFetch https://www.mojeek.com/search?q=Amazon+KDP+%22AI+content+guidelines%22+help+topic
[0m% [0mWebFetch https://le.utah.gov/~2024/bills/xmlEnrolled/SB0149.xml
[0m✗ [0mWebFetch https://www.ftc.gov/business-guidance/blog/2023/05/luring-test-ai-engineering-consumer-trust failed
[91m[1mError: [0mStatusCode: non 2xx status code (404 GET https://www.ftc.gov/business-guidance/blog/2023/05/luring-test-ai-engineering-consumer-trust)
Utah SB 149 fully captured — businesses are liable for what their generative AI says, and must disclose AI on request. Now let me get the FTC "Luring Test" post via Wayback, retry the CDX lookup for Amazon KDP's AI policy, and check Pew Research for buyer-attitude data.
[0m✗ [0mWebFetch https://www.pewresearch.org/short-reads/2023/11/21/what-americans-think-about-ai/ failed
[91m[1mError: [0mStatusCode: non 2xx status code (404 GET https://www.pewresearch.org/short-reads/2023/11/21/what-americans-think-about-ai/)
[0m% [0mWebFetch https://web.archive.org/web/2024/https://www.ftc.gov/business-guidance/blog/2023/05/luring-test-ai-engineering-consumer-trust
[0m% [0mWebFetch https://web.archive.org/cdx/search/cdx?url=kdp.amazon.com/en_US/help/topic/G200227210&output=json&limit=5
The Luring Test moved to consumer-alerts. Let me fetch it archived, retry Bing with US market params for KDP, and pull Pew's AI topic page for survey data.
[0m% [0mWebFetch https://www.bing.com/search?q=amazon+kdp+%22AI+content%22+guidelines+disclosure&mkt=en-US&cc=US&setlang=en-US
[0m% [0mWebFetch https://web.archive.org/web/20250105065215/https://www.ftc.gov/consumer-alerts/2023/05/luring-test-ai-and-engineering-consumer-trust
[0m% [0mWebFetch https://www.pewresearch.org/topic/internet-technology/artificial-intelligence/
[0m% [0mWebFetch https://www.pewresearch.org/short-reads/2025/09/17/from-political-speeches-to-songs-how-would-americans-react-if-they-found-out-ai-was-involved/
FTC "Luring Test" captured — "people should know if they're communicating with a real person or a machine." Pew has a directly relevant 2025 short read on reactions to discovering AI involvement. Let me fetch it, find the real KDP AI-policy URL via CDX, and look at real Gumroad listings for labeling examples.
[0m% [0mWebFetch https://gumroad.com/discover?query=AI%20prompt%20pack
[0m% [0mWebFetch https://web.archive.org/cdx/search/cdx?url=kdp.amazon.com/en_US/help/topic/&matchType=prefix&output=json&limit=100&collapse=urlkey&from=2023&to=2024
[0m✗ [0mWebFetch https://helpx.adobe.com/stock/contributor/help/generative-ai-content.html failed
[91m[1mError: [0mStatusCode: non 2xx status code (403 GET https://helpx.adobe.com/stock/contributor/help/generative-ai-content.html)
[0m% [0mWebFetch https://web.archive.org/cdx/search/cdx?url=kdp.amazon.com/en_US/help/topic/G2002&matchType=prefix&output=json&limit=60&collapse=urlkey&from=2023&to=2025
Pew data captured — strong buyer-expectation numbers (41% feel worse discovering a support chatbot; 49% like AI-made art less; young adults most negative). Now: KDP topic-ID hunt via CDX prefix, Adobe Stock's AI-labeling policy (a real norm-setting example), and the FTC post on misrepresenting how products are created.
[0m% [0mWebFetch https://web.archive.org/web/2024/https://www.ftc.gov/business-guidance/blog/2023/08/cant-lose-what-you-never-had-claims-about-digital-ownership-creation-age-generative-ai
FTC's most on-point statement captured: "Selling digital items created via AI tools is obviously not okay if you're trying to fool people into thinking that the items are the work of particular human creators." Now let me pin down the Amazon KDP policy via news coverage, Adobe's AI-labeling rules, and Etsy's seller-handbook AI guidance.
[0m% [0mWebFetch https://web.archive.org/cdx/search/cdx?url=theverge.com/2023/09/07/&matchType=prefix&output=json&limit=40&collapse=urlkey
[0m% [0mWebFetch https://web.archive.org/web/2024/https://helpx.adobe.com/stock/contributor/help/generative-ai-content.html
[0m% [0mWebFetch https://web.archive.org/web/20260617041729/https://www.etsy.com/seller-handbook/article/1275449912004
[0m✗ [0mWebFetch https://www.theguardian.com/books/2023/sep/06/amazon-limits-self-publishing-amid-flood-of-ai-generated-books failed
[91m[1mError: [0mStatusCode: non 2xx status code (404 GET https://www.theguardian.com/books/2023/sep/06/amazon-limits-self-publishing-amid-flood-of-ai-generated-books)
[0m✗ [0mWebFetch https://www.reuters.com/technology/amazon-limits-self-publishing-authors-amid-flood-ai-generated-books-2023-09-06/ failed
[91m[1mError: [0mStatusCode: non 2xx status code (401 GET https://www.reuters.com/technology/amazon-limits-self-publishing-authors-amid-flood-ai-generated-books-2023-09-06/)
Adobe Stock's mandatory AI-labeling checkbox and Etsy's seller-handbook AI stance both captured. Final gap: the Amazon KDP disclosure policy via news coverage, and a buyer-forum sentiment check.
[0m% [0mWebFetch https://old.reddit.com/r/EtsySellers/search/?q=AI+generated+disclosure&restrict_sr=on&sort=relevance&t=all
Let me try one final CDX search for the Guardian's Amazon KDP coverage, then compile the report.
[0m✗ [0mWebFetch https://web.archive.org/cdx/search/cdx?url=theguardian.com/books/2023/sep/&matchType=prefix&output=json&limit=100&collapse=urlkey&filter=original:.*amazon.* failed
[91m[1mError: [0mStatusCode: non 2xx status code (403 GET https://web.archive.org/cdx/search/cdx?url=theguardian.com/books/2023/sep/&matchType=prefix&output=json&limit=100&collapse=urlkey&filter=original:.*amazon.*)
Research complete. I have enough verified material across all four focus areas. Here is the full report for the orchestrator to save under `research/`.

---

# Research Report: AI-Generated Product Disclosure Norms (Task #4)

**Date:** 2026-10-01 | **Agent:** scout | **Status:** Complete — 15 verified sources, 1 item UNVERIFIED

## Opportunity summary

There is no single global rule that says "label your digital product as AI-made." Instead, disclosure obligations come from four stacked layers: (1) platform policies (Etsy mandates it; Gumroad/Lemon Squeezy push it back onto the seller via anti-deception clauses), (2) consumer-protection law (FTC treats misrepresenting *how a product was made* as deception; the EU AI Act's transparency rules took effect 2 Aug 2026), (3) state/national AI-interaction laws (Utah), and (4) buyer sentiment (Pew: ~half of buyers react negatively to discovering AI involvement after the fact, and young buyers most of all). **The practical norm that is emerging: disclose AI involvement clearly, early, and in the listing itself — and never imply a human made something an agent made.** For Kiraci, a standardized, prominent "How this was made" disclosure block on every product page is cheap insurance that satisfies all four layers at once.

---

## 1. Platform policies

### Gumroad
- **Policy:** Gumroad's Prohibited Products list (rev. Sept 16, 2026) bans "AI services which includes selling access to AI tools, chatbots, image or content generation services, or subscriptions to AI services that are fulfilled outside of Gumroad" (item 2) and "deceptive marketing practices" (item 22). Selling *files created with AI* is not prohibited; selling *access to AI tools* is.
- **ToS obligation:** Suppliers must "use best efforts to ensure that all communications, representations and warranties you make in connection with your Products will: (i) be accurate and contain all disclosures and disclaimers necessary to prevent such communications and/or representations from being false, deceptive, or misleading; and (ii) otherwise comply with all applicable laws… related to consumer protection" (ToS §11.2(b)). Gumroad can hold/withhold funds for "misleading, deceptive" products (§11.3(c)(iii)).
- **No AI-disclosure-specific rule found** in the ToS or prohibited list (I grepped the full fetched ToS text; no "artificial intelligence"/"generative" hits).
- **Source:** https://gumroad.com/prohibited ; https://gumroad.com/terms
- **Implication for Kiraci:** Selling AI-created *files* on Gumroad is allowed, but any product description must not deceive. Do **not** list "access to our AI agent" as a product on Gumroad — that's a prohibited AI service.

### Lemon Squeezy
- **Policy:** The Terms (SaaS Service Agreement with Sold through Link, LLC) contain **no AI-specific disclosure requirement**. Appendix A "Prohibited Products/Services" bans unlicensed content, "business-in-a-box, work-from-home, get-rich-quick schemes," and essay mills — but not AI-created goods.
- **Key clause:** "Lemon Squeezy is not responsible and does not assume any obligations for any regulatory compliance or disclosures required of Customer" (§9.3). Also §9.1(g): customer will comply with all applicable laws; §6.1(f): no unlawful material.
- **Source:** https://www.lemonsqueezy.com/terms
- **Implication for Kiraci:** Lemon Squeezy (Kiraci's planned payment rail) puts 100% of disclosure/compliance burden on the seller. Whatever labeling Kiraci does must be built into its own product pages; the platform will not do it for us, and will not shield us from FTC/EU liability either.

### Etsy (the strictest, and the clearest precedent)
- **Policy:** Etsy's Creativity Standards (live page: https://www.etsy.com/legal/creativity; verified via June 17, 2026 archive capture, page last updated Jun 10, 2025) create a category "Seller-prompted AI creations" and state verbatim: **"Sellers must disclose within their listing description if an item is created with the use of AI."** All items must "incorporate a human touch." **AI prompt bundles explicitly do NOT qualify** as sellable "designed by a seller" items.
- **Seller Handbook** ("What's Etsy's Stance on AI Creations?", July 9, 2024): confirms the listing-description disclosure requirement, prohibits selling AI prompt bundles separately from finished artwork, and subjects AI nudity to the Prohibited Items Policy.
- **Sources:** https://www.etsy.com/legal/creativity (archived: https://web.archive.org/web/20260617041729/https://www.etsy.com/legal/creativity) ; https://www.etsy.com/seller-handbook/article/1275449912004 (archived: https://web.archive.org/web/20260617041256/https://www.etsy.com/seller-handbook/article/1275449912004)
- **Implication for Kiraci:** Etsy is the model to copy: disclosure belongs **in the listing description itself**, not buried in a FAQ. Also note: Etsy treats "prompt packs" as non-products — if Kiraci ever considers selling prompt bundles, Etsy forbids it (Gumroad does not, but the norm is against it).

### Adobe Stock (norm-setting example of platform-side AI labeling)
- **Policy:** Contributors **must** check the "Created using generative AI tools" checkbox before submission; must check "People and Property are fictional" for AI-generated people/property; prompts/titles may not contain artist names, real people's names, or third-party IP references; AI content is labeled platform-side so buyers see it. Notably: "Don't add 'generative AI' to titles and keywords. The checkbox… classifies your image as a generative AI image" — i.e., labeling is structured, not ad-hoc.
- **Source:** https://helpx.adobe.com/stock/contributor/help/generative-ai-content.html (verified via Jan 17, 2025 archive capture; page last updated Jul 17, 2024)
- **Implication for Kiraci:** Structured, standardized labeling (a fixed field/banner rather than free-text prose) is how mature marketplaces do it. Kiraci should implement disclosure as a **mandatory product field**, not something the seller-agent writes ad hoc.

### Amazon KDP (analogous disclosure regime — UNVERIFIED this session)
- **Claim:** Amazon's Kindle Direct Publishing requires authors to disclose at publish time whether content is AI-generated vs. AI-assisted, and limits AI-assisted publishing volume (announced Sept 2023). **UNVERIFIED** — I could not reach the official KDP help page (kdp.amazon.com returned 404 to automated fetches; the Wayback CDX shows no capture of the topic ID I had noted) nor a stable news URL this session. Verify manually at https://kdp.amazon.com/en_US/help (search "AI content guidelines") before relying on it.

---

## 2. Legal requirements

### FTC (US) — deception law applies fully; no "AI exemption"
- **Core rule:** "Using AI tools to trick, mislead, or defraud people is illegal… there is no AI exemption from the laws on the books." Operation AI Comply (Sept 25, 2024) targeted AI-hype schemes (DoNotPay's "robot lawyer," AI e-commerce money-making schemes) and Rytr, an AI review-writing tool. **Source:** https://www.ftc.gov/news-events/news/press-releases/2024/09/ftc-announces-crackdown-deceptive-ai-claims-schemes
- **Most on-point statement for product labeling:** "Selling digital items created via AI tools is obviously not okay if you're trying to fool people into thinking that the items are the work of particular human creators," and "It's not unusual for the FTC to sue when sellers deceive consumers about how products were made." **Source:** FTC business blog, "Can't lose what you never had" (Aug 16, 2023): https://www.ftc.gov/business-guidance/blog/2023/08/cant-lose-what-you-never-had-claims-about-digital-ownership-creation-age-generative-ai (verified via archive capture)
- **AI claims about the product itself:** Don't exaggerate what your AI product can do; substantiate comparative claims; know the risks; and note "merely using an AI tool in the development process is not the same as a product having AI in it." **Source:** "Keep your AI claims in check" (Feb 27, 2023): https://www.ftc.gov/business-guidance/blog/2023/02/keep-your-ai-claims-check (verified via archive capture; live page bot-blocked)
- **Human/machine disclosure:** "…certainly, people should know if they're communicating with a real person or a machine." **Source:** "The Luring Test" (May 1, 2023): https://www.ftc.gov/consumer-alerts/2023/05/luring-test-ai-and-engineering-consumer-trust (verified via archive capture)
- **Fake reviews rule (16 CFR Part 465, effective Oct 21, 2024):** Bans fake/false reviews — including reviews that misrepresent that the reviewer "used or otherwise had experience with the product." Defines "clear and conspicuous" disclosure: unavoidable (no hover/click required), same medium as the claim, not contradicted by other content, understandable diction. **Source:** https://www.ecfr.gov/current/title-16/chapter-I/subchapter-D/part-465
- **Nuance:** The FTC **set aside** the Rytr consent order on Dec 22, 2025, citing the administration's AI Action Plan — enforcement posture on AI is shifting, but the FTC Act deception standard itself is unchanged. **Source:** https://www.ftc.gov/industry/technology/artificial-intelligence (tag page listing both the Rytr case history and the set-aside order)
- **Implication for Kiraci:** (a) Never present agent-made products as human-made, and never use a fake human persona/pen name implying personal craftsmanship. (b) Never generate reviews or testimonials for Kiraci products — that's now a per-se rule violation. (c) If Kiraci's agent chats with buyers, it must not pretend to be human.

### EU AI Act — Article 50 transparency obligations (in force since 2 Aug 2026)
- **Art. 50(1):** AI systems interacting directly with people must inform them they are interacting with AI, unless obvious.
- **Art. 50(2):** Providers of AI systems generating synthetic audio/image/video/text must mark outputs in a **machine-readable format** detectable as artificially generated (exemption for assistive editing and personal non-professional use).
- **Art. 50(4):** Deepfake content must be disclosed as artificially generated; AI-generated **text published to inform the public on matters of public interest** must be disclosed — *unless* it "has undergone a process of human review or editorial control and where a natural or legal person holds editorial responsibility."
- **Art. 50(5):** Disclosure must be "clear and distinguishable… at the latest at the time of the first interaction or exposure."
- **Source:** https://artificialintelligenceact.eu/article/50/ (includes applicability date per Art. 113)
- **Implication for Kiraci:** If Kiraci sells into the EU: AI-generated images/audio in products should carry machine-readable provenance marking (e.g., C2PA-style metadata — implementation detail, UNVERIFIED as to which standard the Commission codes of practice will endorse). AI-written "public-interest" text (e.g., a free newsletter/report used as marketing) needs disclosure **unless** a human editor takes editorial responsibility — a cheap compliance path: have the human owner review/sign off on public-facing content. Product listings and marketing copy aimed at EU buyers should disclose AI generation at first exposure.

### Utah AI Policy Act (SB 149, effective May 1, 2024) — the "disclose on request" model
- **Utah Code 13-2-12(2):** It is **not a defense** to a consumer-protection violation that generative AI "made the violative statement," "undertook the violative act," or "was used in furtherance of the violation" — the business is liable for what its AI says.
- **13-2-12(3):** Anyone using generative AI to interact with a person must "clearly and conspicuously disclose… if asked… that the person is interacting with generative artificial intelligence and not a human."
- **13-2-12(4)-(5):** In regulated occupations, disclosure is proactive (verbally at start of oral exchange; via electronic messaging before written exchange). Fines up to $2,500 per violation.
- **Sources:** bill page https://le.utah.gov/~2024/bills/static/SB0149.html ; enrolled text https://le.utah.gov/~2024/bills/xmlEnrolled/SB0149.xml
- **Implication for Kiraci:** If any Kiraci agent answers buyer email/support, it must admit to being AI when asked (and proactively disclosing is safer). Also: the agent's marketing claims are the business's claims — an agent hallucinating a product benefit is a consumer-protection violation by the business, full stop.

### What's required vs. recommended (synthesis)
- **Legally required (US):** No deception about who/what created the product or what it does (FTC Act); no fake reviews (16 CFR 465); AI-interaction disclosure on request for consumer-facing AI (Utah-style statutes; other states have similar — not individually verified this session: UNVERIFIED).
- **Legally required (EU, since Aug 2, 2026):** Machine-readable marking of synthetic content by AI-system providers; disclosure of deepfakes and public-interest AI text; clear disclosure at first exposure (Art. 50).
- **Platform-required:** Etsy listing-description disclosure; Adobe Stock checkbox.
- **Recommended (not yet mandated for downloadable digital products in the US):** A proactive "made with AI" statement on the product page. No US federal rule currently forces this for, e.g., an AI-written PDF guide — but the FTC's "how products were made" deception doctrine covers the lying case, and buyer sentiment (below) rewards voluntary disclosure.

---

## 3. Best practices — disclosure language observed

- **Etsy's required phrasing pattern:** a plain statement in the listing description that the item "is created with the use of AI" (official requirement text quoted above). Sellers typically write variants like "Created using AI tools based on my original prompt" — the *official* language is Etsy's; seller phrasing examples on live listings were not individually fetched this session (**UNVERIFIED** beyond the policy text).
- **Adobe Stock's pattern:** structured checkbox ("Created using generative AI tools") + fictional-person flag, surfaced to buyers by the platform rather than in free text.
- **EU AI Act's pattern:** disclosure "in a clear and distinguishable manner at the latest at the time of the first interaction or exposure" — i.e., before/at purchase, not in a post-sale README.
- **FTC's implied standard:** the 16 CFR 465 "clear and conspicuous" definition is the best available template for *how* to disclose: unavoidable, same medium, not contradicted, plain language (https://www.ecfr.gov/current/title-16/chapter-I/subchapter-D/part-465 §465.1(c)).
- **Recommended Kiraci disclosure block** (synthesized from the above; this is my recommendation, not a sourced norm): a fixed section on every product page and in every delivered file: *"How this was made: This product was researched, written, and assembled by an automated AI agent [name], with human review for [scope]. No human author is claimed. Sources used: [list]. Created on [date]."* — placed before the buy button (first exposure), never contradicted by marketing copy elsewhere.

---

## 4. Buyer expectations

- **Pew Research Center survey (5,023 US adults, June 9–15, 2025)** — reactions to *learning after the fact* that AI was involved:
  - Customer service: **41% would feel worse** realizing they talked to an AI chatbot; 53% wouldn't change.
  - AI-made painting they liked: **49% would like it less**; 48% no change. AI-made song: 38% less; 58% no change. News article: 56% less. Political speech: 71% less.
  - **Younger buyers are the most negative:** 66% of under-30s would like an AI-made painting less vs. 36% of 65+; 53% vs. 26% for songs.
  - **Source:** https://www.pewresearch.org/short-reads/2025/09/17/from-political-speeches-to-songs-how-would-americans-react-if-they-found-out-ai-was-involved/
- **Related Pew signals:** "Americans want transparency when AI is used in their healthcare" (Aug 25, 2026) — transparency demand generalizes: https://www.pewresearch.org/short-reads/2026/08/25/americans-want-transparency-when-ai-is-used-in-their-healthcare/ ; "How Much of the Internet Is Written With AI?" (Aug 20, 2026): https://www.pewresearch.org/data-labs/2026/08/20/how-much-of-the-internet-is-written-with-ai/ ; "Young adults in the U.S. are increasingly wary of AI" (Aug 18, 2026): https://www.pewresearch.org/short-reads/2026/08/18/young-adults-in-the-us-are-increasingly-wary-of-ai-concerned-it-will-take-jobs/
- **Interpretation for Kiraci:** The "after-the-fact discovery" framing is exactly the risk of *not* disclosing: a large minority (and among young buyers, a majority) punishes the product once they find out. Pre-purchase disclosure converts "feeling deceived" into "informed choice" — the 48–58% "no change" bloc is the addressable market for honestly-labeled AI products. Forum/Reddit sentiment was not fetchable this session (Reddit blocks automated access) — **UNVERIFIED**; Pew is the reliable quantitative base.

---

## Risks

1. **Platform risk (Gumroad):** Selling anything framed as "access to an AI agent/service" violates Gumroad's prohibited list — products must be files/content, not agent access. Fund holds are possible for "misleading" products (ToS §11.3(c)).
2. **Legal risk (US):** FTC deception exposure if any listing implies human authorship, unverified efficacy claims, or if reviews are ever fabricated. Utah-style exposure if agent support chats deny being AI.
3. **Legal risk (EU):** Art. 50 machine-readable marking + first-exposure disclosure for synthetic media; public-interest AI text needs human editorial responsibility to be exempt.
4. **Reputation risk:** Pew data shows post-hoc discovery of AI involvement is net-negative, worst among young buyers — silent AI labeling is a conversion and refund-rate risk (Gumroad reserves funds above 15% refund rate).
5. **Regulatory drift:** FTC's AI enforcement posture is actively shifting (Rytr order set aside Dec 2025; new AI-accuracy policy statement proposed July 2026) — labeling policy needs an annual review trigger.

## Recommended next steps for Kiraci

1. **Adopt a mandatory `ai_disclosure` field** on every venture/product (like Adobe's checkbox, not free text), rendered as a "How this was made" block above the buy button, and mirrored inside delivered files. Satisfies Etsy-style platform rules, FTC "clear and conspicuous," and EU "first exposure" in one move.
2. **Add a disclosure clause to agent prompts:** agents must never claim human authorship, must answer "are you a bot?" truthfully in any buyer-facing channel, and must never generate reviews/testimonials.
3. **Never list agent access as a product** on Gumroad; products = downloadable files only.
4. **For EU sales:** add human editorial sign-off (owner review) for any public-interest AI text used in marketing, and investigate C2PA-style metadata for AI-generated images before any EU launch (standard choice UNVERIFIED — Commission codes of practice still forming).
5. **Verify the Amazon KDP policy manually** (https://kdp.amazon.com/en_US/help, search "AI content guidelines") if Kiraci ever publishes books — it's the strictest known precedent for AI-content disclosure in digital products.
6. **Re-run this research in ~6 months** (FTC posture and EU implementing acts are moving).

## Source list (all verified this session unless noted)

1. https://gumroad.com/prohibited — Gumroad prohibited products (AI services ban, deceptive marketing ban)
2. https://gumroad.com/terms — Gumroad ToS §11.2(b), §11.3(c)
3. https://www.lemonsqueezy.com/terms — Lemon Squeezy ToS §9.3, Appendix A
4. https://www.etsy.com/legal/creativity (archived 2026-06-17) — Etsy Creativity Standards, AI disclosure mandate
5. https://www.etsy.com/seller-handbook/article/1275449912004 (archived 2026-06-17) — Etsy AI stance, prompt-bundle ban
6. https://helpx.adobe.com/stock/contributor/help/generative-ai-content.html (archived 2025-01-17) — Adobe Stock AI labeling
7. https://www.ftc.gov/news-events/news/press-releases/2024/09/ftc-announces-crackdown-deceptive-ai-claims-schemes — Operation AI Comply
8. https://www.ftc.gov/business-guidance/blog/2023/08/cant-lose-what-you-never-had-claims-about-digital-ownership-creation-age-generative-ai (archived) — FTC on misrepresenting AI creation
9. https://www.ftc.gov/business-guidance/blog/2023/02/keep-your-ai-claims-check (archived) — FTC on AI efficacy claims
10. https://www.ftc.gov/consumer-alerts/2023/05/luring-test-ai-and-engineering-consumer-trust (archived) — FTC on human/machine disclosure
11. https://www.ecfr.gov/current/title-16/chapter-I/subchapter-D/part-465 — 16 CFR 465 fake-reviews rule + clear-and-conspicuous definition
12. https://www.ftc.gov/industry/technology/artificial-intelligence — FTC AI enforcement index (incl. Rytr set-aside, Workado, 2026 AI-accuracy policy statement)
13. https://artificialintelligenceact.eu/article/50/ — EU AI Act Art. 50 (in force 2 Aug 2026)
14. https://le.utah.gov/~2024/bills/static/SB0149.html + https://le.utah.gov/~2024/bills/xmlEnrolled/SB0149.xml — Utah AI Policy Act
15. https://www.pewresearch.org/short-reads/2025/09/17/from-political-speeches-to-songs-how-would-americans-react-if-they-found-out-ai-was-involved/ — Pew buyer-reaction survey (+ 3 related Pew URLs above)
16. Amazon KDP AI content guidelines — **UNVERIFIED** (official page unreachable to automated fetch this session; verify manually)
