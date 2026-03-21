# Instalação do servidor runv.club

Este documento descreve a **ordem recomendada** para preparar um servidor Debian (testado em Debian 13 “trixie”) com os scripts deste repositório, e onde aprofundar a configuração de cada módulo.

**Pré-requisitos**

- Acesso **root** (ou `sudo`) no servidor.
- Repositório clonado num caminho fixo (ex.: `/root/runv-server` ou `/opt/runv/src`). Os exemplos abaixo assumem que o diretório raiz do clone é `REPO` — substitua pelo caminho real.

**Convenções de caminhos no servidor**

| Caminho | Função |
|--------|--------|
| `/var/lib/runv/users.json` | Metadados dos utilizadores (criado na primeira operação que o use) |
| `/var/lib/runv/users.lock` | Lock para escrita segura em `users.json` |
| `/var/lib/runv/entre-queue` | Fila de pedidos do SSH «entre» |
| `/var/log/runv/` | Logs do terminal `entre` |
| `/opt/runv/terminal/` | Cópia instalada do módulo `terminal/` |

---

## Ordem geral (resumo)

1. **Bootstrap do sistema** — `scripts/admin/starthere.py` (Apache, SSH, firewall, quotas, pacotes base).
2. **Ferramentas e ficheiros globais** — `tools/tools.py` (MOTD, skel, binários, pacotes do manifest).
3. **Site Apache / landing** — `site/genlanding.py`.
4. **Dados públicos da landing** — `site/build_directory.py` (idealmente em **cron**).
5. **Email de saída (msmtp)** — `email/configure_msmtp.py` (+ documentação em `email/docs/`).
6. **SSH restrito «entre»** — `terminal/setup_entre.py`.
7. **Operação** — `create_runv_user.py`, `update_user.py`, `del-user.py` (e só em cenários controlados: `scripts/doom/doom.py`).

Os passos 2–6 podem ser ajustados conforme já tiveres Apache ou email configurados; a ordem acima minimiza dependências (Apache antes de publicar; `users.json` antes do cron que o lê).

---

## 1. Bootstrap: `starthere.py`

**Objetivo:** instalar e preparar Apache, OpenSSH, UFW, quotas, pacotes úteis e hardening básico.

```bash
cd REPO/scripts/admin
sudo python3 starthere.py --help   # rever opções
sudo python3 starthere.py          # ou com flags que precisares
```

**Nota:** este script **não** configura msmtp nem o utilizador `entre`. Consulta também os Markdown em `scripts/docs/` se existirem no teu clone.

---

## 2. Ferramentas globais: `tools/tools.py`

**Objetivo:** aplicar manifest de pacotes APT, scripts em `/usr/local/bin`, MOTD, skel de utilizador, etc.

```bash
cd REPO/tools
sudo python3 tools.py --help
sudo python3 tools.py              # execução real (requer root conforme o script)
```

Detalhes: `tools/docs/INSTALL.md` (se presente).

---

## 3. Landing Apache: `genlanding.py`

**Objetivo:** virtual host, site estático, opcionalmente Certbot.

```bash
cd REPO/site
sudo python3 genlanding.py --help
sudo python3 genlanding.py --domain runv.club   # exemplo; ajustar domínio e flags
```

Garante que o DNS aponta para o servidor antes de TLS com Certbot.

---

## 4. Dados públicos: `build_directory.py`

**Objetivo:** gerar ficheiros consumidos pela landing a partir de `/var/lib/runv/users.json`.

```bash
cd REPO/site
python3 build_directory.py --help
```

**Cron (exemplo)** — executar como utilizador com permissão de leitura a `users.json` e escrita no destino web:

```cron
*/15 * * * * cd /caminho/para/REPO/site && /usr/bin/python3 build_directory.py
```

Ajusta intervalo e caminhos conforme a política do servidor.

---

## 5. Email (msmtp + mail): `email/configure_msmtp.py`

**Objetivo:** pacotes (`msmtp-mta`, `bsd-mailx` ou equivalente), `msmtprc`, `~/.netrc` ou segredo adequado, aliases, testes.

```bash
cd REPO/email
sudo python3 configure_msmtp.py --help
sudo python3 configure_msmtp.py --dry-run    # simular
sudo python3 configure_msmtp.py              # aplicar (root)
```

Documentação completa:

- `email/docs/INSTALL.md`
- `email/docs/ADMIN.md`, `TROUBLESHOOTING.md`, `INTEGRATION.md`
- `email/README.md`

Scripts auxiliares: `email/scripts/send_test_mail.sh`, `email/scripts/diagnose_msmtp.sh`.

---

## 6. Terminal SSH «entre»: `setup_entre.py`

**Objetivo:** utilizador `entre`, cópia do módulo para `/opt/runv/terminal`, drop-in `sshd_config`, filas e logs.

```bash
cd REPO/terminal
sudo python3 setup_entre.py --help
sudo python3 setup_entre.py
```

- Coloca chaves em `~entre/.ssh/authorized_keys` antes de confiar em acessos.
- Integração com email (avisos): `email/docs/INTEGRATION.md` e `terminal/docs/INSTALL.md`.

Arranque do serviço Python (systemd ou manual) está descrito na documentação do terminal.

---

## 7. Operação: contas runv

Todos em `REPO/scripts/admin/` (executar como **root** salvo indicação em contrário).

| Script | Uso |
|--------|-----|
| `create_runv_user.py` | Criar utilizador Unix + home + quota + entrada em `users.json` |
| `update_user.py` | Atualizar metadados / quota / estado |
| `del-user.py` | Remover utilizador e limpar metadados (com locks e confirmações) |

**Ordem típica na vida real:** após infraestrutura (passos 1–6), usas `create_runv_user.py` para cada membro; `build_directory.py` (cron) mantém o site alinhado com `users.json`.

### `scripts/doom/doom.py` (perigoso)

Remove **todas** as contas listadas em `users.json` exceto a indicada por `--keep`. Só em ambientes de teste ou com backups e confirmação explícita.

```bash
cd REPO/scripts/doom
sudo python3 doom.py --help
```

---

## Verificação rápida (checklist)

- [ ] `sshd -t` sem erros após drop-in do `entre`.
- [ ] `apache2ctl configtest` / `apachectl configtest` OK após `genlanding.py`.
- [ ] `systemctl status apache2` e `ssh` ativos.
- [ ] Email: `send_test_mail.sh` ou equivalente a partir da documentação do email.
- [ ] Ficheiro `users.json` coerente e `build_directory.py` gera saída esperada.
- [ ] Login SSH como `entre` executa apenas o menu esperado (ForceCommand).

---

## Documentação por pasta

| Pasta | Documentos |
|-------|------------|
| `email/` | `README.md`, `docs/INSTALL.md`, `ADMIN.md`, … |
| `terminal/` | `docs/INSTALL.md` |
| `tools/` | `docs/INSTALL.md` |
| `scripts/` | `docs/*.md` (conforme o repositório) |

---

## Nota sobre o código Python

Os scripts usam `subprocess` com **listas de argumentos** (sem `shell=True` nas invocações analisadas), o que reduz risco de injeção de comando. Antes de atualizar em produção, convém correr `python3 -m compileall` na raiz do repositório e testar com `--dry-run` onde o script o suportar.
