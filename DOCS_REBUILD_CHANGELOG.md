# Changelog da reconstrução da documentação (runv-server)

Documento em **pt-BR**. Data da passagem: conforme o commit em que este ficheiro foi adicionado.

## Ficheiros criados (canónico `docs/`)

| Ficheiro | Função |
|----------|--------|
| [docs/README.md](docs/README.md) | Porta de entrada, ordem de leitura, mapa rápido |
| [docs/00-overview.md](docs/00-overview.md) | Visão geral, limites público/privado, fontes de verdade |
| [docs/01-server-baseline-debian.md](docs/01-server-baseline-debian.md) | Debian, tempo, locale, pré-requisitos |
| [docs/02-admin-access-and-ssh.md](docs/02-admin-access-and-ssh.md) | Modelo root/admin, SSH |
| [docs/03-paths-files-and-state.md](docs/03-paths-files-and-state.md) | Caminhos `/var/lib/runv`, logs, email, web |
| [docs/04-bootstrap-and-base-system.md](docs/04-bootstrap-and-base-system.md) | `starthere.py`, quotas ext4, Apache, UFW |
| [docs/05-tools-and-system-experience.md](docs/05-tools-and-system-experience.md) | `tools.py`, MOTD, skel, jail SSH |
| [docs/06-site-and-apache.md](docs/06-site-and-apache.md) | `genlanding.py`, DocumentRoot, TLS |
| [docs/07-public-members-directory.md](docs/07-public-members-directory.md) | `build_directory.py`, `members.json`, privacidade |
| [docs/08-email.md](docs/08-email.md) | Mailgun, legado msmtp, ficheiros de estado |
| [docs/09-terminal-entre.md](docs/09-terminal-entre.md) | Conta `entre`, fila, limites (não provisiona Unix) |
| [docs/10-user-provisioning-and-admin-ops.md](docs/10-user-provisioning-and-admin-ops.md) | `create_runv_user.py`, fluxo de aprovação |
| [docs/11-daily-operations.md](docs/11-daily-operations.md) | Operação corrente |
| [docs/12-security-and-privacy.md](docs/12-security-and-privacy.md) | Confiança, dados sensíveis |
| [docs/13-troubleshooting.md](docs/13-troubleshooting.md) | Erros frequentes |
| [docs/14-smoke-tests-and-validation.md](docs/14-smoke-tests-and-validation.md) | Verificações seguras |
| [docs/15-glossary-and-reference.md](docs/15-glossary-and-reference.md) | Glossário, índice de scripts |
| [docs/diagrams/architecture.mmd](docs/diagrams/architecture.mmd) | Sequência SSH entre → fila (Mermaid) |
| [docs/diagrams/member-flow.mmd](docs/diagrams/member-flow.mmd) | Fluxo pedido → admin → dados públicos (Mermaid) |

## Actualizações posteriores (código + docs)

- **`genlanding.py --sync-public-only`:** cópia de `site/public/` para o DocumentRoot + `members.json`, sem reconfigurar Apache (`site/genlanding.py` v0.05).
- **`create_runv_user.py`:** após criar membro, invoca esse modo em vez de só `build_directory.py`; `--no-refresh-landing-members` omite cópia e JSON.
- **MOTD** [`tools/motd/60-runv`](tools/motd/60-runv): título “Últimos usuários online” sem o sufixo explicativo entre parêntesis.
- Documentação actualizada: `docs/06`, `docs/07`, `docs/10`, `docs/11`, `docs/13`, `docs/15`.

---

Alteração mínima **fora** de `docs/` para não quebrar referências em código ou templates (reconstrução inicial):

- [README.md](README.md) (raiz): ponteiro para `docs/README.md`.
- `tools/tools.py`, `site/build_directory.py`, `email/configure_mailgun.py`, `email/configure_msmtp_legacy.py`: docstrings / mensagens apontam para `docs/…` em vez de `.md` removidos nos módulos.
- `terminal/templates/admin_mail.txt`: linha de ajuda ao admin aponta para `docs/10-user-provisioning-and-admin-ops.md` (antes referia `terminal/docs/ADMIN.md`, removido).

**Nota:** existiu cópia errónea em `dev-notes/DOCS_REBUILD_CHANGELOG.md`; foi removida — a versão canónica é **sempre** este ficheiro na raiz.

## Fontes de evidência usadas

- Código Python em `scripts/admin/`, `terminal/`, `site/`, `tools/`, `email/`, `patches/`.
- `terminal/config.example.toml`, exemplos em `site/example-users.json`.
- Documentação modular **antes da remoção**: `INSTALL.md` (raiz), `site/*.md`, `terminal/docs/*.md`, `tools/docs/*.md`, `email/docs/*.md`, `scripts/**/*.md`, `dev-notes/RUNV_CURRENT_STATE_AUDIT.md`.
- `terminal/docs/ARCHITECTURE.md` (fluxo e componentes).
- Diff e defaults nos scripts (caminhos predefinidos, flags).

## Contradições identificadas e como foram tratadas

1. **Cron vs refresh “sem cron”**  
   - `INSTALL.md` sugeria exemplo de cron para `build_directory.py`.  
   - `site/README.md` enfatizava refresh via `create_runv_user.py` / `genlanding.py` sem cron.  
   - **Resolução:** em `docs/07-public-members-directory.md` (e operações diárias) ficam explícitos **dois modos válidos**: regeneração automática nos fluxos de provisionamento/landing **ou** cron/manual — não são mutuamente exclusivos.

2. **`USO.md` inexistente**  
   - `terminal/docs/ARCHITECTURE.md` referia `USO.md`, que não existia no repositório.  
   - **Resolução:** descrito em `docs/09-terminal-entre.md` e neste changelog; o fluxo cobre-se nos docs canónicos.

3. **Múltiplos `INSTALL.md` por módulo**  
   - Conteúdo sobreposto entre raiz e `tools/`, `email/`, `terminal/`.  
   - **Resolução:** um único percurso numerado em `docs/01`–`docs/11`, com secções por componente.

## O que ficou explicitamente **NÃO VERIFICADO** neste ambiente

- Execução de `--help` e comportamento em runtime de `scripts/admin/create_runv_user.py`, `terminal/setup_entre.py` e `site/genlanding.py` em **Windows**: falham no import (`fcntl` / `grp` inexistentes). **Verificação plena:** correr em **Debian/Linux** alvo.
- Estado real de um servidor de produção (Apache vhosts, TLS, quotas aplicadas, conteúdo de `/var/lib/runv/users.json`): apenas inferência a partir de defaults no código — qualquer deploy concreto deve ser confirmado no servidor.

## Verificações executadas (2026-03-22, Windows / PowerShell)

| Comando | Resultado |
|---------|-----------|
| `python -m compileall -q scripts terminal site tools email patches` | Exit 0 |
| `cd email && python -m pytest tests/ -q` | 11 passed |
| `python site/build_directory.py --users-json site/example-users.json --dry-run` | JSON válido no stdout (`username`, `since`, `path`) |
| `python site/build_directory.py --help` | Exit 0 |
| `python email/configure_mailgun.py --help` | Exit 0 |
| `python scripts/admin/create_runv_user.py --help` | **Falha:** `ModuleNotFoundError: fcntl` |
| `python terminal/setup_entre.py --help` | **Falha:** `ModuleNotFoundError: grp` |
| `python site/genlanding.py --help` | **Falha:** `ModuleNotFoundError: grp` |
| `git status -sb` | Registado no momento da passagem (working tree com `docs/` e alterações pendentes) |

## Pressupostos dependentes do ambiente (operador)

- **Um único host Debian** com paths tipo `/var/www/runv.club/html`, `/var/lib/runv/`, `/opt/runv/terminal/` — são defaults no código; outros caminhos exigem flags explícitas.
- **Root/sudo** para bootstrap, `tools.py`, email, `entre`, provisionamento de utilizadores.
- **Decisões de segurança** (firewall, TLS, política de passwords SSH) combinam o que o repo automatiza com o que o operador mantém — ver `docs/02` e `docs/12`.

## Documentação `.md` removida nesta reconstrução

Removidos de propósito para evitar duplicação e contradições com `docs/` (lista não exaustiva de paths relativos à raiz do repo):

- `INSTALL.md`
- `dev-notes/RUNV_MEMBER_BUBBLE_CHANGELOG.md` (changelog local; conteúdo operacional relevante está em `docs/07` e `docs/10`)
- `dev-notes/RUNV_CURRENT_STATE_AUDIT.md`
- `site/README.md`, `site/build_directory.md`, `site/genlanding.md`, `site/news/README.md`
- `terminal/README.md`, `terminal/docs/INSTALL.md`, `terminal/docs/ARCHITECTURE.md`, `terminal/docs/ADMIN.md`
- `tools/README.md`, `tools/skel/README.md`, `tools/docs/INSTALL.md`, `tools/docs/ADMIN.md`, `tools/docs/USER_EXPERIENCE.md`
- `email/README.md`, `email/docs/INSTALL.md`, `email/docs/ADMIN.md`, `email/docs/INTEGRATION.md`, `email/docs/TROUBLESHOOTING.md`
- `scripts/starthere.md`, `scripts/skel.md`, `scripts/create_runv_user.md`, `scripts/del-user.md`, `scripts/admin/perm1.md`, `scripts/doom/doom.md`, `scripts/docs/*.md`

**Não removido:** `email/.pytest_cache/README.md` (artefacto gerado por pytest; não é documentação do produto).

## Adequação para um operador novo

A documentação é **utilizável** para alguém que não escreveu o código, desde que leia `docs/README.md` na ordem sugerida e execute verificações em **Debian** onde os scripts Unix são relevantes. Lacunas conhecidas estão marcadas como NÃO VERIFICADO ou recomendação, sem afirmar CI/deploy que não exista no repositório.
