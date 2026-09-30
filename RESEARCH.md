# Free promotion channels for PlayNexus — research + audit

**Date:** 2026-09-30
**Scope:** dev-services business (apps, Discord bots, EXEs, tools, games) with ~zero budget.

Legend for **Automation**:
- **AUTO** — official API + your own account/asset. Safe to run unattended.
- **SEMI** — API or structured form exists, but human approval required by the platform's
  rules (or by their moderation). Pipeline drafts; you press publish.
- **MANUAL** — no real API. Pipeline prepares the exact copy, you paste it.

Legend for **Verified**:
- ✅ I read the official doc/source while writing this.
- ⚠️ Community-reported; confirm against the site's own rules before relying on it.

---

## 1. Tier 1 — Owned + your own accounts (build these first)

These have zero permission risk because you already own the surface. This is where
~80% of sustainable pipeline volume should come from, because it is the only tier
where the rules never change on you.

| Channel | Cost | Automation | Notes |
|---|---|---|---|
| **Discord webhooks** (your own server) | Free | **AUTO** ✅ | `POST /webhooks/{id}/{token}`, no auth needed beyond the URL. Rate limit ~5 req/2s per webhook. Hard cap: 30 embeds/min/channel. Best zero-friction channel for a bot-builder brand — the audience is already in the room. |
| **Discord bot** (your own bot posting to partner servers) | Free | **AUTO** ✅ | You can DM/post to any server that has explicitly invited your bot. Never mass-mention or DM non-consenting users. |
| **Bluesky** (AT Protocol) | Free | **AUTO** ✅ | `com.atproto.repo.createRecord` with an app password. 300-char post limit. Generous per-endpoint rate limits, backoff headers returned in `RateLimit-*`. |
| **Mastodon** (any instance) | Free | **AUTO** ✅ | `POST /api/v1/statuses`. Instance-wide limits vary; 500 chars default, more with unlocked "unlimited" chars setting. Mastodon is underrated here — dev community is high-intent. |
| **Telegram channel** | Free | **SEMI** ✅ | Bot API `sendMessage` to your own channel. Cheapest newsletter in existence. 4096 chars. |
| **Dev.to** (Forem) | Free | **AUTO** ✅ | `POST /api/articles`, API v1 requires `accept: application/vnd.forem.api-v1+json` + `api-key`. 30 req/30s for authenticated users, 1000 articles total. No followers cap. |
| **Hashnode** | Free | **SEMI** ⚠️ | GraphQL `mutation publishPost`. Free but dev activity is lower than Dev.to. |
| **X / Twitter** | Free (write-only) | **SEMI** ✅ | Free tier gives ~1,500 posts/month **write**, far less read. Practically: use for replies, not scheduling. |
| **GitHub profile README + repo topics** | Free | **AUTO** ✅ | `PATCH /user` and repo topics via REST. Grossly underused by dev-service sellers. A curated profile README with a services table is evergreen SEO. |
| **YouTube / TikTok** | Free | **MANUAL** ⚠️ | Highest ceiling, zero automation. Do one "I built X in 30 min" per week. Batch-record monthly. |
| **LinkedIn** | Free | **MANUAL** ⚠️ | Best channel for B2B dev-services buyers specifically. No useful API without a Sales Navigator seat. |

## 2. Tier 2 — Community (high value, real rules, approval-gated)

| Channel | Cost | Automation | The actual rule that will bite you |
|---|---|---|---|
| **Reddit** | Free | **SEMI** ✅ | Verified: 100 QPM per OAuth client-id, averaged over a 10-min window (bursts allowed). OAuth mandatory; **descriptive User-Agent is required** — `platform:appID:version (by /u/user)`, and generic UAs like `Python/urllib` are throttled hard. Chat API additionally capped at 2,000 msgs/day/recipient and 3,000/day total. **Self-promo policy is the real limit, not the API**: most dev subs enforce a 9:1 value-to-promotion ratio, and some ban outright. Must read each sub's `r/` sidebar before ever posting. |
| **Hacker News** | Free | **MANUAL** ✅ | Verified: the v0 Firebase API is **read-only and currently has no rate limit**; there is no public submit API. Submissions go through the web form. The written guideline is "don't use HN primarily for promotion" — and `s/showhn.html` requires you "drop any language that sounds like marketing or sales." Practical ceiling: **~1 submission/week, ever**. Treat as a credibility channel, not a volume channel. |
| **Lobsters** | Free | **MANUAL** ⚠️ | Invite-requested, tag-based, far lower noise than HN. Self-promo tolerated in the right tags. |
| **Stack Overflow / Super User** | Free | **MANUAL** ⚠️ | Linking your product in answers is how accounts get suspended. Only link when directly solving the question. |
| **Quora** | Free | **MANUAL** ⚠️ | Has a formal self-promotion policy: disclose affiliation, no link-dropping. |
| **r/Forhire, r/hiring, r/slavelabour** | Free | **SEMI** ⚠️ | Genuinely where dev-services get hired. Strict on unearned upvotes and on being the *only* reason a sub exists. |

## 3. Tier 3 — Launch directories (mostly forms)

Low effort, low ceiling, but they compound and several are one-shot-per-project.

| Site | Cost | Automation | Note |
|---|---|---|---|
| **Product Hunt** | Free for makers | **SEMI** ✅ | Official GraphQL API v2 + webhook. Free makers can post unlimited launches. |
| **top.gg** | Free listing | **SEMI** ✅ | Has a real API (bot stats, application-command publishing, vote webhooks). This is *the* Discord bot directory — a bot-dev business is odd without one. |
| **Disboard** | Free listing | **MANUAL** ⚠️ | Largest Discord server directory. |
| **discordlist / discord.me** | Free | **MANUAL** ⚠️ | Secondary Discord directories. |
| **itch.io** | Free | **MANUAL** ⚠️ | Essential for the games side of the business. No public write API. |
| **BetaList / Fazier / DevHunt / Uneed / Peerlist** | Free | **MANUAL** ⚠️ | Free-tier listings, all form-based. Low effort — do them once per real project. |
| **Fiverr / Freelancer / Upwork** | Free listing | **MANUAL** ⚠️ | Fiverr gives a free 3-pitch/month tier. Best direct-revenue channel for a "build anything" shop. |
| **Roblox Creator Hub** | Free | **MANUAL** ⚠️ | Relevant given your Roblox work. |
| **Steam** | $100/repo | **N/A** | Only worth it once a game is genuinely done. |

## 4. Tier 4 — Owned real estate (the only compounding asset)

- **Free hosting:** Cloudflare Pages, GitHub Pages, Vercel, Netlify. $0.
- **Do this:** one landing page per service (`/discord-bots`, `/exe-tools`, `/games`),
  each with a real embed, screenshots, pricing, and a single CTA.
- Every other tier above gets a tracked link back here. A post to a subreddit that
  doesn't route to a page you own is a wasted post.
- **Free SEO:** Google Search Console, Bing Webmaster Tools, Plausible/Umami analytics,
  `sitemap.xml`, and programmatic long-tail pages (e.g. "discord music bot developer").
  This is the only "advertising source" that pays you back after you stop working.

---

## What the pipeline will deliberately NOT do

These are not missing features. They are guardrails, because each one reliably
destroys the account and any domain you promote:

- ❌ Automated upvotes / vote rings / karma farming.
- ❌ Creating sockpuppet accounts to seed engagement.
- ❌ Bulk Discord DMs, mentions, or friend-request spam.
- ❌ Scraping user emails or contact data.
- ❌ Auto-commenting/DMing people who merely viewed a page.
- ❌ Bypassing CAPTCHA, vote-gating, or any anti-spam mechanism.
- ❌ Posting the same copy to multiple communities with no variation.

The pipeline in this repo enforces all of that in `playnexus/compliance.py`.

---

## Priority order (what I'd actually do)

1. Discord webhook → your own server + any bot you operate. **Instant, free, no rules.**
2. Dev.to articles + Bluesky + Mastodon + Telegram. **4 free APIs, all AUTO.**
3. One-page-per-service site on Cloudflare Pages. **Compounds forever.**
4. Reddit, carefully, per-sub, approval-gated. **Where the dev-services leads are.**
5. top.gg + itch.io + Fiverr. **One-time setup, steady trickle.**
6. Hacker News, ~1/week, technical-writeup angle only. **Credibility, not volume.**
7. YouTube "build log" content, batched monthly. **Slowest to start, highest ceiling.**
