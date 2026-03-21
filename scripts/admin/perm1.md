# perm1 — jail para contas existentes

Script **`scripts/admin/perm1.py`** (root): adiciona utilizadores **uid ≥ 1000** ao grupo **`runv-jailed`** e cria o layout Jailkit em **`/srv/jail/<user>`** com **bind mount** da home real, mais linha em **`/etc/fstab`** (idempotente).

**Excluídos:** `nobody`, `pmurad-admin`, `entre`.

**Pré-requisitos:** `tools/tools.py` já aplicado (pacote **jailkit**, drop-in **`90-runv-jailed.conf`**, grupo `runv-jailed`).

## Opções Jailkit

- **`--jk-profile`** — perfil passado a `jk_init` quando o jail **ainda não tem** `bin/` (default: **`extendedshell`**, mais completo que `basicshell`). Valores: `extendedshell`, `basicshell`.
- **`--no-jk-init`** — **não** executa `jk_init`; só adiciona ao grupo, garante `home/<user>` no jail, bind e fstab. Exige que **`/srv/jail/<user>/bin`** já exista (jail pré-provisionado); caso contrário o script falha com mensagem explícita.

Se `bin/` já existir, `jk_init` **não** é voltado a correr (idempotente).

## Reverter (undo)

O script **`patches/undoperm.py`** (na raiz do repositório) remove o utilizador de `runv-jailed`, desmonta o bind, apaga a linha em `/etc/fstab` e, só com **`--purge-jail-dir`**, remove `/srv/jail/<user>`. **Não** restaura ficheiros alterados por `jk_init`.

```bash
sudo python3 patches/undoperm.py --verbose --dry-run
sudo python3 patches/undoperm.py --only-user maria
```

## Exemplos perm1

```bash
sudo python3 scripts/admin/perm1.py --verbose
sudo python3 scripts/admin/perm1.py --only-user maria --dry-run
sudo python3 scripts/admin/perm1.py --jk-profile basicshell
sudo python3 scripts/admin/perm1.py --no-jk-init --only-user maria
```

Após aplicar, teste SSH com um utilizador antes de confiar em produção.
