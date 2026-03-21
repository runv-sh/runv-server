# IRC no runv.club — comando **`chat`**

Estilo [tilde.club](https://tilde.club): o utilizador corre só **`chat`** e liga ao IRC da casa com auto-ligação já preparada.

## Alinhamento (plano / produto)

- **MOTD** (`tools/motd/60-runv`) e **`runv-help`** referem **apenas o comando `chat`** — sem citar outros nomes de binário ao utilizador.
- **Provisionamento** (`patch_irc.py`) usa **sempre** `weechat-headless` (`-a`, `-r`, `--stdout`): é o fluxo suportado para automatizar `/server add` e `/set` sem editar ficheiros à mão.
- O **cliente interactivo** no terminal é instalado pelos **pacotes globais** em `tools/manifests/apt_packages.txt` (o launcher `chat` escolhe o primeiro binário adequado no PATH); utilizadores continuam a ver só **`chat`**.

## O que o admin faz

```bash
cd /caminho/runv-server/scripts
sudo python3 admin/patch_irc.py --all-users --verbose
# ou um utilizador:
sudo python3 admin/patch_irc.py --user alice --verbose
```

- Instala **`/usr/local/bin/chat`** (salvo `--skip-launcher`).
- Por utilizador: `~/.config/weechat/`, servidor interno **`runv`** (por defeito), nick = **username Unix**, nicks alternativos `user_`, `user__`, `user|away`.
- Exige **`weechat-headless`** no sistema para aplicar o patch; sem esse binário o script falha com mensagem clara (`apt install weechat-headless`).

## O que o utilizador faz

```bash
chat
```

Opcional: variável de ambiente **`WEECHAT_HOME`** para outro directório de dados (convénio do cliente IRC).

## Defaults (ajustáveis por flags)

| Parâmetro | Default |
|-----------|---------|
| Host IRC | `irc.portalidea.com.br` |
| TLS | ligado (`--tls`; omitir `--no-tls`) |
| Porta | `6697` com TLS, `6667` sem TLS (ou `--port`) |
| Nome do servidor na config | `runv` |
| Autojoin | vazio; `--autojoin '#canal1,#canal2'` |

Não há SASL/NickServ automático; no código há comentários para extensão futura com **dados seguros** (sem senhas em texto plano).

## Flags úteis

- `--dry-run`, `--verbose`, `--force`
- `--skip-launcher`, `--skip-backfill`
- `--users-json`, `--homes-root`
- `--user` **ou** `--all-users` (obrigatório um dos dois)

## Integração `tools.py`

Copia **`tools/bin/chat`** → `/usr/local/bin`. O `patch_irc.py` pode reinstalar o mesmo ficheiro se correres o patch sem rerodar `tools.py`.

## Testes rápidos (Debian 13)

```bash
sudo python3 admin/patch_irc.py --dry-run --all-users --verbose
sudo python3 admin/patch_irc.py --user "$(logname)" --verbose
command -v chat && ls -l "$(command -v chat)"
command -v weechat-headless
sudo -u USER test -f /home/USER/.config/weechat/irc.conf && grep '^runv\.' /home/USER/.config/weechat/irc.conf
```

Substitui `USER` por um utilizador real.
