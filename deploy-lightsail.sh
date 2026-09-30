#!/bin/bash
# Lightsail / EC2 안에서 1회 실행 (Ubuntu · Amazon Linux 양쪽 지원)
#   DEMO_KEY=원하는코드 ./deploy-lightsail.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
USER_NAME="$(whoami)"
DEMO_KEY="${DEMO_KEY:-$(head -c 9 /dev/urandom | base64 | tr -d '/+=')}"

echo "▸ 패키지 매니저 확인"
if command -v apt-get >/dev/null; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3-venv python3-pip
elif command -v dnf >/dev/null; then
  sudo dnf install -y -q python3 python3-pip
elif command -v yum >/dev/null; then
  sudo yum install -y -q python3 python3-pip
else
  echo "지원하지 않는 OS"; exit 1
fi
python3 -V

echo "▸ 가상환경 + 의존성 (2~3분)"
cd "$APP_DIR"
python3 -m venv .venv
./.venv/bin/pip install -q --upgrade pip
./.venv/bin/pip install -q -r requirements.txt

echo "▸ systemd 등록"
sudo tee /etc/systemd/system/solve.service >/dev/null <<UNIT
[Unit]
Description=solve prototype
After=network.target

[Service]
User=${USER_NAME}
WorkingDirectory=${APP_DIR}
Environment=DEMO_KEY=${DEMO_KEY}
Environment=TTL_HOURS=24
ExecStart=${APP_DIR}/.venv/bin/uvicorn server:app --host 0.0.0.0 --port 80
AmbientCapabilities=CAP_NET_BIND_SERVICE
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now solve
sleep 3
sudo systemctl is-active solve && echo "✔ 실행 중" || sudo journalctl -u solve -n 20 --no-pager

IP="$(curl -s --max-time 5 ifconfig.me || echo '<인스턴스 IP>')"
echo
echo "───────────────────────────────"
echo "  주소      : http://${IP}/"
echo "  접근 코드 : ${DEMO_KEY}"
echo "───────────────────────────────"
echo "로그:   sudo journalctl -u solve -f"
echo "재시작: sudo systemctl restart solve"
