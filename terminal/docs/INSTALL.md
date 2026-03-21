# Instalação — fluxo SSH `entre` (runv.club)

Guia para **Debian 13** (ou derivado próximo). Por defeito, `setup_entre.py` instala **`/etc/ssh/sshd_config.d/runv-entre.conf`**, corre **`sshd -t`** e **`systemctl reload ssh`** (com backup do drop-in anterior se existir). Use **`--skip-sshd`** se preferir aplicar o bloco à mão.

Para um único documento com **instalação + uso** (visitante e admin), ver também **[USO.md](USO.md)**.

## 1. Dependências

```bash
sudo apt update
sudo apt install -y python3 openssh-server openssh-client mailutils
```

- **python3** — interpretador (stdlib: `tomllib`, `email`, etc.).
- **openssh-client** — binário `ssh-keygen` usado para validar fingerprint da chave pública.
- **openssh-server** — serviço SSH.
- **mailutils** (ou outro MTA com **sendmail** em `/usr/sbin/sendmail`) — **opcional**, só para email ao admin.

**Recomendado para o servidor runv.club:** configurar envio **sem Postfix/Exim** com o módulo do repositório **[`email/`](../email/README.md)** (`msmtp` + `msmtp-mta` + `bsd-mailx`). Depois disso, `/usr/sbin/sendmail` encaminha para o seu SMTP externo e o `entre` continua a usar `sendmail_path = "/usr/sbin/sendmail"` no `config.toml`.

## 2. Obter o código

A partir do repositório `runv-server`, a pasta relevante é `terminal/`.

## 3. Executar o setup (root)

```bash
cd /caminho/do/repositório/terminal
sudo python3 setup_entre.py
```

Ou:

```bash
sudo sh scripts/install.sh
```

O script:

- cria o utilizador **`entre`** (se não existir), com home por omissão `/home/entre` e shell **`/bin/sh`** (o OpenSSH precisa de shell funcional para o contexto do **ForceCommand**; `nologin` impede o fluxo);
- alinha o shell com **`chsh`** se `entre` já existir com outro shell;
- garante **`~entre/.ssh`** e **`authorized_keys`** (vazio; útil sobretudo em `--auth-mode key-only`);
- cria **`/var/lib/runv/entre-queue`** (dono `entre`, modo `0700`);
- garante **`/var/log/runv/`** e o ficheiro **`entre.log`** (dono `entre`, leitura/escrita para append);
- copia o módulo para **`/opt/runv/terminal`** e, se não existir `config.toml`, gera-o a partir de `config.example.toml`;
- **OpenSSH (por defeito):** escreve o drop-in conforme **`--auth-mode`** (omissão: **`shared-password`**); **`sshd -t`**, validação **`sshd -T -C …`**, **`systemctl reload ssh`** (em falha, reverte o drop-in).

Opções úteis:

- `--auth-mode shared-password` | `key-only` | `empty-password` — método para `entre`.
- **`empty-password` (onboarding estilo [tilde.town](https://tilde.town) / `join@tilde.town`):** cria grupo **`entre-open`**, mete `entre` no grupo, **`passwd -d`**, valida **NP**. **Por omissão** o drop-in usa **`AuthenticationMethods keyboard-interactive`** + **`KbdInteractiveAuthentication yes`** (PAM **`pam_succeed_if`** sem prompts) — melhor com **OpenSSH do Windows**, que em geral não envia palavra-passe vazia no método **`password`**. **`--empty-password-tilde-password-auth`** volta ao esquema README tilde (**`password`** + **`PermitEmptyPasswords yes`**). **Por omissão** altera **`/etc/pam.d/sshd`**: backup e linha **`pam_succeed_if … user ingroup …`** antes de **`@include common-auth`**. Sem isto, no Debian o **PAM** pode recusar o fluxo → **«Connection closed»**. **Não** é ausência total de autenticação: é política explícita só para `entre`.
- `--empty-password-group` — nome do grupo suplementar (default: `entre-open`).
- **`--empty-password-tilde-password-auth`** — só com **`empty-password`**: drop-in estilo README tilde (**`password`** + **`PermitEmptyPasswords yes`**); omissão = keyboard-interactive (recomendado para Windows).
- **`--skip-pam-empty-password-rule`** — não mexer no PAM (só para quem configura à mão; em geral **não** use em `empty-password` em Debian).
- `--sshd-test-connection` — argumento `-C` para `sshd -T` (deve bater com o `Match`, ex.: `user=entre,host=runv.club,addr=127.0.0.1`).
- `--dry-run` — apenas mensagens, sem alterações.
- **Reexecução:** se já existir **`/opt/runv/terminal/entre_app.py`**, em terminal interactivo o script pergunta se deseja continuar (actualiza `entre_app.py`, `entre_core.py`, `templates/`, etc.). Responder **não** cancela tudo. Em seguida, se **`config.toml`** já existir, pergunta se deve **substituí-lo** pelo example (omissão: **não**, para não perder `admin_email`).
- `-y` / `--yes` — não mostrar esses prompts (útil em scripts); **`config.toml`** continua preservado salvo **`--force-config`**.
- `--force-config` — repõe `config.toml` a partir do example (sem segundo prompt).
- `--skip-copy` — só directórios/utilizador (sem copiar ficheiros).
- `--skip-sshd` — não toca no SSH; imprime o bloco `Match User entre` para cópia manual.
- `--no-reload` — grava o drop-in e corre `sshd -t` + validação `-T`, mas não recarrega o serviço (útil para rever antes).

## 4. Configuração (`config.toml`)

Edite **`/opt/runv/terminal/config.toml`**:

- **`admin_email`** — endereço para notificações. Pode ficar vazio no TOML se **`admin_email`** estiver definido em **`/etc/runv-email.json`** (fallback usado pelo `entre_app.py`). Se ambos estiverem vazios, só fila + log.
- **`mail_from`** — remetente do email (cabeçalho `From`); por omissão **`entre@runv.club`**. Se a chave existir mas estiver vazia, o programa usa o mesmo endereço. Com Mailgun, se o remetente continuar no default e o JSON tiver `default_from`, o código alinha o *From* a `default_from`.
- **`sendmail_path`** — normalmente `/usr/sbin/sendmail` (ramo legado; com Mailgun configurado, o envio pode ser pela API sem precisar de MTA).

## 5. Autenticação SSH para o utilizador `entre`

O OpenSSH **exige** sempre **alguma** credencial; **não** existe “`ssh` e entrou” sem palavra-passe nem chave no protocolo.

**Modo recomendado (`--auth-mode shared-password`):** palavra-passe Unix **partilhada**, definida **só pelo root** (`sudo passwd entre`, etc.), com **`AuthenticationMethods password`**, **`PubkeyAuthentication no`** e **`KbdInteractiveAuthentication no`** no `Match User entre`, para acesso sem chave pré-registada.

**`key-only`:** só chave pública em **`authorized_keys`**; sem palavra-passe.

**`empty-password`:** `passwd -d entre`, grupo **`entre-open`**, regra PAM **`pam_succeed_if user ingroup entre-open`** (recomendado no Debian). **Por omissão** o SSH usa **`keyboard-interactive`** (PAM resolve sem prompts; compatível com Windows). Com **`--empty-password-tilde-password-auth`**, **`AuthenticationMethods password`** + **`PermitEmptyPasswords yes`** (como muitos README tilde). **Menos seguro** que palavra-passe ou chave; usar só para onboarding do utilizador especial `entre`, não para contas normais.

O fluxo **`entre_app`** (historinha + formulário) **não** altera a senha Unix; só recolhe o pedido de conta.

O visitante **não** obtém shell interactivo normal: o **`ForceCommand`** substitui o comando remoto (o shell em passwd é apenas o contexto mínimo exigido pelo OpenSSH).

## 6. OpenSSH (`runv-entre.conf`)

O setup coloca o ficheiro **`/etc/ssh/sshd_config.d/runv-entre.conf`** com o mesmo conteúdo lógico que abaixo (o caminho de `python3` vem de `which python3` no servidor). Confirme que **`/etc/ssh/sshd_config`** inclui algo como `Include /etc/ssh/sshd_config.d/*.conf` (comum no Debian).

Exemplo equivalente:

```
Match User entre
    AuthenticationMethods password
    PasswordAuthentication yes
    KbdInteractiveAuthentication no
    PubkeyAuthentication no
    PermitEmptyPasswords no
    ForceCommand /usr/bin/python3 /opt/runv/terminal/entre_app.py
    PermitTTY yes
    PermitUserRC no
    X11Forwarding no
    AllowAgentForwarding no
    AllowTcpForwarding no
    PermitTunnel no
    DisableForwarding yes
```

Exemplo **`--auth-mode empty-password`** (omissão; keyboard-interactive + PAM — recomendado para Windows):

```
Match User entre
    AuthenticationMethods keyboard-interactive
    PasswordAuthentication no
    KbdInteractiveAuthentication yes
    PubkeyAuthentication no
    PermitEmptyPasswords no
    ForceCommand /usr/bin/python3 /opt/runv/terminal/entre_app.py
    PermitTTY yes
    PermitUserRC no
    X11Forwarding no
    AllowAgentForwarding no
    AllowTcpForwarding no
    PermitTunnel no
    DisableForwarding yes
```

Com **`--empty-password-tilde-password-auth`** (README tilde; `PermitEmptyPasswords yes`):

```
Match User entre
    AuthenticationMethods password
    PasswordAuthentication yes
    KbdInteractiveAuthentication no
    PubkeyAuthentication no
    PermitEmptyPasswords yes
    ForceCommand /usr/bin/python3 /opt/runv/terminal/entre_app.py
    PermitTTY yes
    PermitUserRC no
    X11Forwarding no
    AllowAgentForwarding no
    AllowTcpForwarding no
    PermitTunnel no
    DisableForwarding yes
```

Em **`empty-password`**, o script faz backup de **`/etc/pam.d/sshd`** e insere antes de `@include common-auth` (ou primeira linha `auth`), salvo **`--skip-pam-empty-password-rule`**:

```
auth [success=done default=ignore] pam_succeed_if.so user ingroup entre-open
```

(Ajuste `entre-open` com **`--empty-password-group`** se mudar o nome do grupo.)

Se usou **`--skip-sshd`**, crie o ficheiro à mão e depois:

```bash
sudo sshd -t
sudo systemctl reload ssh
```

Confirme que o caminho de **`python3`** e de **`entre_app.py`** coincidem com o servidor (`which python3`).

## 7. Teste local do programa (sem SSH)

Na máquina de desenvolvimento (com `ssh-keygen` disponível):

```bash
cd terminal
chmod +x scripts/test_local.sh
./scripts/test_local.sh
```

Os pedidos ficam em `terminal/data/queue/`.

## 8. Teste via SSH

A partir de um cliente:

```bash
ssh entre@runv.club
```

(Substitua o host.) Percorra o fluxo até ao fim e verifique:

```bash
sudo ls -la /var/lib/runv/entre-queue/
sudo jq . /var/lib/runv/entre-queue/<request_id>.json
```

## 9. Teste de notificação por email

1. Defina o destinatário: **`admin_email`** no `config.toml` **ou** (se o TOML estiver vazio) **`admin_email`** em **`/etc/runv-email.json`**.
2. **Mailgun:** estado e segredos correctos; `email_package_root` ou `RUNV_EMAIL_ROOT`; teste com `email/configure_mailgun.py --test` no servidor.
3. **Legado:** **`sendmail`** e MTA a aceitar relay ou mail local.
4. Opcional: inspeccionar o formato com:

```bash
sh scripts/test_mail.sh
```

Se o email falhar, o pedido **mantém-se** na fila e o log regista o aviso (`notificação Mailgun falhou`, `sendmail falhou`, etc.).

## 10. systemd.path (opcional)

Para reagir a alterações na fila (log extra, hook próprio):

```bash
sudo cp systemd/runv-entre-notify.path /etc/systemd/system/
sudo cp systemd/runv-entre-notify.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now runv-entre-notify.path
```

Edite **`runv-entre-notify.service`** se quiser outro `ExecStart` (sem depender do Python do módulo para notificações simples).

## 11. Segurança e reversão do drop-in

A instalação automática faz **backup** do ficheiro anterior (`runv-entre.conf.bak.<timestamp>`), valida com **`sshd -t`** e só então recarrega o serviço. Se o teste falhar, o script **reverte** (ou remove o ficheiro numa primeira instalação). Para ambientes onde qualquer alteração ao SSH exige revisão prévia, use **`--no-reload`** ou **`--skip-sshd`**.

## Problemas frequentes

| Sintoma | Verificação |
|---------|-------------|
| `entre_app.py` não arranca | Permissões em `/opt/runv/terminal`, dono `entre`, `python3` no caminho. |
| Erro ao gravar fila | Dono e modo de `/var/lib/runv/entre-queue`. |
| Log vazio / permissão | Dono de `/var/log/runv/entre.log`. |
| Chave rejeitada | `ssh-keygen` instalado; chave numa linha; tipo permitido. |
| Sessão SSH fecha logo | Autenticação de `entre` falhou antes do ForceCommand. |
| Email do novo pedido não chega | `admin_email` no TOML ou no `/etc/runv-email.json`; Mailgun: allowlist de IP, chave HTTP, `email_package_root` / `RUNV_EMAIL_ROOT`; legado: `sendmail_path` e MTA. Ver log `entre`. |

Documentação de operação: **[ADMIN.md](ADMIN.md)**. Desenho: **[ARCHITECTURE.md](ARCHITECTURE.md)**.
