#!/usr/bin/env bash
# Renew the expired kubeadm certificates on this single-node control plane (approved: R-20261016-007).
# Run it yourself:  sudo bash ~/qrl-lab/tools/ops/k8s_renew_certs.sh
# Rollback:         sudo bash ~/qrl-lab/tools/ops/k8s_renew_certs.sh --rollback
# Each step prints what it does and stops on the first error.
set -euo pipefail

STAMP=20261016
BAK=/etc/kubernetes.bak-$STAMP
USER_HOME=$(getent passwd "${SUDO_USER:-ubuntu}" | cut -d: -f6)
KCFG="$USER_HOME/.kube/config"
NODE=$(hostname)

[ "$(id -u)" -eq 0 ] || { echo "Run with sudo."; exit 1; }

if [ "${1:-}" = "--rollback" ]; then
  echo "== Rollback: restore $BAK and $KCFG.bak-$STAMP, restart kubelet"
  [ -d "$BAK" ] || { echo "No backup at $BAK"; exit 1; }
  rm -rf /etc/kubernetes && cp -a "$BAK" /etc/kubernetes
  [ -f "$KCFG.bak-$STAMP" ] && cp -a "$KCFG.bak-$STAMP" "$KCFG"
  systemctl restart kubelet
  echo "Rolled back."
  exit 0
fi

echo "== 1/6 Backup"
if [ -e "$BAK" ]; then echo "  $BAK exists already, keeping it (not overwritten)"; else cp -a /etc/kubernetes "$BAK"; fi
[ -e "$KCFG.bak-$STAMP" ] || cp -a "$KCFG" "$KCFG.bak-$STAMP"
echo "  ok: $BAK, $KCFG.bak-$STAMP"

echo "== 2/6 kubeadm certs renew all"
kubeadm certs renew all
kubeadm certs check-expiration | sed -n '1,20p'

echo "== 3/6 New kubelet.conf for node $NODE (the kubelet client certificate expired on 2025-11-14)"
mv /etc/kubernetes/kubelet.conf "/etc/kubernetes/kubelet.conf.expired-$STAMP"
kubeadm init phase kubeconfig kubelet --node-name "$NODE"
# Let the kubelet rotate onto a fresh client certificate from the new kubeconfig.
rm -f /var/lib/kubelet/pki/kubelet-client-current.pem

echo "== 4/6 Restart kubelet (it recreates the static pods: etcd, apiserver, controller-manager, scheduler)"
systemctl restart kubelet
sleep 30
systemctl is-active kubelet

echo "== 5/6 Update $KCFG from the renewed admin.conf"
cp /etc/kubernetes/admin.conf "$KCFG"
chown "$(stat -c %u:%g "$USER_HOME")" "$KCFG"
chmod 600 "$KCFG"

echo "== 6/6 Check"
for i in 1 2 3 4 5 6; do
  if sudo -u "${SUDO_USER:-ubuntu}" kubectl get nodes 2>/dev/null; then break; fi
  echo "  API server not ready yet ($i/6), waiting 20 s"; sleep 20
done
sudo -u "${SUDO_USER:-ubuntu}" kubectl get pods -A 2>&1 | head -30
echo "Done. If something looks wrong: sudo bash $0 --rollback"
