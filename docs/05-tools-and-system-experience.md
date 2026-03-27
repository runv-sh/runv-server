# Ferramentas e experiência de sistema

[← Índice](README.md)

## Script: `tools/tools.py`

**Função:** orquestrar no servidor Debian:

1. Pacotes APT listados em `tools/manifests/apt_packages.txt` (alias `chat` → metapacote `weechat`). O manifesto inclui **`weechat-curses`** explicitamente porque `tools.py` usa `apt-get install --no-install-recommends`: sem isso, o metapacote `weechat` pode satisfazer-se **só** com `weechat-headless` e o comando `chat` deixa de encontrar cliente interactivo (`weechat` / `weechat-curses` no PATH).
2. Cópia de `tools/bin/` para `/usr/local/bin` (`runv-help`, `runv-links`, `runv-status`, `chat`, …).
3. MOTD dinâmico: `tools/motd/60-runv` → `/etc/update-motd.d/60-runv`.
4. Modelos para novas contas: `tools/skel/` → `/etc/skel/`.
5. Drop-in SSH para utilizadores jailed: `tools/sshd/90-runv-jailed.conf` → `/etc/ssh/sshd_config.d/`.
6. Sudo administrativo para `pmurad-admin`: `tools/sudoers/90-runv-pmurad-admin` → `/etc/sudoers.d/`.
7. Reconciliação do jail SSH em membros existentes via `scripts/admin/perm1.py`.

**Princípios declarados no código:** Python stdlib; **sem `shell=True`** em subprocess.

## Execução

```bash
cd REPO/tools
sudo python3 tools.py --help
sudo python3 tools.py --dry-run --verbose   # simular
sudo python3 tools.py
```

Flags úteis: `--force`, `--skip-apt`, `--reconcile-existing-users` (ver `--help`).

## IRC / comando `chat`

- **Utilizador:** no servidor, use apenas o comando `chat` (wrapper em `/usr/local/bin/chat` após `tools/tools.py` ou `patches/patch_irc.py`). O cliente gráfico no terminal é `weechat` / `weechat-curses` (pacote `chat` no manifesto APT).
- **Por omissão** (após `patches/patch_irc.py`): o WeeChat fica com um único servidor com autoconnect no arranque — nome interno **`runv`**, endereço **`irc.tilde.chat`**, porta **6697**, **TLS ligado**, autojoin só **`#runv`**. Outras redes que o utilizador adicionar manualmente **não** autoconectam por defeito (o patch desliga `autoconnect` nos outros servidores já existentes, sem apagar redes).
- **Provisionamento:** o patch corre com `weechat-headless -a -r '…' --stdout` (o `-a` evita auto-connect durante o batch). O launcher **`chat` não usa `-a`**. Novas contas Unix criadas com `scripts/admin/create_runv_user.py` invocam o patch automaticamente para esse utilizador. O `tools/tools.py` também aplica o backfill IRC ao final da execução.
- **Backfill / admin:** `sudo python3 patches/patch_irc.py --all-users` (ou `--user NOME`). Requer `weechat-headless` no sistema.

## Isolamento e permissões

- `pmurad-admin` fica explicitamente fora do grupo `runv-jailed` e recebe sudo administrativo via `/etc/sudoers.d/90-runv-pmurad-admin`.
- Membros normais continuam a usar o modelo `runv-jailed` + `ChrootDirectory /srv/jail/%u`, para não saírem das respetivas homes na shell SSH normal.
- `tools/tools.py` não altera contas já existentes por omissão. Se quiser reconciliar jail SSH e IRC em membros antigos, use `--reconcile-existing-users`.

Próximo: [06-site-and-apache.md](06-site-and-apache.md).
