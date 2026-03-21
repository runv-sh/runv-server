# build_directory.py — gerar `members.json` para a landing

O script [`build_directory.py`](build_directory.py) lê o ficheiro interno **`users.json`** (criado pelo [`create_runv_user.py`](../scripts/create_runv_user.md)) e gera um JSON **público** consumido pelo JavaScript da landing (`public/assets/app.js`): posiciona os **pontos** (links para `/~utilizador/`) com base em `username`, `since` e `path`.

- **Python 3**, só biblioteca padrão (sem PyPI).
- **Não** é um servidor web: corre na linha de comando ou via **cron**.

Visão geral do `site/`: [README.md](README.md).

## O que entra e o que sai

### Entrada (`--users-json`)

Caminho para o JSON do provisionador (por omissão no servidor: `/var/lib/runv/users.json`). O ficheiro deve ser uma **lista** de objectos; cada entrada com `username` (string) é considerada.

Se o caminho **ainda não existir** (bootstrap antes do primeiro `create_runv_user.py`), o script **não falha**: emite um aviso em stderr, assume **lista vazia** e gera `members.json` com `[]`. Podes também criar manualmente `/var/lib/runv/users.json` com conteúdo `[]` se preferires.

O script **ignora** linhas que não sejam dicionários ou sem `username` válido. Se o ficheiro **existir** mas o JSON for inválido ou não for uma lista, o script termina com erro.

### Saída (`-o` / `--output`)

Um único ficheiro JSON (por omissão: **`site/public/data/members.json`**, relativo à pasta onde está o script).

Cada elemento do array público tem:

| Campo | Significado |
|--------|-------------|
| `username` | Nome Unix do membro |
| `since` | Valor de `created_at` no `users.json`, se existir e for string (senão `""`) |
| `path` | URL do site pessoal, ex. `"/~alice/"` |
| `homepage_mtime` | *(Opcional)* Só se usares `--homes-root`: ISO UTC da última modificação de `public_html/index.html` desse utilizador |

### Privacidade

**Nunca** são copiados para o ficheiro público: email, fingerprint SSH, quotas, nem outros campos internos do `users.json`.

## Opções da linha de comando

| Opção | Curto | Por omissão | Descrição |
|--------|------|-------------|-----------|
| `--users-json` | — | `/var/lib/runv/users.json` | Ficheiro fonte (lista JSON) |
| `--output` | `-o` | `site/public/data/members.json`* | Onde gravar o JSON público |
| `--homes-root` | — | *(não definido)* | Se definires (ex. `/home`), tenta acrescentar `homepage_mtime` por utilizador |
| `--dry-run` | — | — | Imprime o JSON no **stdout**; não grava ficheiro |

\*O caminho por omissão é relativo ao directório do script: `<pasta_do_build_directory.py>/public/data/members.json`.

## Como executar (a partir da raiz do repositório)

### 1. Servidor em produção

Com acesso a `users.json` e, de preferência, a `/home` para `homepage_mtime`:

```bash
cd /caminho/ao/runv-server
sudo python3 site/build_directory.py \
  --users-json /var/lib/runv/users.json \
  --homes-root /home \
  -o /var/www/runv.club/html/data/members.json
```

Ajusta `-o` ao **DocumentRoot** real (o mesmo que usaste com [`genlanding.py`](genlanding.md), ex. `/var/www/runv.club/html/data/members.json`).

### 2. Máquina local (sem `/var/lib/runv`)

Usa o exemplo do repo ou uma cópia sanitizada do `users.json`:

```bash
cd /caminho/ao/runv-server
python3 site/build_directory.py \
  --users-json site/example-users.json \
  -o site/public/data/members.json
```

Assim podes editar a landing e recarregar o browser sem tocar no servidor.

### 3. Pré-visualizar no terminal (dry-run)

```bash
python3 site/build_directory.py \
  --users-json site/example-users.json \
  --dry-run
```

Útil para validar o JSON sem sobrescrever ficheiros.

### 4. Sem `--homes-root`

Se não quiseres (ou não puderes) ler as homes:

```bash
sudo python3 site/build_directory.py \
  --users-json /var/lib/runv/users.json \
  -o /var/www/runv.club/html/data/members.json
```

A lista aparece na landing; não haverá `homepage_mtime` (o JS deve tolerar campo em falta).

## Erros comuns

| Mensagem / situação | Causa provável |
|---------------------|----------------|
| `Ficheiro inexistente` | `--users-json` aponta para um path errado ou ficheiro ainda não criado |
| `Formato inválido: esperada lista JSON` | O ficheiro não é um array JSON no topo |
| Permissão negada ao gravar `-o` | Corre com `sudo` ou escolhe um `-o` onde o teu utilizador possa escrever |
| `homepage_mtime` nunca aparece | Falta `--homes-root` ou não existe `~/public_html/index.html` legível para esse user |
| «Escritos N membros» mas a página não mostra pontos | Gravaste em `site/public/data/` no repo; o **site público** usa o **DocumentRoot** do Apache (ex. `/var/www/runv.club/html/`). Usa `-o /var/www/runv.club/html/data/members.json` ou `sudo cp …` para lá, ou volta a correr `genlanding.py` depois de actualizar `members.json` na árvore que ele copia. |

## Cron (exemplo)

Regenerar a cada 15 minutos no servidor (caminhos de exemplo):

```cron
*/15 * * * * root python3 /opt/runv-server/site/build_directory.py --users-json /var/lib/runv/users.json --homes-root /home -o /var/www/runv.club/html/data/members.json
```

Garante que o path do `python3`, do script e do `-o` coincidem com a tua instalação.

## Relação com outros ficheiros

| Ferramenta | Papel |
|------------|--------|
| [`create_runv_user.py`](../scripts/create_runv_user.md) | Mantém `/var/lib/runv/users.json` |
| [`genlanding.py`](genlanding.md) | Copia `public/` para o Apache; o **cron** do `build_directory.py` deve escrever `members.json` **dentro** desse DocumentRoot |
| `public/assets/app.js` | Faz `fetch` a `data/members.json` (caminho relativo à página) |

Depois de alterar `members.json` no servidor, não é obrigatório recarregar o Apache — é ficheiro estático servido como qualquer outro.
