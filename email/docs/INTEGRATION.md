# Integração — email com o resto do runv-server

## Variável de ambiente

Defina **`RUNV_EMAIL_ROOT`** como caminho absoluto para a pasta **`email/`** do repositório (a que contém `lib/` e `templates/`).

```bash
export RUNV_EMAIL_ROOT=/srv/runv-server/email
```

Em Python, antes de importar:

```python
import os
import sys
ROOT = "/srv/runv-server/email"
os.environ.setdefault("RUNV_EMAIL_ROOT", ROOT)
sys.path.insert(0, ROOT)
from lib.mailer import (
    send_mail,
    send_admin_notice,
    send_user_notice,
    render_template,
)
from lib import templates as T
```

**Nunca** use `shell=True` em `subprocess` para envio; a biblioteca já invoca `sendmail` com lista de argumentos.

## API resumida (`lib/mailer.py`)

| Função | Uso |
|--------|-----|
| `render_template(nome, **kwargs)` | Lê `templates/<nome>.txt` e substitui `{placeholders}`. |
| `send_mail(to, subject, body, from_addr=..., sendmail=..., headers=...)` | Mensagem texto; `to` pode ser string ou lista. |
| `send_admin_notice(template, admin_email, subject=..., from_addr=..., **kwargs)` | Template → admin. |
| `send_user_notice(template, user_email, subject=..., from_addr=..., **kwargs)` | Template → utilizador. |

`sendmail` por defeito: `/usr/sbin/sendmail` (msmtp-mta).

## Mapa evento → template → script

| Evento | Template(s) | Onde disparar |
|--------|-------------|----------------|
| Novo pedido na fila `entre` | `admin_new_request` → admin; opcional `user_request_received` → email do visitante | Após `save_request_json` em [`terminal/entre_core.py`](../../terminal/entre_core.py) / [`entre_app.py`](../../terminal/entre_app.py). **Hoje** só há email admin via `sendmail_notify` + `admin_mail.txt` — manter compatível ou migrar para templates deste módulo. |
| Pedido aprovado (manual) | `user_approved` | Processo admin / script que marca pedido aprovado. |
| Pedido rejeitado | `user_rejected` (+ `reason`) | Idem. |
| Conta criada | `admin_user_created`, `user_account_created` | Final com sucesso de [`scripts/admin/create_runv_user.py`](../../scripts/admin/create_runv_user.py). |
| Conta removida | `admin_user_deleted`, `user_account_removed` | Final de [`scripts/admin/del-user.py`](../../scripts/admin/del-user.py) (se tiver email em metadados para o utilizador). |
| Erro operacional | `admin_error` | Blocos `except` em scripts admin ou cron. |
| Quota | `user_quota_warning` | Monitorização de disco / `update_user` / quotas. |
| Teste | `system_test` | `configure_msmtp.py --test` ou scripts de CI manual. |

## Fluxo **entre** (terminal)

- **Comportamento actual:** [`entre_core.sendmail_notify`](../../terminal/entre_core.py) envia corpo já montado a partir de `templates/admin_mail.txt`, via `sendmail -t -i`.
- **Compatibilidade:** Depois de configurar este módulo, `/usr/sbin/sendmail` passa a ser o msmtp — **nenhuma alteração obrigatória** no código `entre` se `sendmail_path` em `config.toml` for `/usr/sbin/sendmail`.
- **Opcional:** Unificar com `send_admin_notice(T.ADMIN_NEW_REQUEST, ...)` e placeholders alinhados ao JSON do pedido — exige refactor pequeno em `entre_app.py` e testes.

### Exemplo (opcional) — notificação admin com template do módulo

```python
# Pseudocódigo: após gravação do pedido
send_admin_notice(
    T.ADMIN_NEW_REQUEST,
    admin_email,
    subject="[runv.club] Novo pedido",
    from_addr=mail_from,
    request_id=request_id,
    timestamp=...,
    username=username,
    email=email,
    fingerprint=fingerprint,
)
```

Para email ao **visitante** (`user_request_received`), é preciso endereço válido do utilizador (já recolhido no fluxo).

## `create_runv_user.py`

Após criação bem-sucedida da conta (e sabendo `email` metadado e `admin_email` de config ou estado):

```python
send_admin_notice(
    T.ADMIN_USER_CREATED,
    admin_email,
    subject="[runv.club] Conta criada",
    from_addr=default_from,
    username=username,
    email=user_email,
    operator_info="create_runv_user.py",
    timestamp=str(int(time.time())),
)
send_user_notice(
    T.USER_ACCOUNT_CREATED,
    user_email,
    subject="[runv.club] A sua conta",
    from_addr=default_from,
    username=username,
    email=user_email,
)
```

Obtenha `admin_email` / `default_from` de `/etc/runv-email.json` ou de variáveis de ambiente definidas pelo operador — **não** hardcodar.

## `del-user.py`

Após remoção bem-sucedida:

- `send_admin_notice(T.ADMIN_USER_DELETED, ...)`
- Se existir email de contacto em metadados: `send_user_notice(T.USER_ACCOUNT_REMOVED, ...)`.

## Configuração paralela com `entre`

| Ficheiro | Campos |
|----------|--------|
| `/etc/runv-email.json` | `admin_email`, `default_from` — estado global runv. |
| `/opt/runv/terminal/config.toml` | `admin_email`, `mail_from`, `sendmail_path` — fluxo entre. |

Recomenda-se manter **o mesmo** `admin_email` e remetente coerente entre ambos.

## Checklist de integração

- [ ] `RUNV_EMAIL_ROOT` definido em cron/systemd que invoque scripts Python.
- [ ] `sendmail` = msmtp testado com `configure_msmtp.py --test`.
- [ ] Templates revistos (português, placeholders).
- [ ] Nenhum segredo em logs ou `print()`.
