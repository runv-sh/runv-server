# Glossário e referência rápida

[← Índice](README.md)

## Glossário

| Termo | Significado |
|-------|-------------|
| **entre** | Utilizador SSH especial para pedidos de entrada; não cria membros. |
| **Fila** | Directório `/var/lib/runv/entre-queue/` com JSON por pedido. |
| **members.json** | Dataset **público** para a constelação na landing. |
| **users.json** | Metadados **internos** dos membros no servidor. |
| **DocumentRoot** | Raiz Apache onde `genlanding.py` copia `site/public/`. |
| **REPO** | Caminho do clone (ex. `/opt/runv/src`). |

## Índice de scripts (principal)

| Caminho | Descrição curta |
|---------|-----------------|
| `scripts/admin/starthere.py` | Bootstrap APT, Apache, UFW, quotas ext4 |
| `scripts/admin/create_runv_user.py` | Provisionamento canónico de membro |
| `scripts/admin/update_user.py` | Actualizar membro / metadados |
| `scripts/admin/del-user.py` | Remover membro |
| `tools/tools.py` | APT, MOTD, skel, binários locais |
| `site/genlanding.py` | Apache + cópia landing + refresh members; `--sync-public-only` só cópia `public/` + members (sem Apache) |
| `site/build_directory.py` | users.json → members.json público |
| `email/configure_mailgun.py` | Config email Mailgun / legado |
| `terminal/setup_entre.py` | Instalar fluxo `entre` |
| `terminal/entre_app.py` | App ForceCommand |
| `terminal/entre_core.py` | Núcleo validação/fila |

## Módulos (pastas)

- `scripts/admin/` — administração
- `site/` — web estático + geradores
- `tools/` — experiência global Debian
- `email/` — envio
- `terminal/` — SSH entre
- `patches/` — patches auxiliares (ex. IRC)

## Mapa de documentação

- **Canónico:** esta pasta `docs/`.
- **Changelog da reconstrução:** `DOCS_REBUILD_CHANGELOG.md` na raiz.
