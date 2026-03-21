# Instalação — módulo `tools/` (runv.club)

Guia em **português** para administradores. Ambiente alvo: **Debian 13** (ou Debian estável recente).

## Dependências

- **root** no servidor (sudo).
- **Python 3** do Debian (sem PyPI obrigatório).
- **`apt`** funcional (`apt-get`).
- Rede para `apt-get update` / `install` (ou espelho local configurado).

Não é necessário Docker, banco de dados nem painel web.

## O que o `tools.py` faz

1. Valida execução como **root** (exceto em `--dry-run`, que só simula).
2. Lê **`manifests/apt_packages.txt`** (ignora linhas vazias e `#`).
3. Executa **`apt-get update -qq`** e **`apt-get install -y --no-install-recommends`** com esses pacotes.
4. Copia **`bin/runv-help`**, **`runv-links`**, **`runv-status`**, **`bin/chat`** → **`/usr/local/bin/`** com modo **755** (`chat` abre o IRC com config em `~/.config/weechat`; ver **`scripts/docs/irc_patch.md`**).
5. Copia **`motd/60-runv`** → **`/etc/update-motd.d/60-runv`** com modo **755**.
6. Copia o **`skel/`** do repositório para **`/etc/skel/`**:
   - `README.md` → **644**
   - `.bash_aliases` → **644**
   - `public_html/index.html` → diretório **`public_html` 755**, arquivo **644**
   - `public_gopher/gophermap` → diretório **`public_gopher` 755**, arquivo **644**
   - `public_gemini/index.gmi` → diretório **`public_gemini` 755**, arquivo **644**

O **`/etc/skel`** só afeta **contas novas** criadas depois da cópia (o Debian copia o skel no `adduser`). Utilizadores **já existentes** não recebem automaticamente estes ficheiros: use **[`scripts/admin/setup_alt_protocols.py`](../../scripts/docs/alt_protocols.md)** (backfill) ou crie `~/public_gopher` e `~/public_gemini` manualmente.

Se o destino **já existir** e for **idêntico** (conteúdo byte-a-byte) à origem no repositório, a cópia é **ignorada**. Se o ficheiro no repo **mudou**, o `tools.py` **atualiza** o destino mesmo sem **`--force`**. Use **`--force`** para sobrescrever sempre (útil para repor permissões/mtime ou forçar cópia igual).

## Execução

```bash
cd /caminho/para/runv-server
sudo python3 tools/tools.py
```

### Flags

| Flag | Efeito |
|------|--------|
| `--dry-run` | Não grava nem chama apt de verdade; mostra o que seria feito. |
| `--verbose` | Log detalhado no stderr. |
| `--force` | Sobrescreve sempre, mesmo quando origem e destino são idênticos. |
| `--skip-apt` | Pula `apt-get` (útil para atualizar só MOTD/bin/skel). |

Exemplo seguro antes da primeira aplicação:

```bash
sudo python3 tools/tools.py --dry-run --verbose
```

## Verificar pacotes instalados

```bash
dpkg -l byobu tmux lynx weechat weechat-headless mutt bsdgames tree less curl wget git
```

Ou:

```bash
apt list --installed 2>/dev/null | grep -E 'byobu|tmux|lynx|weechat|mutt|bsdgames|tree|less|curl|wget|git'
```

**Importante:** esses programas são **globais**. **Não** dependem do `/etc/skel`. Qualquer usuário com shell pode usá-los após a instalação (e após login, se o pacote estiver no `PATH`).

## Verificar comandos em `/usr/local/bin`

```bash
ls -l /usr/local/bin/runv-help /usr/local/bin/runv-links /usr/local/bin/runv-status /usr/local/bin/chat
/usr/local/bin/runv-help
```

Devem ser executáveis (**`-rwxr-xr-x`**) e imprimir texto em português com cores.

## Verificar MOTD

O Debian monta o MOTD com scripts em `/etc/update-motd.d/`. Para testar **só** o fragmento runv:

```bash
sudo chmod +x /etc/update-motd.d/60-runv   # se ainda não estiver
/etc/update-motd.d/60-runv
```

Para ver a sequência completa (pode ser longa):

```bash
run-parts /etc/update-motd.d/
```

Em novo login SSH você deve ver o bloco **verde** com arte **RUNV**, a tagline, a lista de comandos úteis e a dica **“digite runv-help para começar”**. Estatísticas do servidor (**`runv-status`**) não aparecem no MOTD nem em `runv-help`; só o utilizador **`pmurad-admin`** pode executar `runv-status`.

## Verificar `/etc/skel`

```bash
ls -la /etc/skel/
ls -la /etc/skel/public_html/
```

Esperado:

- `README.md` e `.bash_aliases` com permissões **644** (arquivos).
- `public_html` como diretório **755**.
- `public_html/index.html` **644**.

Novas contas criadas com `adduser` **depois** desta instalação recebem esses arquivos na home (junto com o restante do skel padrão do Debian, como `.bashrc`, se existir no sistema).

## Instruções de teste (checklist)

1. **Dry-run:** `sudo python3 tools/tools.py --dry-run --verbose` — revisar saída.
2. **Aplicar:** `sudo python3 tools/tools.py --verbose`.
3. **Segunda execução** sem `--force` com repo **inalterado** — deve **pular** ficheiros já iguais; após **editar** MOTD/bin/skel no repo, a mesma execução deve **copiar de novo**.
4. **`runv-help` / `runv-links`** — qualquer utilizador; **`runv-status`** — apenas como **`pmurad-admin`**.
5. **MOTD:** rodar `/etc/update-motd.d/60-runv` ou novo login SSH.
6. **Skel:** criar usuário de teste com `adduser` e conferir `~usuario/README.md` e `~/public_html/index.html`.

## Problemas comuns

- **apt-get update falha:** corrija espelhos/rede; o script registra erro e ainda pode copiar bin/MOTD/skel.
- **Permissão negada:** execute com `sudo` / root.
- **MOTD não aparece:** em alguns setups o display do MOTD depende de `pam_motd` e SSH; confira configuração do `sshd` e PAM no Debian.
- **MOTD sem grelha `last`:** o fragmento `60-runv` usa `/usr/bin/last` quando o PATH mínimo não o expõe; confirme **util-linux** e permissões de leitura em `/var/log/wtmp`. A mensagem *sem registos recentes em wtmp* indica wtmp vazio, não falta do binário.
