# Email runv.club — envio via Mailgun HTTP API (predefinido)

**Aviso: o configurador predefinido foi feito para Mailgun.** Não pré-configura credenciais.

Subsistema **só de envio** para Debian 13: por omissão grava estado em `/etc/runv-email.json` e segredos em `/etc/runv-email.secrets.json`, e envia mensagens pela **API HTTP Mailgun** (Basic Auth `api` + API key). Opcionalmente mantém um modo **legado** com `msmtp` + `sendmail`.

## O que faz (predefinido)

- Configura envio **sem** Postfix/Exim/Dovecot — **não** é um MTA completo.
- **Não** recebe email (sem IMAP, sem caixa local).
- Biblioteca Python reutilizável (`lib/mailer.py`) com templates em texto puro; suporte opcional a corpo **HTML** no `send_mail`.

## O que instala (APT) — só modo legado SMTP

| Pacote | Papel |
|--------|-------|
| `msmtp` | Cliente SMTP. |
| `msmtp-mta` | Fornece `/usr/sbin/sendmail`. |
| `ca-certificates` | Confiança TLS. |
| `bsd-mailx` | Comando `mail` para testes em CLI. |

**Mailgun API (predefinido)** não exige estes pacotes.

## Execução rápida

```bash
cd /caminho/runv-server/email
sudo python3 configure_mailgun.py
```

Legado SMTP:

```bash
sudo python3 configure_mailgun.py --legacy-smtp
# ou: sudo python3 configure_msmtp_legacy.py
```

O ficheiro `configure_msmtp.py` apenas **indica** estes comandos (substituição do antigo fluxo).

Flags: `--dry-run`, `--verbose`, `--force`, `--test`, `--legacy-smtp`. Detalhes: [docs/INSTALL.md](docs/INSTALL.md).

## Documentação

| Ficheiro | Conteúdo |
|----------|-----------|
| [docs/INSTALL.md](docs/INSTALL.md) | Mailgun vs legado, ficheiros, flags, testes, variáveis de ambiente. |
| [docs/ADMIN.md](docs/ADMIN.md) | Alterar remetente, admin, segredos. |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Falhas comuns. |
| [docs/INTEGRATION.md](docs/INTEGRATION.md) | `lib/mailer.py`, eventos, `entre`. |

## Biblioteca

Defina `RUNV_EMAIL_ROOT` para a pasta `email/` do repositório (onde estão `lib/` e `templates/`) e importe `lib.mailer`. O configurador grava também `email_package_root` em `/etc/runv-email.json` para o serviço `entre` encontrar o módulo sem variável de ambiente.

## Checklist manual de verificação (Mailgun)

- [ ] `sudo ls -l /etc/runv-email.json /etc/runv-email.secrets.json` — **0600**, root.
- [ ] `sudo python3 configure_mailgun.py --test` — email de teste recebido.
- [ ] `email_package_root` no JSON aponta para a pasta `email/` do deploy (para notificações `entre`).
- [ ] Fluxo `entre` com `admin_email` no `config.toml` — notificação ao admin (Mailgun ou sendmail de fallback).

## Scripts auxiliares (legado / diagnóstico)

- `scripts/diagnose_msmtp.sh` — diagnóstico msmtp (modo SMTP).
- `scripts/send_test_mail.sh` — teste via `mail`.
- `scripts/netrc_password.py` — usado por `passwordeval` no msmtp (só legado).

Versão do módulo alinhada ao repositório runv-server.
