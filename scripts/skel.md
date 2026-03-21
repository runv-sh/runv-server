# skel.py — preparar `/etc/skel` (runv.club)

**Versão 0.02** · runv.club

Script para **administradores** prepararem o diretório `/etc/skel` no **Debian** (ex.: Debian 13), de modo que `adduser` copie automaticamente uma home inicial com `public_html`, página de boas-vindas e README para novos usuários.

- **Não** cria usuários.
- **Não** altera Apache, SSH, chaves ou pacotes.
- Só cria/atualiza ficheiros sob `/etc/skel` (com segurança e idempotência).

**Ambiente:** execute no servidor Linux como **root** (ou `sudo`). No Windows, use apenas para revisão do código; a execução real é no Debian.

## Objetivo

- Garantir `/etc/skel/public_html/` e `/etc/skel/public_html/index.html`.
- Garantir `/etc/skel/README.md` (texto de ajuda para quem entra na shell).
- Aplicar permissões: diretório `755`, ficheiros `644`.
- Ser **idempotente**: voltar a correr não apaga nada; sem `--force`, ficheiros existentes são **preservados**.

## Requisitos

- Python 3 (stdlib apenas; usa `pathlib`).
- Permissões de root para escrita em `/etc/skel`.

## Como executar

Nos exemplos com **`admin/skel.py`**, execute a partir do diretório **`scripts/`** do repositório.

Torne o script executável (opcional):

```bash
sudo chmod +x admin/skel.py
```

(a partir do diretório `scripts/` do repositório; ou use o caminho absoluto até `scripts/admin/skel.py`.)

### Simular (sem root, sem alterar disco)

```bash
python3 admin/skel.py --dry-run
python3 admin/skel.py --dry-run --verbose
```

### Aplicar de verdade

```bash
sudo python3 admin/skel.py
sudo python3 admin/skel.py --verbose
```

### Regenerar templates (sobrescrever)

Se `index.html` ou `README.md` já existirem em `/etc/skel` e quiser substituir pelo conteúdo embutido no script:

```bash
sudo python3 admin/skel.py --force
```

## Opções

| Opção | Efeito |
|--------|--------|
| `--dry-run` | Mostra o que seria criado/atualizado; **não** exige root; não escreve ficheiros. |
| `--verbose` | Mais detalhe (ex.: `chmod` explícito). |
| `--force` | Sobrescreve `index.html` e `README.md` se já existirem. Sem `--force`, são preservados. |
| `--version` | Mostra versão do script. |

## Exemplos de saída

### Dry-run (trecho)

```
Modo dry-run — nenhuma alteração em disco.

  [dry-run] criaria diretório: /etc/skel/public_html
  [dry-run] criaria arquivo: /etc/skel/public_html/index.html
  [dry-run] criaria arquivo: /etc/skel/README.md

Resumo: nada foi gravado. Execute sem --dry-run como root para aplicar.
```

### Execução real (trecho)

```
skel.py — preparando /etc/skel para runv.club

  [dir] criado: /etc/skel/public_html
  [file] criado: /etc/skel/public_html/index.html
  [file] criado: /etc/skel/README.md

Aplicando permissões...

--- Resumo ---
  ...
```

Segunda execução **sem** `--force`: deve aparecer `preservado` para os ficheiros já existentes.

## Limitações

- Não altera `/etc/skel` fora do que o script define (outros ficheiros que o admin adicionar manualmente ficam).
- Não remove ficheiros.
- Não cria `public_html` na home de utilizadores **já** existentes — só para **novos** utilizadores criados **depois** de preparar o skel; utilizadores antigos precisam copiar à mão ou de outro procedimento.

## Como testar no Debian 13

1. **Preparar o skel**

   ```bash
   sudo python3 ./admin/skel.py --verbose
   ```

2. **Criar um utilizador de teste**

   ```bash
   sudo adduser testuser
   ```

   (ou `adduser --disabled-password` se o seu fluxo não precisar de password interativa.)

3. **Verificar cópia a partir de `/etc/skel`**

   Como `testuser` (ou inspecionando a home):

   ```bash
   sudo ls -la /home/testuser/
   sudo ls -la /home/testuser/public_html/
   sudo cat /home/testuser/public_html/index.html | head
   sudo cat /home/testuser/README.md | head
   ```

4. **Permissões típicas para publicação web** (o README em `/etc/skel` explica; após `adduser`, confirme se a sua política exige `chmod` na home — muitas instalações já ficam com home `755` e `public_html` herdado de `755`).

5. **Prova no browser** (se DNS e Apache estiverem corretos): `http://runv.club/~testuser/`

## Ficheiros geridos pelo script

| Caminho | Conteúdo |
|---------|-----------|
| `/etc/skel/public_html/index.html` | Página inicial estática em português (CSS embutido, visual simples). |
| `/etc/skel/README.md` | Instruções para o utilizador na shell. |

## Créditos

runv.club.
