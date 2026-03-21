# Instalação e uso — módulo `terminal` (entre)

Este documento resume **como instalar**, **como usar** (visitante e administrador) e **onde olhar** quando algo falha. Detalhes técnicos extra: [INSTALL.md](INSTALL.md), [ADMIN.md](ADMIN.md), [ARCHITECTURE.md](ARCHITECTURE.md).

---

## 1. O que é

- Utilizador Unix **`entre`** no servidor; quem corre `ssh entre@runv.club` **não** recebe shell normal.
- O OpenSSH executa **`entre_app.py`** (`ForceCommand`), que mostra textos em [templates/](../templates/) (introdução, avisos, formulário), valida dados e grava um **JSON** em `/var/lib/runv/entre-queue/`.
- **Não cria conta Linux** automaticamente; a aprovação é manual e o provisionamento usa [`create_runv_user.py`](../../scripts/admin/create_runv_user.py).

---

## 2. Instalação no servidor (admin)

1. **Dependências** (Debian 13): `python3`, `openssh-server`, `openssh-client` (`ssh-keygen`), opcional `mailutils` para email.
2. **Copiar e preparar o módulo** (como root), a partir da pasta `terminal/` do repositório:

   ```bash
   cd /caminho/runv-server/terminal
   sudo python3 setup_entre.py
   ```

   Ou: `sudo sh scripts/install.sh`

3. **Configurar** `/opt/runv/terminal/config.toml` (a partir de `config.example.toml`):
   - `admin_email` — para receber notificação por `sendmail` (pode ficar vazio).
   - `queue_dir`, `log_file`, `templates_dir` — normalmente não precisa mudar.

4. **OpenSSH:** por defeito o `setup_entre.py` instala **`/etc/ssh/sshd_config.d/runv-entre.conf`**, corre **`sshd -t`** e **`systemctl reload ssh`**. Com **`--skip-sshd`**, aplica o bloco à mão (ver [INSTALL.md](INSTALL.md) ou [examples/sshd_match_entre.conf.sample](../examples/sshd_match_entre.conf.sample)).

5. **Autenticação:** omissão **`--auth-mode shared-password`**. **`empty-password`**: espírito **`join@tilde.town`** — grupo **`entre-open`**, **`passwd -d`**, **PAM** em `/etc/pam.d/sshd` por omissão; o drop-in SSH usa **`keyboard-interactive`** por omissão (Windows); **`--empty-password-tilde-password-auth`** = **`password`** + **`PermitEmptyPasswords`**. Não é “SSH sem credencial”. Shell **`/bin/sh`**. Ver [INSTALL.md](INSTALL.md).

---

## 3. Uso pelo visitante (candidato)

1. Ligar (o site indica a **palavra-passe partilhada** do utilizador `entre`, se existir):

   ```bash
   ssh entre@runv.club
   ```

2. **Opcional:** em **`key-only`**, ou se o admin tiver posto a tua chave em `authorized_keys` (não aplica ao modo `shared-password` por defeito).

3. No início aparece o **logo RUNV em ASCII** (verde, se o terminal suportar cores) e a frase *Aperte qualquer tecla para continuar...*; a cadeia **`runv.club`** é destacada a verde onde o terminal suporta. Segue-se uma **intro curta** e um **aviso sobre a chave** (Enter para seguir; `%%PAGE%%` nos `.txt` ainda pode partir em mais do que um ecrã se quiseres).
4. No **aviso da chave**: relembra colar só a **pública**, nunca a privada.
5. **Formulário em quatro passos**, cada um com cabeçalho claro e linha **»** onde escreves:
   - **utilizador** desejado (regras: minúsculas, letras/dígitos/`_`/`-`, não reservado nem já existente);
   - **email** de contacto — formato `nome@domínio` (com um único `@` e pelo menos um ponto no domínio, ex.: `maria@exemplo.org`);
   - **onde apareces online** — links ou perfis (várias linhas; termina com uma linha só com `.` e Enter);
   - **chave pública** SSH (uma linha).
6. **Rever o resumo** (inclui fingerprint SHA256 e o texto “online”):
   - confirmar envio, **editar** de novo ou **cancelar**.
7. Se confirmar: o pedido fica na fila; aparece a **despedida** com a referência `{request_id}`.
8. **Aguardar email** da administração; não repetir o mesmo pedido muitas vezes.

O **splash ASCII** (igual ao da landing em `site/public/index.html`) e o texto *Aperte qualquer tecla...* estão em [`entre_app.py`](../entre_app.py) (`RUNV_ASCII_ART`, `show_opening_splash`). Em `intro.txt` e `warning_public_key.txt`, `%%PAGE%%` **parte o texto em ecrãs** (`show_paged_template`). Os restantes textos: `confirm.txt`, `goodbye.txt`.

---

## 4. Uso pelo administrador (após pedidos)

1. **Listar pedidos:** `/var/lib/runv/entre-queue/*.json`
2. **Ler e decidir** (duplicados, email inválido, etc.) — ver [ADMIN.md](ADMIN.md).
3. **Criar conta** com o provisionador, usando os campos do JSON aprovado.
4. **Opcional:** `systemd` `runv-entre-notify.path` para reagir a novos ficheiros na fila.

---

## 5. Teste sem SSH (desenvolvimento)

```bash
cd terminal
chmod +x scripts/test_local.sh
./scripts/test_local.sh
```

Grava em `terminal/data/queue/` e usa `config.example.toml`. Exige `ssh-keygen` no PATH.

Variáveis úteis: `RUNV_ENTRE_CONFIG`, `RUNV_ENTRE_QUEUE_DIR`, `RUNV_ENTRE_LOG_FILE` (ver [README.md](../README.md)).

---

## 6. Onde está o quê

| Item | Caminho típico |
|------|----------------|
| Aplicação instalada | `/opt/runv/terminal/` |
| Configuração | `/opt/runv/terminal/config.toml` |
| Fila de pedidos | `/var/lib/runv/entre-queue/` |
| Log | `/var/log/runv/entre.log` |
| Textos da sessão | `/opt/runv/terminal/templates/` |
| Drop-in SSH `entre` | `/etc/ssh/sshd_config.d/runv-entre.conf` |

---

## 7. Problemas comuns

| Situação | O que verificar |
|----------|-----------------|
| SSH recusa antes de aparecer o texto | Palavra-passe de `entre` definida (`sudo passwd entre`); ou chave em `authorized_keys`; firewall; drop-in com `PasswordAuthentication yes` para `entre`. |
| Erro ao gravar pedido | Dono e permissões de `/var/lib/runv/entre-queue` (dono `entre`, `0700`). |
| Email não chega | `admin_email` preenchido; `sendmail` e MTA; mensagens no log. |
| Chave inválida | Uma linha só; tipo permitido; `ssh-keygen` instalado no servidor. |

---

## 8. Checklist rápido pós-instalação

- [ ] `sudo python3 setup_entre.py` concluído sem erros
- [ ] `config.toml` com `admin_email` se quiseres mail
- [ ] Drop-in `runv-entre.conf` presente (ou `--skip-sshd` aplicado à mão); `sshd -t` OK após o setup
- [ ] `ssh entre@host` mostra a narrativa e completa até JSON na fila
- [ ] Log com linha `pedido gravado`

Para texto legal e segurança em profundidade, ver [ARCHITECTURE.md](ARCHITECTURE.md).
