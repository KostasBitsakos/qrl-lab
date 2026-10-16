# Paper scaffold

Shared text: `sections/*.tex`, `authors.tex`, `preamble.tex`, `refs.bib`. Numbers: only macros from
`generated/results.tex` (written by a script from the run database).

Build one venue: `make ieee` (default, CCGrid), `make acm`, `make lncs`. PDFs land in `build/<venue>/`.
To switch venue, build another target; nothing in `sections/` changes. Venue-specific class files
(IEEEtran, acmart, llncs, splncs04) must be installed or copied next to the mains.
Notes from `\todo{}` are hidden (`disable` option in `preamble.tex`); remove `disable` to show them.
Author order is provisional: edit `authors.tex` only (three forms, same order).
hyperref is loaded in the IEEE and LNCS mains; acmart loads it itself.
