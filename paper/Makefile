.PHONY: ieee acm lncs clean
ieee acm lncs:
	latexmk -pdf -outdir=build/$@ main-$@.tex
clean:
	rm -rf build/*
