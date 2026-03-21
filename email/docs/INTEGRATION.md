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
| Novo pedido na fila `entre` | `admin_new_request` → admin; opcional `user_request_received` → visitante | Após `save_request_json` em [`terminal/entre_core.py`](../../terminal/entre_core.py) / [`entre_app.py`](../../terminal/entre_app.py). **Hoje** email admin via `sendmail_notify` + `admin_mail.txt` — com Mailgun, `sendmail_notify` tenta **primeiro** a API se o estado global o indicar. |
| Pedido aprovado (manual) | `user_approved` | Processo admin. |
| Pedido rejeitado | `user_rejected` (+ `reason`) | Idem. |
| Conta criada | `admin_user_created`, `user_account_created` | [`scripts/admin/create_runv_user.py`](../../scripts/admin/create_runv_user.py). |
| Conta removida | `admin_user_deleted`, `user_account_removed` | [`scripts/admin/del-user.py`](../../scripts/admin/del-user.py). |
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

O **`create_runv_user.py`** envia por omissão um email de **boas-vindas** ao utilizador (`user_account_created`), com instruções para aceder por SSH com a **chave privada** correspondente à chave pública registada. Requer `/etc/runv-email.json` e módulo `email/` acessível; `--no-welcome-email` para desactivar; `--welcome-ssh-host` ou `RUNV_WELCOME_SSH_HOST` para um comando `ssh` explícito.

Obtenha `admin_email` / `default_from` de `/etc/runv-email.json` — **não** hardcodar.

Ver exemplos na versão anterior deste documento para `send_admin_notice` / `send_user_notice` adicionais.

## Checklist de integração

- [ ] `RUNV_EMAIL_ROOT` ou `email_package_root` correcto para serviços Python e **entre**.
- [ ] `sudo python3 configure_mailgun.py --test` (ou legado) com sucesso.
- [ ] Templates revistos (português, placeholders).
- [ ] Nenhum segredo em logs ou `print()` (API key só em ficheiro 0600 ou env).
