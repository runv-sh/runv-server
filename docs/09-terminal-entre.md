# Terminal SSH «entre»

[← Índice](README.md)

## Papel

- Utilizador Unix especial **`entre`**: ao ligar por SSH, o OpenSSH executa **`ForceCommand`** → `entre_app.py`.
- **Recolhe** dados (username, email, presença online, chave pública), **valida** (`entre_core.py`), **grava** JSON na fila com criação exclusiva (`O_EXCL`), **regista** log, **opcionalmente** notifica admin por email.

## Limite explícito (facto de código)

- **`entre_app.py` / `entre_core.py` não criam contas Linux de membros.** O utilizador `entre` em si é criado por **`setup_entre.py`** com `useradd` — isso é **bootstrap do sistema**, não provisionamento de membro.

## Ficheiros principais

| Ficheiro | Função |
|----------|--------|
| `entre_app.py` | UI terminal, passos |
| `entre_core.py` | Config TOML, validação, fila, log, sendmail/Mailgun |
| `setup_entre.py` | Instalação: `entre`, `/opt/runv/terminal`, fila, logs, drop-in sshd, modos de auth |
| `config.example.toml` | Modelo; `config.toml` gerado, não versionado no mesmo sítio |
| `templates/*.txt` | Textos editáveis |
| `systemd/*.path`, `*.service` | Opcional (notificações) |

## Configuração

- `queue_dir` default `/var/lib/runv/entre-queue`
- `log_file` default `/var/log/runv/entre.log`
- Ver `terminal/config.example.toml`

## Modos de autenticação (`setup_entre.py`)

- Documentados na docstring: `shared-password`, `key-only`, `empty-password` (estilo tilde.town), com avisos de segurança explícitos no código.

## Documentação histórica

- O antigo `terminal/docs/ARCHITECTURE.md` referia `USO.md`, que **não existia** neste snapshot. O fluxo operacional está consolidado neste documento e em [10-user-provisioning-and-admin-ops.md](10-user-provisioning-and-admin-ops.md) (a documentação modular em `terminal/docs/` foi removida em favor de `docs/` — ver `DOCS_REBUILD_CHANGELOG.md` na raiz).

Diagrama de sequência: [diagrams/architecture.mmd](diagrams/architecture.mmd).

Próximo: [10-user-provisioning-and-admin-ops.md](10-user-provisioning-and-admin-ops.md).
