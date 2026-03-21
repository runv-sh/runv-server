# Instalação — módulo email runv.club

Debian 13 (ou próximo). **Apenas envio** — SMTP externo via **msmtp**; interface **`/usr/sbin/sendmail`**.

## Dependências

Instaladas automaticamente por `configure_msmtp.py`:

- `msmtp`, `msmtp-mta`, `ca-certificates`, `bsd-mailx`

**Porque `bsd-mailx` e não `mailutils`?** O meta-pacote `mailutils` no Debian **recomenda** `default-mta`, o que em instalações interativas pode puxar **Postfix ou Exim**. O objetivo aqui é **não** ter servidor de correio local — só um cliente que invoque `sendmail` (na prática msmtp).

## Pré-requisitos

- Acesso **root** ao servidor.
- Conta SMTP relay (qualquer fornecedor — não é assumido no código).
- Firewall a permitir saída TCP para o host/porta SMTP.

## Executar o instalador

```bash
cd /caminho/para/runv-server/email
sudo python3 configure_msmtp.py
```

O script pergunta (de forma genérica):

- host e porta SMTP;
- TLS e STARTTLS (sim/não);
- autenticação (sim/não), utilizador e senha/token (**não ecoa**);
- remetente padrão (From);
- email do administrador.

Gera (com backup se já existir):

| Ficheiro | Descrição |
|----------|-----------|
| `/etc/msmtprc` | Conta `runv`, `default : runv`, log, aliases. **0600** root. |
| `/root/.netrc` | Entrada `machine <host>` com `login` e `password`. **0600** root. |
| `/etc/msmtp_aliases` | `root`, `cron`, `default` → email do admin. **0644** root. |
| `/etc/runv-email.json` | Metadados **sem segredos** (`admin_email`, `default_from`, host) para `--test`. **0600** root. |
| `/usr/local/lib/runv-email/netrc_password.py` | Helper para `passwordeval` ler a senha do `.netrc`. |

## Flags

| Flag | Efeito |
|------|--------|
| `--dry-run` | Mostra acções; não grava ficheiros nem apt (exceto prompts interactivos). |
| `--verbose` / `-v` | Log DEBUG. |
| `--force` / `-f` | Sobrescreve sem confirmar. |
| `--test` | Só envia [system_test.txt](../templates/system_test.txt) usando estado existente. |
| `--skip-apt` | Não corre `apt-get` (útil se pacotes já instalados). |

Exemplo de teste após configuração:

```bash
sudo python3 configure_msmtp.py --test
```

## Verificar `/etc/msmtprc`

```bash
sudo ls -l /etc/msmtprc
sudo msmtp --version
# Conteúdo (sem partilhar publicamente):
# sudo cat /etc/msmtprc
```

Deve conter `tls_trust_file`, `account runv`, `account default : runv`, e se usar auth, `passwordeval` apontando para `/usr/local/lib/runv-email/netrc_password.py HOST`.

## Verificar `/root/.netrc`

```bash
sudo ls -l /root/.netrc   # deve ser -rw------- root root
```

A linha `machine` deve ser **exactamente** o mesmo hostname que o campo `host` no msmtprc (o helper recebe esse host como argumento).

## Verificar `sendmail`

```bash
ls -l /usr/sbin/sendmail
readlink -f /usr/sbin/sendmail
```

Deve resolver para o binário **msmtp** (pacote `msmtp-mta`).

## Testar envio

1. `sudo python3 configure_msmtp.py --test`
2. Ou: `sudo sh scripts/send_test_mail.sh admin@seu-dominio`
3. Ou linha directa (Python), com `RUNV_EMAIL_ROOT`:

```bash
sudo RUNV_EMAIL_ROOT=/caminho/runv-server/email python3 -c "
import sys
sys.path.insert(0, '/caminho/runv-server/email')
from lib.mailer import send_mail
send_mail('voce@exemplo.com', 'Teste', 'Corpo.', from_addr='noreply@exemplo.com')
"
```

## Aliases msmtp

O ficheiro `/etc/msmtp_aliases` usa o formato **msmtp** (`local: email@externo`). **Não** é o mesmo que aliases Sendmail; **`newaliases` não aplica** aqui. Qualquer alteração: editar o ficheiro e manter coerência com a directiva `aliases` no `msmtprc`.

## Checklist pós-instalação

- [ ] Pacotes `msmtp`, `msmtp-mta`, `ca-certificates`, `bsd-mailx` instalados.
- [ ] `/usr/sbin/sendmail` → msmtp.
- [ ] Permissões 600 em `/etc/msmtprc` e `/root/.netrc`.
- [ ] Email de teste recebido.
- [ ] [INTEGRATION.md](INTEGRATION.md) lido se for integrar com `entre` ou scripts admin.

Próximo: [ADMIN.md](ADMIN.md) para operação corrente.
