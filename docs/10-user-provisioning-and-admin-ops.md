# Provisionamento de utilizadores e operações admin

[← Índice](README.md)

## Fonte canónica: `scripts/admin/create_runv_user.py`

- **Único** script de criação de **membros** com a política completa (docstring longa no ficheiro): `adduser`, chaves, `public_html` / gopher / gemini, permissões, jail (Jailkit), quota, metadados em `users.json`.
- Executar como **root** no servidor Debian.

## Pós-criação: constelação

- Flag `--landing-document-root` (default `/var/www/runv.club/html`): se o directório **existir**, corre `build_directory.py` para `data/members.json` (salvo `--no-refresh-landing-members`).
- Saída explícita para o operador: linha de **sucesso** com contagem ou **AVISO** com comando sugerido se path em falta ou falha (**código actual**).

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
