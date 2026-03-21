# Email runv.club — envio via msmtp + sendmail

Subsistema **só de envio** para Debian 13: instala `msmtp`, `msmtp-mta`, `ca-certificates` e `bsd-mailx`, configura `/etc/msmtprc` e credenciais em `/root/.netrc`, e oferece biblioteca Python reutilizável com templates em texto puro.

## O que faz

- Coloca `/usr/sbin/sendmail` compatível (via **msmtp-mta**) a apontar para um **SMTP externo** configurável.
- **Não** instala Postfix, Exim, Dovecot nem qualquer MTA completo.
- **Não** recebe email (sem IMAP, sem caixa local).

## O que instala (APT)

| Pacote | Papel |
|--------|--------|
| `msmtp` | Cliente SMTP. |
| `msmtp-mta` | Fornece `/usr/sbin/sendmail`. |
| `ca-certificates` | Confiança TLS. |
| `bsd-mailx` | Comando `mail` para testes em CLI (evita `mailutils`, que pode recomendar MTA local). |

## Execução rápida

```bash
cd /caminho/runv-server/email
sudo python3 configure_msmtp.py
```

Flags: `--dry-run`, `--verbose`, `--force`, `--test`, `--skip-apt`. Detalhes: [docs/INSTALL.md](docs/INSTALL.md).

## Documentação

| Ficheiro | Conteúdo |
|----------|-----------|
| [docs/INSTALL.md](docs/INSTALL.md) | Instalação, flags, verificação, testes. |
| [docs/ADMIN.md](docs/ADMIN.md) | Alterar SMTP, remetente, admin, aliases. |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Falhas comuns. |
| [docs/INTEGRATION.md](docs/INTEGRATION.md) | `lib/mailer.py`, eventos, scripts existentes. |

## Biblioteca

Defina `RUNV_EMAIL_ROOT` para a pasta `email/` do repositório (onde estão `lib/` e `templates/`) e importe `lib.mailer`.

## Checklist manual de verificação

- [ ] `dpkg -l msmtp msmtp-mta` — pacotes instalados.
- [ ] `readlink -f /usr/sbin/sendmail` — aponta para msmtp.
- [ ] `ls -l /etc/msmtprc /root/.netrc` — permissões 600, root.
- [ ] `sudo python3 configure_msmtp.py --test` — email de teste recebido.
- [ ] `echo corpo | mail -s assunto root` — chega ao alias do admin (se aliases configurados).
- [ ] Fluxo `entre` com `admin_email` no `config.toml` — notificação ao admin (regressão).

## Scripts auxiliares

- `scripts/diagnose_msmtp.sh` — diagnóstico sem segredos.
- `scripts/send_test_mail.sh` — teste via `mail`.
- `scripts/netrc_password.py` — usado por `passwordeval` no msmtp (instalado em `/usr/local/lib/runv-email/`).

Versão do módulo alinhada ao repositório runv-server.
