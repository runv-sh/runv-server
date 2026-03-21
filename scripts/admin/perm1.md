# perm1 — jail para contas existentes

Script **`scripts/admin/perm1.py`** (root): adiciona utilizadores **uid ≥ 1000** ao grupo **`runv-jailed`** e cria o layout Jailkit em **`/srv/jail/<user>`** com **bind mount** da home real, mais linha em **`/etc/fstab`** (idempotente).

**Excluídos:** `nobody`, `pmurad-admin`, `entre`.

**Pré-requisitos:** `tools/tools.py` já aplicado (pacote **jailkit**, drop-in **`90-runv-jailed.conf`**, grupo `runv-jailed`).

```bash
sudo python3 scripts/admin/perm1.py --verbose
sudo python3 scripts/admin/perm1.py --only-user maria --dry-run
```

Após aplicar, teste SSH com um utilizador antes de confiar em produção.
