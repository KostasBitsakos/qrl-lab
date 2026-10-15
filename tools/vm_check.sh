#!/usr/bin/env bash
# Read-only check of the VM before setting up QRL-Lab. Changes nothing. Prints no secrets.
# Run on the VM:  bash vm_check.sh 2>&1 | tee ~/vm_check.txt   and paste the output to the coordinator.
echo "== system";   (lsb_release -ds 2>/dev/null || head -1 /etc/os-release); uname -m; nproc
free -g | head -2;  df -h "$HOME" | tail -1
echo "== gpu";      nvidia-smi -L 2>/dev/null || echo "no NVIDIA GPU visible"
echo "== tools"
for c in python3 pip3 git tmux node npm claude codex kubectl helm docker latexmk; do
  printf "%-8s " "$c"; if command -v "$c" >/dev/null 2>&1; then
    case "$c" in
      kubectl) kubectl version --client 2>/dev/null | head -1 ;;
      tmux) tmux -V ;;
      *) "$c" --version 2>&1 | head -1 ;;
    esac
  else echo "not installed"; fi
done
[ -s "${NVM_DIR:-$HOME/.nvm}/nvm.sh" ] && echo "nvm: present" || echo "nvm: not present"
echo "== kubernetes (read-only)"
kubectl config current-context 2>&1 | head -1
kubectl version 2>&1 | grep -i server | head -1
kubectl get nodes -o wide 2>&1 | head -5
kubectl get ns 2>&1 | head -20
kubectl get deploy,statefulset,svc -A 2>/dev/null | grep -i redis | head -20
echo "== outbound https (HTTP code; 000 = unreachable)"
for u in https://api.anthropic.com https://claude.ai https://chatgpt.com https://auth.openai.com \
         https://registry.npmjs.org https://pypi.org https://quantum.ibm.com https://github.com; do
  printf "%-28s " "$u"; curl -s -o /dev/null -m 10 -w "%{http_code}\n" "$u"
done
echo "== candidate project directories (top level of home, newest first)"
ls -lt --time-style=+%Y-%m-%d "$HOME" | head -30
echo "== git repositories under home (depth 3)"
find "$HOME" -maxdepth 3 -name .git -type d 2>/dev/null | head -30
echo "== python environments (depth 3)"
find "$HOME" -maxdepth 3 \( -name pyvenv.cfg -o -name conda-meta \) 2>/dev/null | head -20
