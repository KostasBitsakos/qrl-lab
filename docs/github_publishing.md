# GitHub publishing (R-20261029-008)

Repo: ONLY github.com/KostasBitsakos/dinos_sofia_k8s_redis_scaling (remote `github`; the script refuses any other URL or remote, M-20261029-147). Rules: R-20261029-002 (joint Claude+Codex review,
never force, never secrets), R-20261029-008 (versions as tags, no "Compare & pull").

- Versions are annotated tags: `cycle<N>-claude-vX.Y`, `cycle<N>-codex-vX.Y`, `cycle<N>-final-vX.Y`. A pushed tag is
  never moved; a fix gets a new version.
- `main` is the only branch: the approved shared code, fast-forward only.
- Tool: `tools/publish_release.py` (`tag`, `main`, `retire-branch`; `--dry-run` first). Every push needs a review file
  naming the full commit SHA with lines `claude: APPROVE` and `codex: APPROVE`; the tree is scanned for secret-looking
  files. Log: `.lab/publish/log.jsonl`; review records: `.lab/publish/review_*.md`.
- Cycle 1: tags `cycle1-claude-v1.0` (afc4ea7) and `cycle1-codex-v1.0` (ad283e4) pushed 29/10 (J88). Deleting the old
  branches `cycle1-claude`/`cycle1-codex` was blocked by the agent permission classifier; the researcher runs
  `git push github :refs/heads/cycle1-claude :refs/heads/cycle1-codex` (content stays in the tags).
