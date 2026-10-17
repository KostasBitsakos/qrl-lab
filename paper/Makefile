.PHONY: ieee acm lncs clean
ieee acm lncs:
	latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=build/$@ main-$@.tex
clean:
	rm -rf build/*
