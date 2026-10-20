# Extensions evaluation: Perplexity, HyperFrames, Chrome MCP, Playwright, Firecrawl

Request M-20261020-043 · 2026-10-20 · author: scholar. Nothing was installed. All facts below were read on 2026-10-20
from the cited pages; "unknown" means the page did not show it. Star counts and release dates are as displayed by
WebFetch of the GitHub page; the fetch tool does not always show years (marked).

Project constraints used for the verdicts: no purchases, no API keys or paid credits; new plugins/MCP servers need the
researcher's approval; packages only in the project venv. Existing capability: `WebSearch`/`WebFetch` for literature,
puppeteer + chrome-headless-shell for headless dashboard checks, VM is headless and reached over SSH.

## Summary table

| Tool | Verdict | One-line reason |
|---|---|---|
| Perplexity (API / MCP) | NOT FOR THIS PROJECT | Needs an API key and prepaid balance; synthesised answers are not primary sources |
| HyperFrames | NOT FOR THIS PROJECT | Video rendering; the deliverable is a LaTeX paper |
| Chrome MCP: Claude in Chrome | NOT FOR THIS PROJECT | Needs a GUI Chrome + extension on the machine; the VM is headless over SSH |
| Chrome MCP: Chrome DevTools MCP | NOT FOR THIS PROJECT (low-value MAYBE) | Duplicates puppeteer + chrome-headless-shell, adds telemetry and ~tens of tool definitions to context |
| Playwright (Python lib) | MAYBE | Optional venv replacement for puppeteer if dashboard tests grow; not needed now |
| Playwright MCP | NOT FOR THIS PROJECT | Interactive browsing is not a bottleneck; RCE-equivalent tool, context cost |
| Firecrawl (API / MCP) | NOT FOR THIS PROJECT | Needs a key (or sends URLs to a third party on the keyless tier); WebFetch already covers our needs |

## 1. Perplexity

- What: official MCP server for the Perplexity API Platform (tools `perplexity_search`, `perplexity_ask`,
  `perplexity_research`, `perplexity_reason`). Repo: https://github.com/perplexityai/modelcontextprotocol
- Licence: MIT. Stars ~2.6k (385 forks). Releases: the GitHub Releases page shows none; last release date unknown.
- Cost/keys: requires `PERPLEXITY_API_KEY` (local) or a Bearer token (remote server). API pricing page
  (https://docs.perplexity.ai/docs/getting-started/pricing): Search API $5.00 per 1,000 requests ($1.00 with Fast Search);
  Agent API per token plus tool fees (web_search $0.0025 per call). Search results state that Pro subscribers get $5 of
  API credit per month, that the API is billed separately from the chat subscription, and that a nonzero prepaid
  balance is needed to create a key (secondary sources: https://withorb.com/blog/perplexity-pricing,
  https://radar.apideck.com/blog/how-to-get-your-perplexity-api-key). We do not know whether the researcher has Perplexity
  Pro; the project has Claude Pro and ChatGPT Plus only (PLAN R2).
- Reviews/issues: none read; not assessed.
- Plug-in: `claude mcp add perplexity --env PERPLEXITY_API_KEY=... -- npx -y @perplexity-ai/mcp-server` or the remote
  HTTP server (command from the repo README).
- Use here vs existing: literature scouting is already done by `scholar` with WebSearch/WebFetch, and the rule is that every
  bib entry is opened at its primary source. A synthesised answer with citations still has to be re-opened, so it saves
  little and adds a hallucination surface.
- Risks: an API key (forbidden by rule 6), prepaid billing, queries leave the VM.
- Verdict: NOT FOR THIS PROJECT. If the researcher already holds Perplexity Pro, using the web UI by hand for idea
  discovery (not citations) costs nothing and needs no install.

## 2. HyperFrames

- What: HeyGen's open-source framework "Write HTML. Render video. Built for agents": HTML/CSS/media/seekable animations
  rendered deterministically to MP4. Repo: https://github.com/heygen-com/hyperframes (confirmed HeyGen).
- Licence: Apache-2.0. Stars 68.4k, 6.2k forks. Latest releases v0.8.181 and v0.8.180, both 20 Oct 2026
  (https://github.com/heygen-com/hyperframes/releases). Very fast release cadence at pre-1.0 versions.
- Cost/keys: the core is free/local; needs Node.js 22+ and FFmpeg. A listing (https://agentman.ai/agentskills/connections/mcp-server/hyperframes)
  says the hosted HeyGen connector spends HeyGen credits and keeps output in HeyGen; the local CLI is the free path.
- Reviews: https://kompozy.io/reviews/heygen-hyperframes scores it 3.8/5 (renders one clip, no scripting or publishing);
  one blog cites ~3 min for a 30 s 1080p clip (https://www.noqta.tn/en/blog/heygen-hyperframes-html-to-mp4-ai-agent-video-2026).
  No GitHub issue analysis was done.
- Plug-in: Claude Code plugin (`claude plugin marketplace add heygen-com/hyperframes`, then
  `claude plugin install hyperframes@hyperframes`), standalone skills (`npx skills add heygen-com/hyperframes`), or CLI
  (`npx hyperframes init|preview|render`). No standalone MCP server is described.
- Use here: none for the paper (LaTeX, static figures). Only conceivable: an animated explainer or talk video after
  acceptance; the conference deadlines (Nov-Dec 2026) do not need it.
- Risks: a plugin that auto-updates and loads skills into context; Node 22 and FFmpeg are outside the venv.
- Verdict: NOT FOR THIS PROJECT.

## 3. Chrome MCP (two different things)

### 3a. Claude in Chrome (Anthropic)
- What: a Chrome Web Store extension that Claude Code drives with `claude --chrome` / `/chrome`. Docs:
  https://code.claude.com/docs/en/chrome
- Cost: needs a direct Anthropic plan (Pro, Max, Team, Enterprise) and `/login`; an API key or `setup-token` login keeps it
  off. No extra charge is stated on the page. Works with Chrome/Edge (other Chromium browsers detected); not supported in WSL.
- Requirements: a visible Chrome window plus the extension and native-messaging host on the same machine; it shares the
  browser's logged-in sessions. Our work runs on a headless OpenStack VM over SSH, so there is no such browser on the VM.
  It could run on the researcher's laptop only if Claude Code ran there too, which is not the setup.
- Risks: acts inside logged-in sessions (Gmail, GitHub, IBM Quantum portal); the page itself warns recordings may contain
  account details.
- Verdict: NOT FOR THIS PROJECT.

### 3b. Chrome DevTools MCP (Google)
- What: MCP server giving agents control and inspection of a live Chrome (DOM, console, network, performance traces) plus a
  CLI. Repo: https://github.com/ChromeDevTools/chrome-devtools-mcp
- Licence Apache-2.0; 53.9k stars; latest v1.11.0 on 15 Oct (2026), previous v1.10.1 on 23 Sep (2026).
- Cost: free, no key. Privacy: usage statistics on by default (opt out `--no-usage-statistics`), npm update check
  (`CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS`), performance tools may send trace URLs to the Google CrUX API
  (`--no-performance-crux`). README warns the server exposes browser content to the client. Official support: Chrome and
  Chrome for Testing only.
- Install route (needs approval): `claude mcp add chrome-devtools -- npx -y chrome-devtools-mcp@latest --headless --no-usage-statistics --no-performance-crux`
  (flags other than those named in the README were not verified; check `--help` before use).
- Context cost: one community report estimates ~19.0k tokens of tool definitions (9.5% of 200k) vs ~13.7k for Playwright MCP
  (https://mintlify.com/shanraisshan/claude-code-best-practice/reports/browser-automation-mcp); other sources disagree,
  single estimate.
- Use here: the dashboard is already checked headlessly with puppeteer + chrome-headless-shell, which is scripted and costs no
  context. DevTools MCP would add console/network inspection and performance traces for Streamlit, rarely needed.
- Verdict: NOT FOR THIS PROJECT (MAYBE only if a Streamlit front-end bug resists the puppeteer script).

## 4. Playwright

- Playwright library (Microsoft): browser automation and test runner, Python/Node. Docs: https://playwright.dev
  (not opened this session; library facts here rest on the MCP repo and general knowledge, so treat the pip route as
  UNVERIFIED until the engineer checks `pip index versions playwright` inside the venv).
- Playwright MCP: https://github.com/microsoft/playwright-mcp. Apache-2.0, 38.4k stars (3.3k forks). Latest v0.0.83 on
  28 Sep, v0.0.82 on 18 Sep (year not shown by the page). Works from accessibility snapshots rather than screenshots.
- Cost: free, no key. Headed by default; `--headless` available; `--browser` chrome/firefox/webkit/msedge.
- Install (MCP): `claude mcp add playwright npx @playwright/mcp@latest` (README). Needs approval.
- Security (README): "not a security boundary"; `browser_run_code_unsafe` is RCE-equivalent; origin allow/block lists are
  not boundaries; `--no-sandbox` and `0.0.0.0` binding are risky.
- Use here: our need is deterministic, repeatable dashboard checks, which a script does. The Python library in the venv
  (`pip install playwright`, then reuse the existing chrome-headless-shell via `executable_path` to avoid a second
  browser download) would give a cleaner test API than puppeteer (auto-waiting, tracing, screenshots) and keep tests in
  Python next to `dashboard/app.py`. Marginal gain since the puppeteer check already works.
- Verdict: Playwright Python library: MAYBE (only if dashboard tests are being extended). Playwright MCP: NOT FOR THIS
  PROJECT.

## 5. Firecrawl

- What: web search/scrape/crawl API; official MCP server https://github.com/firecrawl/firecrawl-mcp-server (MIT, 7.6k stars,
  921 forks). Latest visible release v3.2.1 on 26 Sep (year not shown), v3.2.0 on 16 Sep (self-hosted fix).
- Cost/keys: cloud API needs `FIRECRAWL_API_KEY`. README: a keyless hosted tier at `https://mcp.firecrawl.dev/v2/mcp`
  offers rate-limited scrape, search, parse; crawl/map/agent need a key. Self-host possible with `FIRECRAWL_API_URL`
  and Docker. Free plan: the official pricing page lists 1,000 credits per month, no rollover
  (https://www.firecrawl.dev/pricing.md as summarised by search; third-party pages disagree: 500/month, or 1,000 one-time;
  treat as unverified until the page is opened directly).
- Reviews: pricing commentary only (https://www.eesel.ai/blog/firecrawl-pricing); no issue review done.
- Plug-in: MCP (`env FIRECRAWL_API_KEY=... npx -y firecrawl-mcp`), or the keyless HTTP endpoint.
- Use here: venue CFPs and paper pages are fetched with WebFetch; the main failures are paywalls/Cloudflare (ACM DL, IEEE
  Xplore, CORE portal 403 per memory), which Firecrawl does not reliably solve and which may breach site terms. Scraping
  for dates must come from the official CFP page anyway.
- Risks: key or third-party data flow (every URL fetched goes to Firecrawl), self-hosting adds a Docker service.
- Verdict: NOT FOR THIS PROJECT.

## Open points for the researcher
1. Does the researcher already have a Perplexity Pro account? Only then is manual web use free.
2. Is the Playwright Python option wanted? If yes, the engineer should first verify the pip route in the venv.
