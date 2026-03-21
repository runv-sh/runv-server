# del-user.py — banimento / remoção de conta (runv.club)

**Versão 0.02** · runv.club

Ferramenta para **administradores** removerem **permanentemente** um utilizador Unix no Debian (banimento no runv.club): apaga a conta e, por defeito, a home com `deluser --remove-home`.

- **Não** remove nem altera configuração do Apache ou SSH globalmente.
- Opcionalmente remove a entrada correspondente em `/var/lib/runv/users.json` (mesmo formato que `create_runv_user.py`).
- **Gemini:** **umount** do bind em **`/var/gemini/users/<user>`** se estiver montado, remove a linha correspondente em **`/etc/fstab`**, remove symlink legado ou directório vazio.
- Se a home estiver num **ext4** com **usrquota** ativo, tenta **`setquota`** para repor limites a zero **antes** de `deluser` (mount detetado automaticamente, mesma lógica que `create_runv_user.py` / `runv_mount.py`). Se `setquota` falhar, a remoção da conta continua com aviso em stderr.

**Ambiente:** servidor **Linux** (Debian). Executar como **root** ou `sudo`. No Windows use só para revisão do código.

## Objetivo

- Eliminar o utilizador do sistema (`deluser`).
- Remover a pasta home (`--remove-home`) ou, se pedido, todos os ficheiros detidos pelo UID (`--purge-all-files`).
- Manter o registo interno coerente ao apagar o username do JSON de metadados runv (opcional).

## Segurança

- **Nunca** remove `root`.
- Recusa contas **reservadas** (ex.: `www-data`, `nobody`) salvo `--force`.
- Recusa UID **&lt; 1000** (contas de sistema típicas) salvo `--force`.
- Confirmação interativa: tem de **digitar o username** à letra (salvo `-y`/`--yes`).
- Sem `shell=True`; usa `subprocess` com lista de argumentos.

## Requisitos

- Pacote Debian `adduser` (fornece o comando `deluser`).
- Python 3 (stdlib: `pathlib`, `fcntl`, `json`, etc.).

## Uso

Nos exemplos com **`admin/del-user.py`**, execute a partir do diretório **`scripts/`** do repositório.

### Simular (sem root)

```bash
python3 admin/del-user.py -u alguem --dry-run
python3 admin/del-user.py -u alguem --dry-run --verbose
```

### Remover (interativo)

```bash
sudo python3 admin/del-user.py --username spammer
```

O script pede que escreva de novo o username para confirmar.

### Remover sem pergunta (automação / scripts)

```bash
sudo python3 admin/del-user.py -u spammer --yes
```

### Remover também ficheiros do utilizador fora da home

Cuidado: apaga **todos** os ficheiros detidos por esse UID no sistema.

```bash
sudo python3 admin/del-user.py -u spammer --yes --purge-all-files
```

### Não tocar no `users.json`

```bash
sudo python3 admin/del-user.py -u spammer --yes --skip-metadata
```

### Forçar remoção de conta “de sistema” (perigoso)

```bash
sudo python3 admin/del-user.py -u algum --yes --force
```

## Opções

| Opção | Significado |
|--------|-------------|
| `-u`, `--username` | Utilizador a remover (obrigatório). |
| `--dry-run` | Só mostra o plano; não exige root. |
| `-v`, `--verbose` | Mais saída (comando `deluser`, etc.). |
| `-y`, `--yes` | Não pede confirmação interativa. |
| `--force` | Ignora bloqueio a contas reservadas / UID &lt; 1000. |
| `--purge-all-files` | Usa `deluser --remove-all-files` em vez de `--remove-home`. |
| `--skip-metadata` | Não altera `/var/lib/runv/users.json`. |
| `--metadata-file` | Caminho alternativo ao JSON de metadados. |
| `--lock-file` | Lock `flock` para escrita do JSON (default runv). |

## Códigos de saída

- `0` — sucesso.
- `1` — validação / utilizador inexistente / confirmação cancelada.
- `2` — falha de `deluser` ou erro ao gravar metadados.

## Limitações

- Se o utilizador tiver sessões ativas ou processos a correr, `deluser` pode falhar ou comportar-se de forma estranha — termine sessões antes, se necessário.
- `--purge-all-files` pode afetar ficheiros em diretórios partilhados se o UID tiver dono em mais sítios; use com consciência.
- O script **não** revoga tokens ou chaves noutros serviços (só o que o SO e os teus processos fizerem com a conta removida).

## Exemplo de saída (trecho)

```
del-user.py — removendo 'spammer' (UID 1005)

  [exec] deluser --remove-home spammer
  [ok] deluser concluído para 'spammer'
  [metadata] removido registo de 'spammer' em /var/lib/runv/users.json

--- Resumo ---
  Conta removida: 'spammer'
  Próximo passo: verificar se não restam processos desse UID ...
```

## Relação com outros scripts

- **`create_runv_user.py`**: cria conta e acrescenta linha ao JSON.
- **`del-user.py`**: remove conta e remove a linha com o mesmo `username` no JSON (salvo `--skip-metadata`).

— runv.club
