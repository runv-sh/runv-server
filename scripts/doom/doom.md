# `doom.py` — reset em massa de utilizadores runv

Script de administração que **remove todas as contas runv** registadas em `users.json`, **excepto** um conjunto **protegido**. A remoção real (Unix, quotas, metadados) é feita pelo mesmo fluxo que o banimento manual: chama [`../admin/del-user.py`](../admin/del-user.py) com `-y` para cada utilizador a apagar.

**Aviso:** operação **irreversível**. Use primeiro `--dry-run` se tiver dúvidas.

## O que é “protegido”

O script **nunca** passa ao `del-user.py` ninguém que pertença ao conjunto **protegido**:

```
protegido = { conta de referência (--keep / omissão) } ∪ { quem está ligado ao processo }
```

### Conta de referência (`keeper`)

- Com **`--keep USER`**: essa conta é a referência explícita (e entra no protegido).
- Sem `--keep`, com **EUID root** e **`SUDO_USER`** definido (caso típico `sudo python3 doom.py`): a referência é o utilizador em `SUDO_USER`.
- **Root sem `SUDO_USER`**: é **obrigatório** `--keep USER` (evita ambiguidade).
- **Sem ser root** (ex.: só inspeção): a referência é o utilizador do **real UID** (útil em cenários limitados; a remoção real ainda exige root).

### Quem está ligado ao processo (nunca apagado)

Mesmo que `--keep` aponte para **outra** conta, o script **não apaga**:

| Origem | Motivo |
|--------|--------|
| `SUDO_USER` | Quem executou `sudo`. |
| Real UID e **effective** UID | Cobre `sudo -u bob`: protege quem invocou e o utilizador efectivo. |
| `root` | Se o processo corre como root **e** não há `SUDO_USER`, `root` fica protegido se existir no JSON. |

Os nomes são normalizados para bater com entradas típicas de `users.json` (ex.: minúsculas, regra de username runv).

## Fonte da lista de utilizadores

- Lê **apenas** os `username` presentes no ficheiro JSON de metadados (por omissão `/var/lib/runv/users.json`).
- **Não** enumera o `/etc/passwd` por conta própria: o que não está no JSON **não** é alvo do doom (mas contas órfãs no sistema continuam fora deste script).

## Fluxo de execução

1. Determina `keeper` e o conjunto **protegido** (referência + quem rodou).
2. Lista todos os utilizadores no JSON **fora** do protegido → **vítimas**.
3. Se não houver vítimas, termina sem chamar `del-user.py`.
4. **Confirmação:** a menos que use `--yes`, é preciso escrever **`DOOM`** em maiúsculas.
5. Em modo real, exige **root** (EUID 0).
6. Para cada vítima, invoca `del-user.py` com `--yes` e os mesmos caminhos de metadata/lock que indicar.

## Modo dry-run

`--dry-run` **não exige root**. Mostra quem seria removido e corre o `del-user.py` em dry-run por cada vítima (sem alterações reais).

## Opções principais

| Opção | Função |
|--------|--------|
| `--keep USER` | Referência explícita; obrigatório em root puro sem `SUDO_USER`. |
| `--yes` / `-y` | Sem prompt `DOOM` (automação; perigoso). |
| `--dry-run` | Simulação. |
| `--metadata-file`, `--lock-file` | Sobrescreve caminhos do JSON e do lock (útil em testes). |
| `--purge-all-files` | Repassa ao `del-user.py` (além de remover home). |
| `-v` / `--verbose` | Mais saída no `del-user.py`. |

## Exemplos

```bash
# Conta a manter = quem fez sudo (ex.: alice); apaga todos os outros no JSON
sudo python3 /caminho/scripts/doom/doom.py

# Root em consola sem SUDO_USER: dizer explicitamente quem fica como referência
sudo python3 /caminho/scripts/doom/doom.py --keep alice

# Simular sem apagar nada
python3 /caminho/scripts/doom/doom.py --dry-run

# Automação (sem confirmação DOOM)
sudo python3 /caminho/scripts/doom/doom.py --yes
```

## Nota sobre “ficar só um utilizador”

O objectivo habitual é deixar **uma** conta runv no JSON (a referência). Se `--keep` for diferente de quem invocou o script, **várias** contas podem permanecer no ficheiro (referência + todas as que o doom é obrigado a proteger). Isto é intencional: **nunca** apagar quem está ligado ao processo.

## Dependências

- Python 3, acesso root para execução real.
- `scripts/admin/del-user.py` no repositório, relativo a `doom.py` (`../admin/del-user.py`).

Versão do script documentada aqui: alinhada a `doom.py` (ver `--version`).
