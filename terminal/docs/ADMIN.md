# Operação — fila de pedidos `entre` (runv.club)

Fluxo geral de instalação e utilização: **[USO.md](USO.md)**.

## Onde ficam os pedidos

- Directório: **`/var/lib/runv/entre-queue/`**
- Um ficheiro **`{request_id}.json`** por pedido (UUID v4).
- Permissões: directório `0700`, dono **`entre`**; ficheiros `0640` na criação.

## Conteúdo típico do JSON

| Campo | Descrição |
|-------|-----------|
| `request_id` | Identificador único. |
| `username` | Nome Unix desejado pelo candidato. |
| `email` | Contacto. |
| `online_presence` | Texto livre com sítios/perfis indicados pelo candidato. |
| `public_key` | Linha OpenSSH normalizada. |
| `public_key_fingerprint` | SHA256 (formato OpenSSH). |
| `submitted_at` | ISO 8601 UTC. |
| `remote_addr` | Endereço remoto, se `SSH_CONNECTION`/`SSH_CLIENT` existir. |
| `tty` | `SSH_TTY`, se existir. |
| `source` | `entre-ssh`. |
| `status` | Inicialmente `pending`. |
| `app_version` | Versão do `entre_app`. |

## Ler e filtrar

```bash
sudo ls -1 /var/lib/runv/entre-queue/
sudo jq -r '"\(.submitted_at) \(.username) \(.email) \(.status)"' /var/lib/runv/entre-queue/*.json
```

## Revisão manual

1. Abrir o JSON e confirmar que username, email, `online_presence` e chave são plausíveis.
2. Procurar duplicados (mesmo email ou mesma fingerprint com pedidos `pending`).
3. Decidir: aprovar, rejeitar ou pedir mais informação por email **fora** deste sistema.

## Aprovar e criar a conta real

Use o provisionador interno **[`scripts/admin/create_runv_user.py`](../../scripts/admin/create_runv_user.py)** (no servidor, como root):

```bash
sudo python3 /caminho/create_runv_user.py \
  --username "NOME_DO_JSON" \
  --email "EMAIL_DO_JSON" \
  --public-key 'LINHA_EXACTA_DO_JSON'
```

Ou modo interactivo sem flags e colar os dados. O script valida de novo (regex, chave, utilizador ainda inexistente, etc.).

**Importante:** os dados do JSON são **proposta**; a última palavra é sempre o operador e o `create_runv_user.py`.

## Marcar pedidos no JSON

Não há base de dados: o operador pode:

- Acrescentar campos manualmente, por exemplo:
  - `"reviewed_at": "2026-03-20T12:00:00+00:00"`
  - `"status": "approved"` | `"rejected"` | `"archived"`
  - `"reviewer": "admin"`
- Ou mover ficheiros para subpastas (`approved/`, `rejected/`) se criar essa convenção localmente.

Sugestão mínima: manter o ficheiro no sítio e só alterar `status` para auditoria simples.

## Notificação ao administrador

1. **Obrigatória:** novo ficheiro na fila.
2. **Log:** `/var/log/runv/entre.log` (ou o caminho em `config.toml`); também um resumo curto (`admin_console_notice`) na mesma sessão.
3. **Email:** o `entre_app.py` envia o corpo definido em `templates/admin_mail.txt` quando há destinatário válido:
   - **Prioridade:** `admin_email` em `config.toml`.
   - **Fallback:** se `admin_email` no TOML estiver vazio, usa `admin_email` de `/etc/runv-email.json` (o mesmo ficheiro do Mailgun / `configure_mailgun.py`).
   - **Transporte:** [`entre_core.sendmail_notify`](../entre_core.py) tenta **primeiro** a API **Mailgun** via `lib.mailer.send_mail` quando o JSON global indica Mailgun; caso contrário usa `sendmail_path` (por omissão `/usr/sbin/sendmail`). Requisitos Mailgun: `email_package_root` ou variável `RUNV_EMAIL_ROOT` a apontar para a pasta `email/` do repositório.
   - **Remetente:** se `mail_from` no TOML for o default `entre@runv.club` e o JSON tiver `default_from`, o *From* alinha-se a `default_from` (útil com domínio verificado no Mailgun).

### Reenviar notificação

Não há botão. Opções:

- Copiar o JSON e enviar email manualmente.
- Script local que relê o JSON e chama `sendmail` com o mesmo formato que `templates/admin_mail.txt`.

### Depuração de email

- Ver log: `grep -E 'notificação|Mailgun|sendmail' /var/log/runv/entre.log`.
- **Mailgun:** confirmar `/etc/runv-email.json` + chave em `/etc/runv-email.secrets.json`; IP allowlist no painel Mailgun; `email_package_root` ou `RUNV_EMAIL_ROOT`.
- **Legado (MTA):** testar `echo test | mail -s test root` (conforme o servidor); `ls -l /usr/sbin/sendmail`.

## Pedidos inválidos ou spam

- Marcar `status` como `rejected` ou arquivar.
- Não apagar de imediato se quiseres trilho de auditoria; podes mover para `archive/` depois de um tempo.
- **Rate limiting** avançado está fora de âmbito deste módulo; pode ser feito à frente (fail2ban, firewall, etc.).

## Logs e privacidade

Os JSONs contêm dados pessoais e chave pública. Restringe acesso ao directório da fila e rotações de log conforme a política da runv.

## Ligação com o site / documentação pública

Se existir página “Junte-se a nós” no site estático, deve apontar para **`ssh entre@runv.club`** e explicar geração de chaves — mantém coerência com este fluxo.
