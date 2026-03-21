# runv.club – Initial Server Setup (SSH Hardening Guide)

## Configurações básicas do servidor (Debian)

Antes do hardening SSH e dos scripts em `scripts/admin/` (`starthere.py`, `create_runv_user.py`, …), convém deixar o sistema **identificável**, com **hora fiável** e **locale** coerente. Executar como **root** ou `sudo` onde indicado.

### Nome do host (hostname)

Escolha um nome estável (ex.: `runv-debian`, `runv-prod`). Evite espaços e caracteres estranhos.

```bash
sudo hostnamectl set-hostname runv-debian
hostnamectl status
```

Garanta que o FQDN local resolve (muitas stacks Debian esperam uma linha `127.0.1.1`):

```bash
grep -E '^127\.0\.1\.1' /etc/hosts || \
  echo "127.0.1.1 runv-debian" | sudo tee -a /etc/hosts
```

(Ajuste `runv-debian` ao hostname que definiu.)

### Fuso horário e relógio (NTP)

Para servidores é comum **UTC**; se preferir hora local (ex. Portugal):

```bash
sudo timedatectl set-timezone Europe/Lisbon
# ou: sudo timedatectl set-timezone UTC
sudo timedatectl set-ntp true
timedatectl status
```

Confirme que **NTP sync: yes** e que a data/hora estão corretas. Logs e metadados (`create_runv_user` grava timestamps) ficam alinhados.

### Locale e teclado (opcional mas útil)

```bash
sudo dpkg-reconfigure locales
```

Selecione pelo menos `en_US.UTF-8` ou `pt_PT.UTF-8` (UTF-8). Para consola:

```bash
sudo dpkg-reconfigure keyboard-configuration
```

### Pacotes e índices APT

Após timezone/locale:

```bash
sudo apt update
sudo apt full-upgrade -y
```

### Notas para o projeto runv-server

- **Debian recente** (ex. 13): alinhado a `scripts/requirements.txt` e aos guias em `scripts/*.md`.
- **Quotas ext4:** não edite à mão `fstab`/quotas se for usar **`starthere.py`** — ele deteta o mount de `/home` e prepara `usrquota` de forma coerente com **`create_runv_user.py`**.
- **Documentação interna:** anote hostname, IP público/privado e timezone num sítio da equipa (evita confusão entre VPS X / VPS Y).

---

## Overview
This document describes the initial secure setup of the runv.club server on Debian 13.
The goal is to establish a safe baseline before installing pubnix / shared-hosting services for runv.club.

---

## 1. Create Admin User

```bash
adduser pmurad
adduser pmurad sudo
```

Verify:
```bash
id pmurad
```

Switch:
```bash
su - pmurad
```

Test:
```bash
sudo whoami
```

---

## 2. Generate SSH Key (Client)

```powershell
ssh-keygen -t ed25519 -C "runv-sandbox" -f "$env:USERPROFILE\.ssh\runv-sandbox"
```

---

## 3. Install Public Key

```bash
mkdir -p /home/pmurad/.ssh
chmod 700 /home/pmurad/.ssh

cat > /home/pmurad/.ssh/authorized_keys <<'EOF'
<YOUR PUBLIC KEY>
EOF

chmod 600 /home/pmurad/.ssh/authorized_keys
chown -R pmurad:pmurad /home/pmurad/.ssh
```

---

## 4. Test SSH Login

```powershell
ssh -i "$env:USERPROFILE\.ssh\runv-sandbox" pmurad@SERVER_IP
```

---

## 5. Check SSH Config

```bash
sudo sshd -T | grep -E 'passwordauthentication|pubkeyauthentication|permitrootlogin'
```

---

## 6. Disable Root Login

```bash
sudo mkdir -p /etc/ssh/sshd_config.d

sudo tee /etc/ssh/sshd_config.d/99-runv-hardening.conf > /dev/null <<'EOF'
PermitRootLogin no
EOF
```

Validate:
```bash
sudo sshd -t
sudo systemctl reload ssh
```

---

## 7. Disable Password Auth

```bash
sudo tee /etc/ssh/sshd_config.d/99-runv-hardening.conf > /dev/null <<'EOF'
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
EOF
```

Reload:
```bash
sudo sshd -t
sudo systemctl reload ssh
```

Verify:
```bash
sudo sshd -T | grep -E 'passwordauthentication|pubkeyauthentication|permitrootlogin'
```

---

## Final State

- Root login: disabled
- Password login: disabled
- Key authentication: enabled

Secure SSH baseline achieved.
