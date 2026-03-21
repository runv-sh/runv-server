# Integração — email com o resto do runv-server

**Predefinição:** envio via **Mailgun HTTP API** quando `/etc/runv-email.json` indica `backend: mailgun` (ou contém `mailgun_domain` + `mailgun_region` sem `backend: sendmail`). Caso contrário, `lib.mailer` usa **sendmail** (msmtp legado).

## Variável de ambiente

Defina **`RUNV_EMAIL_ROOT`** como caminho absoluto para a pasta **`email/`** do repositório (a que contém `lib/` e `templates/`).

```bash
export RUNV_EMAIL_ROOT=/srv/runv-server/email
```

O configurador Mailgun grava também **`email_package_root`** em `/etc/runv-email.json`. O fluxo **`entre`** usa esse campo (ou `RUNV_EMAIL_ROOT`) para importar `lib.mailer` e enviar via API quando Mailgun está activo.

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

**Nunca** use `shell=True` em `subprocess` para envio; a biblioteca usa urllib (Mailgun) ou `sendmail` com lista de argumentos.

## API resumida (`lib/mailer.py`)

| Função | Uso |
|--------|-----|
| `render_template(nome, **kwargs)` | Lê `templates/<nome>.txt` e substitui `{placeholders}`. |
| `send_mail(to, subject, body, from_addr=..., html=..., sendmail=..., headers=..., _state=...)` | Texto; `html` opcional (Mailgun). `to` string ou lista. `_state` evita reler disco (testes / entre). |
| `send_admin_notice(..., html_body=...)` | Template → admin. |
| `send_user_notice(..., html_body=...)` | Template → utilizador. |

Com **Mailgun**, `sendmail` é ignorado para o transporte (usa API). Com **legado**, `sendmail` por defeito: `/usr/sbin/sendmail`.

## Mapa evento → template → script

| Evento | Template(s) | Onde disparar |
|--------|-------------|----------------|
| Novo pedido na fila `entre` | Corpo do email: [`terminal/templates/admin_mail.txt`](../../terminal/templates/admin_mail.txt) (não `email/templates/admin_new_request.txt`). Opcional: `user_request_received` existe em `email/templates/` mas **não** está ligado ao `entre`. | Após `save_request_json` em [`terminal/entre_core.py`](../../terminal/entre_core.py) / [`entre_app.py`](../../terminal/entre_app.py). Email admin via `sendmail_notify`; com Mailgun, tenta **primeiro** `lib.mailer.send_mail` se `/etc/runv-email.json` e `email_package_root` / `RUNV_EMAIL_ROOT` forem válidos. |
| Pedido aprovado (manual) | `user_approved` | Processo admin (manual / futuro). |
| Pedido rejeitado | `user_rejected` (+ `reason`) | Idem. |
| Conta criada | `admin_user_created` → admin; `user_account_created` → utilizador | [`scripts/admin/create_runv_user.py`](../../scripts/admin/create_runv_user.py): `--no-welcome-email` / `--no-admin-create-email` para desactivar cada ramo. |
| Conta removida / banimento | `user_account_community_deactivated` → utilizador | [`scripts/admin/del-user.py`](../../scripts/admin/del-user.py): envia por omissão se existir email em `users.json` e `/etc/runv-email.json` válido; `--no-ban-notify-email` desactiva. Templates `admin_user_deleted` / `user_account_removed` existem mas **não** estão ligados a este script. |
| Erro operacional | `admin_error` | Scripts admin / cron. |
| Quota | `user_quota_warning` | Monitorização / quotas. |
| Teste | `system_test` | `configure_mailgun.py --test` (API) ou legado. |

## Fluxo **entre** (terminal)

- **`entre_core.sendmail_notify`** tenta primeiro envio **Mailgun** se `/etc/runv-email.json` for compatível e se `email_package_root` ou `RUNV_EMAIL_ROOT` permitir importar `lib.mailer`.
- Se Mailgun não aplicável ou falhar o ramo API, usa **`sendmail -t -i`** como antes (requer msmtp-mta no modo legado).

### Coerência de configuração

| Ficheiro | Campos |
|----------|--------|
| `/etc/runv-email.json` | `backend`, `admin_email`, `default_from`, Mailgun (`mailgun_domain`, …) ou SMTP (`smtp_host`, …), `email_package_root`. |
| `/opt/runv/terminal/config.toml` | `admin_email`, `mail_from`, `sendmail_path` — fluxo entre. |

Recomenda-se o **mesmo** `admin_email` e remetente coerente com o Mailgun/domínio verificado.

## `create_runv_user.py` / `del-user.py`

O **`create_runv_user.py`** envia por omissão:

1. **Boas-vindas** ao utilizador (`user_account_created`), com instruções SSH; `--no-welcome-email` desactiva.
2. **Aviso ao admin** (`admin_user_created` para `admin_email` no JSON); `--no-admin-create-email` desactiva.

Requer `/etc/runv-email.json` (com `default_from`, `admin_email` para o ramo admin), segredos Mailgun se aplicável, e pasta `email/` acessível (`email_package_root` ou `RUNV_EMAIL_ROOT`). Para o texto de boas-vindas, `--welcome-ssh-host` ou `RUNV_WELCOME_SSH_HOST` define o hostname SSH sugerido.

Obtenha `admin_email` / `default_from` de `/etc/runv-email.json` — **não** hardcodar.

O **`del-user.py`** envia **`user_account_community_deactivated`** ao endereço no campo `email` do registo em `/var/lib/runv/users.json` (lido **antes** de apagar o registo), com texto de desativação por descumprimento das normas da comunidade. Requer `default_from` e pasta `email/` acessível (`RUNV_EMAIL_ROOT` ou `email_package_root`). Com `--skip-metadata` ainda tenta ler o ficheiro de metadados para obter o email.

## Checklist de integração

- [ ] `RUNV_EMAIL_ROOT` ou `email_package_root` correcto para serviços Python e **entre**.
- [ ] `sudo python3 configure_mailgun.py --test` (ou legado) com sucesso.
- [ ] Templates revistos (português, placeholders).
- [ ] Nenhum segredo em logs ou `print()` (API key só em ficheiro 0600 ou env).

Roteiro passo a passo no servidor: [VERIFICATION_CHECKLIST.md](VERIFICATION_CHECKLIST.md).
