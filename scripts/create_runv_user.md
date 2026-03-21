# create_runv_user — provisionamento interno (runv.club)

**Versão 0.01** · **Desenvolvido por pmurad — 2026**

Ferramenta de linha de comando para **administradores** criarem contas Unix no servidor **Debian/Linux** (runv.club). Não é cadastro público.

É a **fonte principal** da política de provisionamento: usa `adduser`, mas o fluxo completo (SSH, `public_html`, `README.md`, permissões, quota, metadados, log) está centralizado aqui — sem depender de `adduser.local`, `QUOTAUSER` ou regras em `/etc/adduser.conf`.

**Ambiente:** execute apenas no servidor (ou VM Debian). O script usa `pwd`, `fcntl`, `adduser`, `ssh-keygen`, `findmnt`/`setquota` — **não é suportado no Windows.**

### O que o script garante (ordem de execução)

1. **Criar o usuário** — `adduser --disabled-password` (conta Unix).
2. **Instalar a chave** — `~/.ssh/authorized_keys` com chave validada e modos `700` / `600`.
3. **Preparar `public_html`** — diretório `755` e `~/public_html/index.html` estático (sem JavaScript, sem CDN); não sobrescreve sem `--force-index`.
4. **Copiar o skel** — o Debian **copia `/etc/skel` para a home no passo 1**. Depois, o script acrescenta `~/README.md` runv em português (runv.club, URL `~/username/`, permissões, comandos, aviso sobre arquivos públicos); não sobrescreve sem **`--force-readme`**. Se o skel do sistema já tiver um `README.md`, ele permanece até usar `--force-readme`. Para padronizar o skel do servidor, use **[`skel.py`](skel.md)** antes de criar contas.
5. **Aplicar permissões** — `apply_runv_permissions` reforça home `755`, `.ssh` / `authorized_keys`, `public_html` / `index.html` e `README.md` com modos e donos corretos; em seguida quota (se ativa), verificação final e metadados.

**Log** em arquivo (e stderr com `--verbose`) com estas fases numeradas, quota, metadados e verificação final.

## Quota ext4

O `create_runv_user.py` descobre **automaticamente** o mount que contém `/home/username` (`findmnt` / `admin/runv_mount.py` no repositório) e aplica `setquota` nesse ponto — tanto se a home está na **raiz `/`** como se **`/home`** é um volume **ext4** separado. O filesystem tem de ser **ext4** com **`usrquota`** (ou **`usrjquota=`**) ativo nesse mount.

- **Não** usa `xfs_quota` nem assume XFS.
- **Não** altera `/etc/fstab`, **não** remonta, **não** reinicia a máquina, **não** executa `quotaon` por si.
- **Apenas verifica** se o ambiente está pronto e, em caso afirmativo, aplica limites ao utilizador recém-criado.

### Preparar o sistema (Debian 13)

**Recomendado:** no servidor novo, correr **`admin/starthere.py`** (ver **[starthere.md](starthere.md)**) como root — instala pacotes, pode ativar Apache/UFW e configura **usrquota** no mount detetado a partir de `/home` (o mesmo critério que este script).

**Alternativa manual** (se não usar `starthere.py`):

1. Instalar ferramentas: `sudo apt install quota`
2. Em **`/etc/fstab`**, na linha do mount onde está a home (no caso típico, `/`), acrescentar **`usrquota`** (e opcionalmente `grpquota`) nas opções de mount, por exemplo:  
   `UUID=... / ext4 defaults,usrquota 0 1`
3. Remontar read-write com nova opção ou reiniciar:  
   `sudo mount -o remount /`
4. Inicializar ficheiros de quota (ajuste o mountpoint se não for `/`):  
   `sudo quotacheck -cum /`  
   (pode demorar; em sistemas com quota já ativa use os flags que a sua política recomendar.)
5. Ativar quotas:  
   `sudo quotaon -v /`
6. Confirmar:  
   `findmnt -n -o OPTIONS /` deve mostrar `usrquota` ou `usrjquota=...`

Só depois disto o `create_runv_user.py` conseguirá aplicar limites automaticamente.

### Política padrão runv (ajustável por flags)

| Limite | Padrão |
|--------|--------|
| Blocos soft | 450 MiB |
| Blocos hard | 500 MiB |
| Inodes soft | 10000 |
| Inodes hard | 12000 |

**Unidades:** os flags `--quota-soft-mb` e `--quota-hard-mb` usam o sufixo histórico `-mb`, mas os valores são **MiB** (mebibytes, 1024² bytes), **não** megabytes decimais (10⁶). Internamente convertem para as unidades de **1 KiB** que o `setquota` usa em ext4 (vfsv0): `kib = mib * 1024`.

### Comportamento e política de falhas (v1)

| Situação | Comportamento |
|----------|----------------|
| **Padrão** (sem `--no-quota`) | Após criar o utilizador, tenta aplicar quota. Se o sistema **não** estiver preparado ou `setquota` falhar, a conta **permanece**, metadados gravados com `status: partial_quota` e `quota_status: failed` ou `not_configured`, **saída 3** (`EXIT_INCONSISTENT`), mensagem de aviso forte no stderr. |
| **`--require-quota`** | Antes de `adduser`, verifica ext4 + `usrquota`/usrjquota + `setquota`. Se falhar, **aborta sem criar** utilizador (saída 1). |
| **`--no-quota`** | Não chama `setquota`; metadados com `quota_enabled: false`, `quota_status: skipped`. |

Não há remoção automática da conta quando só a quota falha; o admin decide (ex.: `del-user.py` ou `deluser` manual).

## Modo interativo (recomendado)

Sem argumentos, o script entra em **modo interativo**: mostra o cabeçalho (versão e crédito), faz perguntas e você responde no terminal.

```bash
sudo python3 /usr/local/bin/create_runv_user.py
```

Ou explicitamente:

```bash
sudo python3 /usr/local/bin/create_runv_user.py --interactive
# ou
sudo python3 /usr/local/bin/create_runv_user.py -i
```

Fluxo típico:

1. Nome de usuário Unix  
2. Email administrativo (metadado)  
3. Chave SSH: colar **uma linha** OpenSSH ou indicar **caminho** de um arquivo `.pub`  
4. Dry-run (só validar, sem criar usuário) — sim/não  
5. Se for criar de verdade: sobrescrever `index.html` existente — sim/não  
6. Se for criar de verdade: sobrescrever `README.md` existente — sim/não  
7. Log verboso — sim/não  
8. Criar **sem** quota (`--no-quota`) — sim/não (padrão não)  
9. Se for com quota: exigir sistema pronto **antes** de criar (`--require-quota`) — sim/não (padrão não)  
10. Confirmação final antes de executar  

`Ctrl+C` cancela. Se responder “não” na confirmação final, o script encerra sem alterar o sistema.

## Modo não interativo (CLI)

Nos exemplos com caminho **`admin/create_runv_user.py`**, execute a partir do diretório **`scripts/`** do repositório (ou ajuste o caminho). Em produção, use normalmente **`/usr/local/bin/create_runv_user.py`** após `install`.

### Criação normal com quota (padrão)

```bash
sudo python3 admin/create_runv_user.py \
  --username alice \
  --email alice@example.com \
  --public-key "ssh-ed25519 AAAA... comentario"
```

### Sem quota

```bash
sudo python3 admin/create_runv_user.py \
  --username alice \
  --email alice@example.com \
  --public-key-file /root/alice.pub \
  --no-quota
```

### Exigir quota configurada antes de criar

```bash
sudo python3 admin/create_runv_user.py \
  -u alice \
  --email alice@example.com \
  --public-key "ssh-ed25519 AAAA..." \
  --require-quota
```

Se `usrquota` não estiver ativo em `/`, o script termina **sem** chamar `adduser`.

### Dry-run

```bash
python3 admin/create_runv_user.py \
  --username alice \
  --email alice@example.com \
  --public-key "ssh-ed25519 AAAA..." \
  --dry-run
```

(Não exige root.)

### Limites personalizados

```bash
sudo python3 admin/create_runv_user.py \
  -u bob \
  --email bob@example.com \
  --public-key "..." \
  --quota-soft-mb 400 \
  --quota-hard-mb 450 \
  --quota-inode-soft 8000 \
  --quota-inode-hard 9000
```

### Exemplo: falha por quota não habilitada

Com utilizador criado com sucesso mas mount **sem** `usrquota`:

- Stderr: aviso forte de conta criada sem quota aplicada.
- Exit code **3**.
- Em `/var/lib/runv/users.json`: `status: partial_quota`, `quota_status: not_configured` (ou `failed` se `setquota` falhou).

Versão e crédito:

```bash
python3 admin/create_runv_user.py --version
```

## Pré-requisitos no servidor

- Debian 13 (ou outro Linux com `adduser` e `deluser`)
- Python 3 (`python3`)
- Pacotes: `openssh-client` (`ssh-keygen`), `adduser`, **`quota`** (para `setquota`), **`util-linux`** (`findmnt`)
- Para quota: ext4 com **`usrquota`** (ou **`usrjquota=`**) no mount que contém `/home`
- Apache com `mod_userdir` já configurado (o script não altera o Apache)
- SSH com chaves (o script não altera `sshd_config`)

## Instalação

```bash
sudo install -m 755 admin/create_runv_user.py /usr/local/bin/create_runv_user.py
sudo mkdir -p /var/lib/runv
```

Log padrão: `/var/log/runv-user-provision.log`  
Metadados: `/var/lib/runv/users.json`

## Opções úteis (CLI)

- `--dry-run` — valida tudo e mostra o plano sem criar usuário
- `--verbose` — mais detalhes no stderr
- `--force-index` — sobrescreve `~/public_html/index.html` se já existir
- `--force-readme` — sobrescreve `~/README.md` se já existir (útil se o skel do sistema já criou um README)
- `--no-quota` — não aplica `setquota`
- `--require-quota` — falha antes de `adduser` se quota não estiver disponível
- `--quota-soft-mb`, `--quota-hard-mb`, `--quota-inode-soft`, `--quota-inode-hard` — limites (MiB para blocos)
- `--metadata-file`, `--lock-file`, `--log-file` — caminhos alternativos (ex.: testes em VM)
- `--base-url` — URL base no resumo (padrão `http://runv.club`)

## Metadados JSON (campos de quota)

Cada registo pode incluir:

- `quota_enabled` (bool)
- `quota_soft_mb`, `quota_hard_mb` (int ou null)
- `quota_inode_soft`, `quota_inode_hard` (int ou null)
- `quota_filesystem`, `quota_mountpoint` (string ou null)
- `quota_applied_at` (ISO 8601 ou null)
- `quota_status`: `skipped` | `applied` | `failed` | `not_configured`

## Códigos de saída

| Código | Significado |
|--------|-------------|
| 0 | Sucesso (utilizador criado e, se aplicável, quota aplicada) |
| 1 | Erro de validação ou argumentos (incl. `--require-quota` com sistema não pronto) |
| 2 | Falha de sistema (subprocess, permissões) antes/desde rollback completo |
| 3 | Estado inconsistente: utilizador criado mas quota não aplicada / não configurada; ou rollback falhou |

## Como testar no Debian 13 (resumo)

1. Configure quota no `/` conforme a secção “Preparar o sistema”.
2. `sudo python3 admin/create_runv_user.py --username testquota ... --verbose`
3. `sudo quota -u testquota` ou `repquota /` para ver limites.
4. Teste `--dry-run` sem root.
5. Teste `--require-quota` com fstab **sem** usrquota: deve sair **1** sem criar utilizador.
6. Remova o utilizador de teste com a sua ferramenta de banimento (`admin/del-user.py`) quando terminar.

## Segurança (resumo)

- Sem `shell=True`; subprocess só com lista de argumentos.
- Username e caminhos validados; sem path traversal.
- Chave pública validada com `ssh-keygen`; fingerprint SHA256 em metadados.
- Email é só metadado administrativo, não conta Unix.

## Limitações

- Quota suportada: **ext4** com quota de utilizador tradicional; outros filesystems recusados com mensagem clara.
- Sem remoção de utilizador por este script (use `admin/del-user.py` a partir de `scripts/` no repositório, ou a cópia em `/usr/local/bin` se instalou).
- O script **não** configura automaticamente fstab nem `quotaon`.
- Backup de `/var/lib/runv/users.json` é manual.

## Dependências Python

Nenhuma biblioteca PyPI — apenas a biblioteca padrão (ver `requirements.txt`).
