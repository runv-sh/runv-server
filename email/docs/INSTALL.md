# Instalação — módulo email runv.club

**Aviso: o configurador predefinido foi feito para Mailgun.** Não embute credenciais, domínios nem chaves — tudo é pedido em tempo de configuração.

Debian 13 (ou próximo). **Apenas envio** — caminho predefinido **Mailgun HTTP API** (Basic Auth: utilizador `api`, palavra-passe = API key). O modo **SMTP/msmtp + sendmail** permanece disponível como **legado**, desativado por predefinição.

## O que o predefinido faz (Mailgun)

- Grava metadados em **`/etc/runv-email.json`** (0600, root): domínio Mailgun, região da API (o configurador fixa **`us`** e `https://api.mailgun.net/`), remetente padrão, email do admin, tipo de chave, caminho da pasta `email/` do repositório (`email_package_root`), etc. **Sem API key neste ficheiro.**
- Grava segredos em **`/etc/runv-email.secrets.json`** (0600, root): apenas `mailgun_api_key`. **Não partilhar nem fazer backup deste ficheiro para repositórios públicos.**

### API key em variável de ambiente (opcional)

Em tempo de execução, **`RUNV_MAILGUN_API_KEY`** (se definida) **tem prioridade** sobre o ficheiro de segredos. Útil para systemd ou contentores; o estado público pode continuar a referir `api_key_source: file` — o runtime usa na mesma a env quando presente.

### Mailgun: SMTP vs HTTP API

- **Credenciais SMTP** do painel Mailgun são para clientes SMTP (ex.: msmtp); **não** são o mesmo fluxo que a API HTTP.
- A **HTTP API** usa autenticação **HTTP Basic**: username fixo **`api`**, password = **API key** (primary ou domain sending key).
- **US:** `https://api.mailgun.net/v3/<domínio>/messages` (o configurador usa sempre este endpoint; é o mesmo eixo que o SMTP **`smtp.mailgun.org`** nas credenciais SMTP do painel.)
- **EU:** `https://api.eu.mailgun.net/v3/<domínio>/messages` — só para contas/domínios alojados na região UE; nesse caso **edite** `mailgun_region` (`eu`) e `api_base_url` em `/etc/runv-email.json` após correr o script, ou a API devolverá erros de autenticação/domínio.

### IP allowlist (API)

Se no painel Mailgun estiver activa a **restrição por IP** para a API, qualquer servidor que chame `api.mailgun.net` tem de ter o **seu IP público** na lista. Sem isso, a API pode responder **401** / «Invalid private key» / **Forbidden** mesmo com chave e domínio correctos. Inclua o IP da VPS (ou desactive a allowlist para testes).

### Obter uma API key

1. Painel Mailgun → domínio → **Domain settings** / **Sending API keys**.
2. Preferir **domain sending key** (menor privilégio) se só precisar de enviar desse domínio; **primary API key** também funciona se tiver permissão de envio.

Para validar a **primary** no painel ou com `curl`, a listagem de domínios usa **`GET /v4/domains`** (US ou EU). A **domain sending key** não serve para esse endpoint; o envio do runv usa **`POST /v3/<domínio>/messages`** (já implementado em `lib/mailgun_client.py`).

## Executar o configurador (predefinido)

```bash
cd /caminho/para/runv-server/email
sudo python3 configure_mailgun.py
```

No arranque é mostrado o aviso de que o script foi feito para Mailgun e **não** pré-configura credenciais.

O script pergunta:

- tipo de chave (domain sending vs primary);
- domínio de envio Mailgun (ex.: `mg.exemplo.com`);
- API key (**ecoada** ao digitar; deve ser introduzida **duas vezes iguais** para continuar — útil para validar cópia/colar; evite terminais partilhados);
- remetente padrão (From);
- email do administrador (notificações / teste);
- caminho da pasta **`email/`** do repositório (para importações, ex. fluxo `entre` — por omissão é a pasta onde está o script).

A região da API HTTP **não é perguntada**: fica **`us`** (`api.mailgun.net`). Conta só UE: ajuste manualmente o JSON (ver secção «SMTP vs HTTP API» acima).

## Ficheiros criados (Mailgun)

| Ficheiro | Descrição |
|----------|-----------|
| `/etc/runv-email.json` | Metadados **sem** API key. **0600** root. |
| `/etc/runv-email.secrets.json` | `mailgun_api_key`. **0600** root. **World-readable proibido.** |

## Flags (`configure_mailgun.py`)

| Flag | Efeito |
|------|--------|
| `--dry-run` | Não grava ficheiros; mostra acções. |
| `--verbose` / `-v` | Log DEBUG (nunca inclui a API key). |
| `--force` / `-f` | Sobrescreve estado/segredos sem confirmar. |
| `--test` | Só envia `templates/system_test.txt` via **Mailgun API** (requer estado existente). |
| `--legacy-smtp` | Delega no configurador **SMTP/msmtp** (`configure_msmtp_legacy.py`). |

## Teste de envio (API)

```bash
sudo python3 configure_mailgun.py --test
```

Em caso de falha, mensagens típicas:

- **401 / 403** — Chave incorrecta (não é API HTTP / não é do domínio), região errada (US vs EU), ou **IP allowlist** no painel a bloquear o servidor; confira também se o domínio na URL coincide com o domínio verificado.
- **400** — payload inválido; From não autorizado no domínio; campos em falta.
- **404** — domínio errado ou URL/região incorreta (US vs EU).
- **Timeout / erro de rede** — DNS, firewall ou TLS.

## Modo legado: SMTP + msmtp + sendmail

Apenas se precisar de relay SMTP clássico:

```bash
sudo python3 configure_mailgun.py --legacy-smtp
# ou directamente:
sudo python3 configure_msmtp_legacy.py
```

Instala `msmtp`, `msmtp-mta`, `ca-certificates`, `bsd-mailx`, gera `/etc/msmtprc`, `/root/.netrc`, `/etc/msmtp_aliases`, e grava `/etc/runv-email.json` com **`backend: sendmail`**.

**`configure_msmtp.py`** (sem `_legacy`) é apenas um **encaminhamento** com mensagem a indicar os comandos correctos.

## Verificação rápida (Mailgun)

```bash
sudo ls -l /etc/runv-email.json /etc/runv-email.secrets.json
# Ambos devem ser -rw------- root root
sudo python3 configure_mailgun.py --test
```

Nunca imprima o conteúdo de `runv-email.secrets.json` em chats ou logs públicos.

## Biblioteca Python (`lib/mailer.py`)

Com **`backend: mailgun`** no estado, `send_mail` usa a API Mailgun (urllib, stdlib). Com **`backend: sendmail`** ou estado antigo só com `smtp_host`, usa `sendmail -t -i`.

Defina **`RUNV_EMAIL_ROOT`** para a pasta `email/` ao importar em scripts (ou use `email_package_root` em `/etc/runv-email.json` — o fluxo `entre` tenta ambos).

Exemplo:

```bash
sudo RUNV_EMAIL_ROOT=/caminho/runv-server/email python3 -c "
import sys
sys.path.insert(0, '/caminho/runv-server/email')
from lib.mailer import send_mail
send_mail('voce@exemplo.com', 'Teste', 'Corpo.', from_addr='noreply@exemplo.com')
"
```

## Variáveis de ambiente úteis

| Variável | Uso |
|----------|-----|
| `RUNV_EMAIL_ROOT` | Caminho da pasta `email/` (import `lib.*`). |
| `RUNV_EMAIL_STATE_PATH` | Alternativa a `/etc/runv-email.json` (testes). |
| `RUNV_EMAIL_SECRETS_PATH` | Alternativa ao caminho de segredos indicado no estado. |
| `RUNV_MAILGUN_API_KEY` | API key em memória/ambiente (sobrepor ficheiro de segredos). |

Próximo: [ADMIN.md](ADMIN.md) para operação corrente.
