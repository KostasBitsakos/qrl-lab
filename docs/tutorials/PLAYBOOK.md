# Tutorial playbook — Codex owner

Request: M-20261029-159; conceptual explanations of the research, in Greek, short and easy to read.
Future tutorial requests should be assigned to **Codex** and start by reading this file and `docs/tutorial.md`.
An agent does not retain its session: this file, sources and review notes provide continuity.

## Before writing
1. Read `docs/STATE.md`, this guide and relevant questions in `docs/tutorial.md`.
2. Define the reader, prerequisites and a few things the reader should be able to explain afterward.
3. Inspect actual code and frozen specifications; distinguish implementation, proposal and measured finding.
4. Research primary teaching/technical sources online; record URLs and what each supports.
5. Use one running example. Mark invented teaching values explicitly as hypothetical; cite actual defaults.
6. Draft a concept sequence: practical problem → concrete action → intuition → equation → interpretation → check.
7. Keep a source map with file + symbol + revision for each implementation claim. Do not turn the tutorial into code documentation.

## Writing and page design
- Short Greek sentences; give the English technical term on first use. Define every new symbol beside its equation.
- Introduce observables, actions, rewards and time before neural networks. Explain a sum as repeated addition first.
- One main question per page/section; visible headings; generous spacing; no decorative imagery.
- Use small diagrams that explain a process, with labels next to the relevant parts.
- Pair a worked example with a similar question the reader answers unaided, then provide an answer.
- Fade guidance: show all steps early; ask for the last step later.
- Explain what an equation predicts physically (pods, work, queue) and practically (which decision changes).
- Say when “physical meaning” is an analogy: a neural hidden state is not a physical measurement.
- Avoid long proofs, installation steps, tuning logs, rankings and unlabeled historical protocol values.
- Put source pointers at the relevant section; collect full titles/URLs in the references.
- In a PDF, audio-specific redundancy/modality findings do not imply removing useful text or captions.
- Prefer manageable reading segments and invite later recall. Page count is an editorial constraint, not evidence of learning.

## Teaching evidence and scope
- [IES/WWC, Organizing Instruction and Study to Improve Student Learning](https://ies.ed.gov/ncee/wwc/PracticeGuide/1):
  supports alternating worked solutions and exercises, linking concrete and abstract representations,
  retrieval and explanatory questions. Evidence strength differs by recommendation; this is not a trial of our PDF.
- [Fiorella & Mayer, Principles for Reducing Extraneous Processing (2021)](https://doi.org/10.1017/9781108894333.019):
  supports removing irrelevant material, marking structure and placing related words/graphics together.
- [Mayer, Using multimedia for e-learning (2017)](https://doi.org/10.1111/jcal.12197):
  supports segmenting and pre-teaching terms; effects depend on reader knowledge and medium.
Our page template and short length are design choices inferred from these principles, not experimentally verified benefits.

## Quality gate before publishing
1. Verify implementation statements against code, not class names or old papers. No invented API behavior or results.
2. Fresh reader: ask a separate agent to assume a beginner's knowledge, list unclear words/steps and answer the checks.
   This is an editorial proxy, not a measured human comprehension study. Revise once, then inspect the revised pages.
3. Obtain Claude technical review through `tools/ask_peer.py`; keep prompt, verbatim answer and resolution.
4. Build on cores 4–7 with `docs/tutorials/src/build.sh`; no experiments are needed.
5. Inspect representative rendered pages, Greek text extraction, page count, formulas, hyperlinks and overflow warnings.
6. Verify dashboard title/date/description/download, no directory escape, and narrow-screen layout.
7. Register the PDF in `docs/tutorials/catalog.json`; keep source and build instructions with it.
8. Update `docs/STATE.md` briefly; keep long evidence in `docs/tutorials/REVIEW.md`.

## Library convention
- PDFs live directly in `docs/tutorials/`; source in `docs/tutorials/src/`.
- `catalog.json` maps each PDF filename to title, ISO date and concise Greek description.
- Unregistered PDFs still appear with filename and modification date; register them for a polished entry.
- Never claim a quantum speed-up from simulator timings; compare parameter savings to parameter-matched classical controls.
- Quantum screens are paused (`docs/rules/paused.md`); explaining proposals does not resume experiments.
