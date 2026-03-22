# Directório público de membros

[← Índice](README.md)

## Script: `site/build_directory.py`

- **Entrada:** `--users-json` (default `/var/lib/runv/users.json`) — deve ser uma **lista** JSON de objectos.
- **Saída:** `-o` / `--output` (default no repo: `site/public/data/members.json`; em produção típico: `DocumentRoot/data/members.json`).

## Schema público (campos escritos)

Cada elemento do array gerado contém:

| Campo | Origem / notas |
|-------|------------------|
| `username` | De `users.json` |
| `since` | `created_at` se for string; senão `""` |
| `path` | `"/~username/"` |
| `homepage_mtime` | Opcional; só com `--homes-root` (ex. `/home`) |

**Privacidade:** o script **não** copia email, fingerprint SSH, quotas nem outros campos internos (**evidência:** lógica em `build_directory.py`, função `main`).

## Consumo no browser

- `site/public/assets/app.js`: `validMembers()` exige `username` e `path` (strings); `since` opcional para brilho visual.

## Quando regenerar

1. **Hooks:** `create_runv_user.py` (se DocumentRoot existir e refresh activo); `genlanding.py` após cópia (por omissão).
2. **Cron (opcional):** exemplo histórico em `INSTALL` — adequado se quiser actualização periódica sem depender só de criar utilizadores.
3. **Manual:**

```bash
python3 REPO/site/build_directory.py \
  --users-json /var/lib/runv/users.json \
  -o /var/www/runv.club/html/data/members.json
```

## Cron vs hooks (sem contradição)

- **Hooks** actualizam quando corres `create_runv_user` ou `genlanding`.
- **Cron** é **opcional** para alinhar site com `users.json` mesmo sem novos provisionamentos.

Próximo: [08-email.md](08-email.md).
