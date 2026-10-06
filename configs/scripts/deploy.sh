#!/bin/bash
set -e

echo "Checking Docker..."
if ! type docker >/dev/null 2>&1; then
  echo "Docker does not exist"
  echo "Start installing docker..."
  sudo apt-get update
  sudo apt-get install -y ca-certificates curl gnupg lsb-release
  sudo mkdir -p /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
  sudo apt-get update
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  sudo systemctl enable docker
  sudo systemctl start docker
  sudo usermod -aG docker ubuntu
fi

echo "Checking Docker Compose..."
if ! type docker-compose >/dev/null 2>&1; then
  echo "docker-compose does not exist"
  echo "Start installing docker-compose"
  sudo curl -L "https://github.com/docker/compose/releases/download/1.27.3/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
  sudo chmod +x /usr/local/bin/docker-compose
fi

echo "Pulling the latest Docker Hub image"
sudo docker compose --env-file /home/ubuntu/srv/ubuntu/.env.prod \
  -f /home/ubuntu/srv/ubuntu/docker-compose.prod.yml pull

echo "Starting the container"
sudo docker compose --env-file /home/ubuntu/srv/ubuntu/.env.prod \
  -f /home/ubuntu/srv/ubuntu/docker-compose.prod.yml up -d