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
- Por utilizador: `~/.config/weechat/`, servidor interno **`runv`** (por defeito), nick = **username Unix**, nicks alternativos `user_`, `user__`, `user|away`, autojoin por defeito no canal **`#runv`**.
- O patch aplica também **definições globais** WeeChat (na mesma sessão `weechat-headless`): `irc.look.buffer_switch_join` = `on` (ao entrar num canal, o buffer activo passa a ser esse canal), `irc.look.server_buffer` = `independent` (buffer do servidor separado), `buflist.look.display_conditions` = ``${buffer.plugin} == irc`` (buflist só lista buffers do plugin IRC, reduzindo ruído tipo `core.weechat`). Se o teu WeeChat for muito antigo ou sem plugin buflist, o `/set buflist.*` pode falhar — rever a versão ou ajustar à mão.
- Com **`--all-users`**, a lista de contas é a **união** de: usernames em `users.json` **e** utilizadores com diretório em `--homes-root` (por omissão `/home`), UID ≥ 1000 e fora da lista interna de contas de sistema — assim contas de administração (ex.: `pmurad-admin`) que não estão no JSON também são provisionadas.
- Exige **`weechat-headless`** no sistema para aplicar o patch; sem esse binário o script falha com mensagem clara (`apt install weechat-headless`).
- Se a config **já existe** mas **não coincide** com o alvo (host, TLS, nicks, autojoin, etc.), o patch **realinha** sozinho (`/server del` + voltar a criar). Não é obrigatório **`--force`** para isso. **`--force`** serve para **reaplicar mesmo quando já estava alinhada** (útil para repor estado conhecido).

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
| Autojoin | `#runv`; `--autojoin ""` para nenhum; ou `--autojoin '#canal1,#canal2'` |

Não há SASL/NickServ automático; no código há comentários para extensão futura com **dados seguros** (sem senhas em texto plano).

## Flags úteis

- `--dry-run`, `--verbose`, `--force` (reaplica mesmo com config já igual ao alvo)
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
sudo -u USER grep '^runv\.autojoin' /home/USER/.config/weechat/irc.conf
```

Substitui `USER` por um utilizador real.
