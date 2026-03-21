# starthere.py

Bootstrap **conservador** para preparar um servidor **Debian**: pacotes úteis ao runv.club e **quotas de utilizador** (`usrquota`) no **mesmo filesystem ext4 onde vivem as homes** (detetado automaticamente — tipicamente `/` se `/home` está na raiz, ou `/home` se é um volume dedicado). A lógica de descoberta é a de [`runv_mount.py`](admin/runv_mount.py), alinhada a [`create_runv_user.py`](create_runv_user.md).

Versão do script: **0.02** (use `python3 admin/starthere.py --version` a partir do diretório `scripts/` do repositório).

### Comportamento de `--dry-run`

O script **consulta sempre o `findmnt` real** (só leitura) para mostrar o estado do mount detetado. Como o `fstab` não é gravado em dry-run, o kernel **não** passa a mostrar `usrquota` até uma execução real; por isso, em dry-run o fluxo **assume** quotas ativas só para completar o plano de quotas, incluindo `quotacheck` / `quotaon` simulados.

## Quando usar

- Máquina nova ou recém-instalada, antes de criar utilizadores com [`create_runv_user.py`](create_runv_user.md).
- Quando ainda não existem quotas ativas no filesystem das homes e pretende alinhar ao fluxo de `create_runv_user.md` (ext4 + `setquota`).

## Requisitos

- **root** (`sudo` ou sessão root).
- **Debian** (ou derivado com `apt-get`).
- O path de sonda (predefinido **`/home`**) tem de residir num filesystem **`ext4`**. Se `/home` estiver noutro tipo (btrfs, xfs, …), o script aborta — configure quotas manualmente ou use layout ext4 para as homes.
- Acesso à rede para `apt-get update` / `install` (exceto em `--dry-run`, que não executa APT mas ainda pode ler `/etc/fstab` nos passos de quota).

## O que o script faz

1. **`apt-get update`** (a menos que `--no-install`).
2. **`apt-get install -y`** de um conjunto fixo de pacotes (personalizável com `--packages`; ver lista em `BASE_PACKAGES` no código).
3. **Limpeza segura**: `apt-get autoremove` e `autoclean` (desligável com `--no-cleanup`).
4. **Serviços** (desligável com `--no-services`):
   - `systemctl enable --now apache2`
   - Se o UFW estiver **inativo**: `ufw allow OpenSSH`, `80/tcp`, `443/tcp`, depois `ufw --force enable` (não altera regras se o UFW já estiver ativo).
5. **Quotas** (desligável com `--no-quota`):
   - **Deteta** o mountpoint com `find_mount_triple` sobre `--quota-probe` (predefinido `/home`).
   - Garante `usrquota` na linha **ext4** correspondente a esse mountpoint em `/etc/fstab`.
   - Backup de `/etc/fstab` em `/root/runv-fstab-backups/fstab.<timestamp>.bak`.
   - **`mount -o remount,usrquota <mount>`** e, se preciso, **`mount -o remount <mount>`** (saltável com `--skip-remount`).
   - **`quotacheck`** / **`quotaon`** nesse mesmo `<mount>`.

## O que o script não faz

- Não remove pacotes em massa nem faz `purge` agressivo.
- Não altera vhosts Apache nem cria utilizadores (só enable/start do serviço `apache2`).
- Não altera configuração SSH além do que o pacote `openssh-server` já traz.
- Não instala stack de correio.
- Não define limites por utilizador — isso fica para `create_runv_user.py` / `setquota` manual.

## Opções de linha de comandos

| Opção | Efeito |
|--------|--------|
| `--dry-run` | Mostra comandos e plano; não executa subprocessos reais (saídas simuladas onde aplicável). |
| `--verbose` | Ecoa comandos e saída de stderr/stdout dos programas. |
| `--packages` | Lista explícita de pacotes a instalar (substitui o padrão). |
| `--no-install` | Não corre APT; apenas lógica de quotas (útil se os pacotes já estiverem instalados). |
| `--no-cleanup` | Não corre `autoremove` / `autoclean`. |
| `--no-quota` | Só instala/limpa; não mexe em `fstab` nem quotas. |
| `--quota-probe PATH` | Caminho para descobrir o FS de quotas (predefinido `/home`; deve bater com onde o `create_runv_user` cria homes). |
| `--skip-remount` | Não tenta `remount` após editar `fstab`. |
| `--allow-live-scan` | Usa apenas **`quotacheck -cuM`** (não tenta antes `-cu`). |
| `--no-services` | Não ativa Apache nem configura/ativa UFW. |
| `--version` | Mostra versão e sai. |

Códigos de saída: **0** sucesso; **2** erro operacional (`BootstrapError`); **130** interrupção (Ctrl+C).

## Pacotes base (padrão)

Incluem, entre outros: `apache2`, `openssh-server`, `sudo`, `ufw`, `quota`, ferramentas de rede e ficheiros (`curl`, `wget`, `git`, `rsync`), consola (`tmux`, `htop`, `vim`, …), `jq`, `acl`, `build-essential`, `python3-venv`, `python3-pip`, `ripgrep`, `shellcheck`. A lista completa está em `BASE_PACKAGES` em [`starthere.py`](admin/starthere.py).

## Quotas: comportamento esperado e problemas comuns

- Depois de editar `fstab`, o **remount** pode falhar em alguns ambientes (cloud-init, segurança do kernel). O script sugere **reiniciar a VM** e voltar a executar o script.
- **`quotacheck` com filesystem montado**: o script tenta **`-cu`**, depois **`-cuM`**, e se ainda falhar (p.ex. quotas já ativas após remount — mensagem «use -f»), **`-cuM -f`** e **`-cu -f`**. **`--allow-live-scan`** começa por **`-cuM`** e, se preciso, **`-cuM -f`**.
- **`quotaon -vu`**: se o kernel já tiver quotas de utilizador activas neste mount (comum após `remount,usrquota` + `quotacheck`), o `quotaon` pode devolver **Device or resource busy**. O script trata isso como **sucesso** e imprime um aviso — confirme com **`quota -vs`** ou **`sudo repquota -s <mount>`** (`repquota` costuma estar em `/usr/sbin/`).
- Confirme com `mount | grep ' on <mount> '` (o `<mount>` é o indicado no resumo do script, ex. `/` ou `/home`) e `quota -vs`.
- **Reinício:** em muitas contas normais o comando `reboot` não está no `PATH`; use `sudo reboot` ou `/sbin/reboot`.

### Avisos «external quota files» e `tune2fs -O quota`

O `quotacheck` e o `quotaon` podem imprimir avisos dizendo que o kernel prefere a **feature interna `quota` do ext4** e que os ficheiros clássicos (`aquota.user` / «external quota files») estão **deprecated**.

- **Isto não invalida o que o script fez:** com `usrquota` no mount e `quota -vs` a mostrar o filesystem, as quotas estão ativas; `setquota` (como em `create_runv_user.py`) funciona neste modo.
- O script usa o caminho suportado em **/** montado: `usrquota` + ficheiros de quota geridos pelas ferramentas `quota` — é o esperado quando a feature `quota` do ext4 **não** foi ligada no superbloco.
- **Migrar** para quotas «só no ext4» (sem aquele aviso) implica, em geral, **desmontar** o volume (para `/` isso significa **modo rescue/live** ou VM parada), correr algo como `tune2fs -O quota <dispositivo>`, voltar a montar e rever opções de mount/documentação do seu Debian — fora do âmbito automático deste bootstrap.
- O pacote **`e2fsprogs`** (inclui `tune2fs`, `dumpe2fs`) está na lista base para inspeção manual; após um run bem-sucedido, o script pode imprimir uma **nota** em stderr se detectar que a feature interna ainda não está ativa.

## Relação com outros scripts

- Após este bootstrap, use **[create_runv_user.md](create_runv_user.md)** para criar contas com quota e `public_html`.
- **[skel.md](skel.md)** e **[del-user.md](del-user.md)** cobrem esqueleto de ficheiros e remoção de utilizadores.

## Segurança e operações

- Alterações em **`/etc/fstab`** são precedidas de backup em **`/root/runv-fstab-backups/`**.
- O script foi pensado para **ext4 no volume das homes**; não extrapola para outros filesystems.
- Revise sempre `--dry-run` / `--verbose` num ambiente de teste antes de produção.
