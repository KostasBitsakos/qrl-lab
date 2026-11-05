#!/usr/bin/env bash
# Uses installed TeX only; no package downloads or experiment runs.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p ../../../.lab/j97/tex
for pass in 1 2; do
    taskset -c 4-7 pdflatex -interaction=nonstopmode -halt-on-error \
        -output-directory=../../../.lab/j97/tex ml_quantum_autoscaling.tex \
        > "../../../.lab/j97/tex/build-${pass}.stdout"
done
cp ../../../.lab/j97/tex/ml_quantum_autoscaling.pdf ../ml_quantum_autoscaling.pdf
