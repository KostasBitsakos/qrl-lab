#!/usr/bin/env bash
# Create ~/qrl-lab/.venv for the dashboard (and later for the experiments' tooling).
# Isolated: it does not touch conda base or the research environments.
set -euo pipefail
LAB="${QRL_LAB_DIR:-$HOME/qrl-lab}"
cd "$LAB"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install --upgrade pip >/dev/null
.venv/bin/pip install -r dashboard/requirements.txt
.venv/bin/python -c "import streamlit, plotly, pandas, psutil; print('dashboard env ok: streamlit', streamlit.__version__)"
