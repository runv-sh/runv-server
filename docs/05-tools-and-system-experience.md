# Ferramentas e experiência de sistema

[← Índice](README.md)

## Script: `tools/tools.py`

**Função:** orquestrar no servidor Debian:

1. Pacotes APT listados em `tools/manifests/apt_packages.txt` (alias `chat` → pacote `weechat`).
2. Cópia de `tools/bin/` para `/usr/local/bin` (`runv-help`, `runv-links`, `runv-status`, `chat`, …).
3. MOTD dinâmico: `tools/motd/60-runv` → `/etc/update-motd.d/60-runv`.
4. Modelos para novas contas: `tools/skel/` → `/etc/skel/`.
5. Drop-in SSH para utilizadores jailed: `tools/sshd/90-runv-jailed.conf` → `/etc/ssh/sshd_config.d/`.

**Princípios declarados no código:** Python stdlib; **sem `shell=True`** em subprocess.

## Execução

```bash
cd REPO/tools
sudo python3 tools.py --help
sudo python3 tools.py --dry-run --verbose   # simular
sudo python3 tools.py
```

Flags úteis: `--force`, `--skip-apt` (ver `--help`).

## IRC / patches

A rede IRC “da casa” e o comando `chat` ligam-se a `patches/patch_irc.py` conforme documentação histórica do módulo (código em `patches/`).

Próximo: [06-site-and-apache.md](06-site-and-apache.md).
