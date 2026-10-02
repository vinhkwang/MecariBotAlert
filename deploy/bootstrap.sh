#!/usr/bin/env bash
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run as root on a freshly provisioned VPS." >&2
  exit 1
fi

if [[ $# -lt 2 ]]; then
  echo "Usage: bootstrap.sh <username> \"<ssh-public-key>\"" >&2
  exit 1
fi

USERNAME="$1"
SSH_PUBLIC_KEY="$2"
SSH_PORT="${SSH_PORT:-22}"
SWAP_SIZE="${SWAP_SIZE:-1G}"

echo "==> Base packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl gnupg ufw fail2ban unattended-upgrades

echo "==> Timezone UTC"
timedatectl set-timezone UTC

echo "==> User ${USERNAME}"
if ! id -u "${USERNAME}" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" "${USERNAME}"
fi
usermod -aG sudo "${USERNAME}"
install -d -m 700 -o "${USERNAME}" -g "${USERNAME}" "/home/${USERNAME}/.ssh"
echo "${SSH_PUBLIC_KEY}" > "/home/${USERNAME}/.ssh/authorized_keys"
chmod 600 "/home/${USERNAME}/.ssh/authorized_keys"
chown "${USERNAME}:${USERNAME}" "/home/${USERNAME}/.ssh/authorized_keys"

echo "==> SSH hardening"
# sshd keeps the first value it reads; 00- loads before provider files like 50-cloud-init.conf.
cat > /etc/ssh/sshd_config.d/00-hardening.conf <<SSHCONF
Port ${SSH_PORT}
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no
PubkeyAuthentication yes
X11Forwarding no
AllowTcpForwarding yes
MaxAuthTries 3
SSHCONF
sshd -t
systemctl reload ssh || systemctl reload sshd

echo "==> Firewall"
ufw --force reset >/dev/null
ufw default deny incoming
ufw default allow outgoing
ufw allow "${SSH_PORT}/tcp"
ufw --force enable

echo "==> fail2ban"
cat > /etc/fail2ban/jail.d/sshd.local <<F2BCONF
[sshd]
enabled = true
port = ${SSH_PORT}
maxretry = 4
bantime = 1h
findtime = 10m
F2BCONF
systemctl enable --now fail2ban
systemctl restart fail2ban

echo "==> Unattended security upgrades"
cat > /etc/apt/apt.conf.d/20auto-upgrades <<APTCONF
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APTCONF

echo "==> Swap ${SWAP_SIZE}"
if [[ ! -f /swapfile ]]; then
  fallocate -l "${SWAP_SIZE}" /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=1024
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
sysctl -w vm.swappiness=10 >/dev/null
grep -q '^vm.swappiness' /etc/sysctl.conf || echo 'vm.swappiness=10' >> /etc/sysctl.conf

echo "==> Docker Engine"
if ! command -v docker >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  . /etc/os-release
  curl -fsSL "https://download.docker.com/linux/${ID}/gpg" -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${ID} ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
usermod -aG docker "${USERNAME}"
systemctl enable --now docker

echo
echo "Done. Verify BEFORE closing this session:"
echo "  ssh -p ${SSH_PORT} ${USERNAME}@<vps-ip>"
echo "  docker run --rm hello-world"
echo
echo "Port 8080 is intentionally closed. Reach the UI with:"
echo "  ssh -p ${SSH_PORT} -L 8080:127.0.0.1:8080 ${USERNAME}@<vps-ip>"
