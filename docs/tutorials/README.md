# Tutorials library

Owner: Codex, at the researcher's request M-20261029-159. Future stateless jobs read
[PLAYBOOK.md](PLAYBOOK.md), `../tutorial.md`, and `../STATE.md` first.

- [Από τα pods στην κβαντική πολιτική](ml_quantum_autoscaling.pdf): Greek conceptual guide, 20 pages.
- Source: [src/ml_quantum_autoscaling.tex](src/ml_quantum_autoscaling.tex).
- [Review and validation status](REVIEW.md): includes any unfinished independent checks.

Build from the lab root with installed pdfLaTeX + Greek Babel/alphabeta fonts:

```sh
bash docs/tutorials/src/build.sh
taskset -c 4-7 .venv/bin/python docs/tutorials/src/verify_pdf.py
```

No package installation or experiment run is part of this build. The installed LuaLaTeX is incomplete
(`luaotfload-main` missing); pdfLaTeX is the verified build path. Auxiliary files go to `.lab/j97/tex/`.
The final PDF is copied into this folder. `pypdf` in the project venv checks text/pages/bookmarks/links;
manual inspection and independent review determine correctness/readability.

The dashboard **📚 Tutorials** tab lists direct PDFs from this folder, with a full-width download button.
Add a PDF and its title/date/description to `catalog.json` for future guides. No dashboard code changes
or service restart are needed to add a guide. Unknown PDFs appear with a filename-derived title.
