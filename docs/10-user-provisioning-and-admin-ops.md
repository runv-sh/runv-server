# Provisionamento de utilizadores e operações admin

[← Índice](README.md)

## Fonte canónica: `scripts/admin/create_runv_user.py`

- **Único** script de criação de **membros** com a política completa (docstring longa no ficheiro): `adduser`, chaves, `public_html` / gopher / gemini, permissões, jail (Jailkit), quota, metadados em `users.json`.
- Executar como **root** no servidor Debian.

## Pós-criação: landing pública e constelação

- **`genlanding.py` completo** continua necessário para a **primeira** montagem do site (VirtualHost Apache, módulos, cópia inicial). Não é preciso repetir esse fluxo **a cada** novo membro.
- Flag **`--landing-document-root`** (default `/var/www/runv.club/html`): se o directório **existir**, após gravar `users.json` o script invoca **`site/genlanding.py --sync-public-only`** — recopia `site/public/` para o DocumentRoot, aplica `chown` a `www-data` e regenera `data/members.json` via `build_directory.py` interno ao genlanding.
- **`--no-refresh-landing-members`:** omite toda essa sincronização (nem cópia de `public/` nem `members.json`).
- Saída para o operador: linha **`landing (public + bolhas): sincronizado`** com contagem opcional, ou **AVISO** com comando manual (`genlanding.py --sync-public-only …`) se o DocumentRoot não existir ou o subprocess falhar.

## Outros scripts admin

| Script | Uso |
|--------|-----|
| `update_user.py` | Actualizar metadados / quota / estado (`users.json` com lock) |
| `del-user.py` | Remover utilizador e metadados |
| `setup_alt_protocols.py` | Reparar protocolos para contas criadas fora do fluxo |
| `scripts/doom/doom.py` | **Perigoso:** remove contas em massa; só testes / com backup |

## Fluxo de aprovação

1. JSON na fila `entre-queue/`.
2. Admin valida manualmente.
3. `create_runv_user.py` com dados aprovados.
4. Refresh público conforme [07](07-public-members-directory.md).

Próximo: [11-daily-operations.md](11-daily-operations.md).
