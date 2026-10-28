# Tools for writing clear CS tutorials about this repo (2026-10-22)

Author: scholar. Nothing was installed or changed. Facts read on 2026-10-22 from the pages cited; "not shown" means the
page did not state it (WebFetch shows no dates or licences for many GitHub folders). Previously rejected tools
(`docs/extensions_eval_2026-10-20.md`) and token-saving items (`docs/token_saving_2026-10-22.md`) are not repeated.

## Περίληψη για τον Κώστα

Κώστα, δεν βρήκα επίσημο skill/plugin που να γράφει «tutorials από κώδικα» αυτόματα. Το πιο κοντινό επίσημο είναι το
`jupyter-notebook` skill της OpenAI για Codex (έχει ρητό τρόπο `tutorial`, μόνο standard library, εξάγει `.ipynb`).
Για Claude το επίσημο `explanatory-output-style` plugin κάνει τις εξηγήσεις πιο διδακτικές, αλλά δεν παράγει αρχείο
tutorial. Η ουσία: τα tutorials τα γράφει καλά ο υπάρχων `writer` agent με Markdown + Mermaid (η GitHub το
αποδίδει ως διάγραμμα), χωρίς εγκατάσταση. Σύσταση: (1) καμία εγκατάσταση, προδιαγραφή tutorial σε ένα αρχείο
οδηγιών· (2) αν θες εκτελέσιμα notebooks, το `jupyter-notebook` skill για Codex (θέλει έγκρισή σου)· (3) προαιρετικά το
explanatory plugin για Claude.

## Candidates

| # | Name | Side | Produces | Source / licence / maintainer / recency | Trust | Cost | Approval to install | Fit for CS tutorials |
|---|---|---|---|---|---|---|---|---|
| A | `jupyter-notebook` skill | Codex | `.ipynb` (kind `tutorial`, also experiment/ablation); output in `output/jupyter-notebook/` | https://github.com/openai/skills/tree/main/skills/.curated/jupyter-notebook ; OpenAI; licence not shown in SKILL.md (repo says each skill has its own `LICENSE.txt`; not opened); last commit not shown. The openai/skills repo is marked "deprecated" and points to the OpenAI Plugins repository (28.2k stars, 114 commits) | High (official) but repo deprecated | Free; Python 3.12 via `uv`, scaffold uses stdlib only; `jupyterlab`+`ipykernel` optional | Yes (skill install, `$skill-installer`; run `uv`) | Good: scaffolds tutorial structure from `references/tutorial-patterns.md`. Notebooks suit our Python analysis code, not the Streamlit dashboard. Does not write the content itself. |
| B | `explanatory-output-style` plugin (and `learning-output-style`) | Claude | No file. Adds "Insights" on implementation choices and codebase patterns to answers via a SessionStart hook | https://github.com/anthropics/claude-code/tree/main/plugins (folder list and descriptions read; repo licence, stars, dates not shown). Built-in Explanatory style is documented at https://code.claude.com/docs/en/output-styles. The plugin description says it "mimics the deprecated Explanatory output style" | High (Anthropic) | Free; adds text to every session's context (token cost, see token note) | Yes (plugin + hook) | Moderate: good for reading the code with Claude, weak for producing a polished tutorial document. `learning-output-style` inserts TODO(human) markers into code: do NOT use on research code. |
| C | `doc-coauthoring` skill | Claude | Markdown file or artifact; three stages: context gathering, section-by-section refinement, "reader testing" with a fresh Claude instance lacking your context | https://github.com/anthropics/skills/tree/main/skills/doc-coauthoring ; Anthropic; repo 183.0k stars, 60 commits; per-skill licence not shown, README says many skills Apache-2.0 and docx/pdf/pptx/xlsx source-available | High | Free | Possibly none: skills are plain folders, but adding one to `.claude/skills/` is a repo change; ask (new skill = new context rules) | Good fit for the process (reader test catches missing prerequisites), generic, not CS-specific. |
| D | `web-artifacts-builder` skill | Claude | Single self-contained `bundle.html` (React 18, TypeScript, Tailwind, shadcn/ui) | https://github.com/anthropics/skills/tree/main/skills/web-artifacts-builder ; Anthropic; needs Node 18+; scaffold scripts `init-artifact.sh`, `bundle-artifact.sh` | High | Free, but Node toolchain outside the venv | Yes (Node) | Useful only for interactive explainers (e.g. step through an HPA scaling decision). Heavy for tutorials; overkill versus static HTML. |
| E | Community Mermaid skills (`mermaid-skill`, `mermaid-tools`, others) | both | `.mmd` validated and exported to SVG/PNG/PDF via `mmdc` (Mermaid CLI) or Kroki | e.g. https://github.com/Agents365-ai/mermaid-skill and https://skillselion.com/skills/daymade/claude-code-skills/mermaid-tools (aggregator pages, search snippets only; repos NOT opened, licences unknown). A claimed mitsuhiko mermaid skill is UNVERIFIED: https://github.com/mitsuhiko/agent-stuff (Apache-2.0, 3.2k stars) lists no mermaid skill | Low-medium (unaudited) | Free; `mmdc` needs Node and headless Chromium via Puppeteer; Kroki fallback sends diagram text to a third party | Yes | Marginal: Mermaid in Markdown renders on GitHub without any tool; the skill only adds syntax validation and image export. |
| F | `anthropics/skills` `pptx`, `docx`, `pdf` | Claude | Slides, Word, PDF | https://github.com/anthropics/skills ; README: these four are source-available, not open source | High | Free | Yes | Only if slides/PDF handouts are wanted; not for tutorials. |

Also seen in the official lists, not relevant: `academy-guide` (recommends Claude Academy courses after answering Claude-usage
questions; not for our repo), `skill-creator` (authors/tests new skills; useful if we decide to write our own tutorial skill),
`canvas-design`, `algorithmic-art`, `slack-gif-creator`, `theme-factory`, `brand-guidelines`, `internal-comms`, `claude-api`,
`mcp-builder`, `webapp-testing`. Codex curated list (39 folders) also has `pdf`, `screenshot`, `playwright`, `openai-docs`,
`notion-*`, `figma-*`: none aimed at code tutorials.

## Can we do it well without any install? Yes, mostly

Existing capability: the `writer` agent, plain Markdown, and Mermaid fenced blocks. GitHub renders Mermaid inside `.md`
files natively (not re-verified today; standard GitHub feature). The dashboard has no Mermaid rendering (grep of
`dashboard/`, `tools/`, `.claude/` found no mention), so Mermaid would be seen on GitHub or in an editor, not in the dashboard
unless the engineer adds a renderer. HTML output can go through our existing Artifact/HTML publishing (not re-checked here).

Proposed no-install recipe (a short tutorial spec the writer follows, e.g. `docs/tutorial_style.md`, to be created after approval):
1. Audience and prerequisites at the top; one learning goal per tutorial (e.g. "how the HPA formula picks replicas", "how a run
   is launched and approved", "reading the dashboard Experiments tab").
2. Runnable commands from the repo only (copy from real files, with file:line pointers), expected output taken from a real run id;
   no invented numbers (golden rule 2).
3. One Mermaid diagram per architecture or control-flow idea (autoscaler loop, run approval flow).
4. "Check yourself" questions and a common-errors section.
5. Reader test: give the finished tutorial to a fresh subagent with no repo context and ask it to list every unclear step
   (the same idea as `doc-coauthoring` stage 3, free to copy).
6. Optional: a notebook version for analysis code only, using A.

## Ranking and recommendation

1. No-install workflow: `writer` + Markdown + Mermaid + written tutorial spec + reader test (copied from C). Zero cost, no approval, fully
   under our golden rules. Weakness: quality depends on the spec; needs one pass to calibrate.
2. `jupyter-notebook` skill for Codex (A). Official, free, stdlib-only scaffold; gives executable tutorials for analysis and
   metrics code. Needs approval to install; check the skill's `LICENSE.txt` and that the deprecated repo's skill still installs
   with the current Codex before relying on it.
3. `explanatory-output-style` plugin for Claude (B), as an optional reading aid when Kostas explores code with Claude. Needs
   approval; adds context per session; keep `learning-output-style` off.

Not recommended: community Mermaid skills (unaudited, add Node/Chromium for little gain), `web-artifacts-builder` (heavy toolchain),
anything requiring keys or paid credits.

## Open points
1. Which format do readers need: Markdown on GitHub, HTML in the dashboard, or notebooks? This decides between rank 1 and 2.
2. Approve the engineer adding a Mermaid renderer to the dashboard docs view? (Otherwise diagrams are only visible on GitHub.)
3. Third-party aggregator pages were not audited; any community skill must be read in full before install.

## Sources
- https://github.com/anthropics/skills (and `skills/` folder listing, raw SKILL.md of academy-guide, web-artifacts-builder, doc-coauthoring, skill-creator)
- https://github.com/anthropics/claude-code/tree/main/plugins
- https://github.com/anthropics/claude-plugins-official (repo-level facts only: Apache-2.0, 43.8k stars; plugin list not shown)
- https://code.claude.com/docs/en/output-styles
- https://github.com/openai/skills and `skills/.curated/jupyter-notebook/SKILL.md`
- https://github.com/mitsuhiko/agent-stuff
- Search snippets only: https://github.com/Agents365-ai/mermaid-skill , https://skillselion.com/skills/daymade/claude-code-skills/mermaid-tools
