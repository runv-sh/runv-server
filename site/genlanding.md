# genlanding.py — Apache para a landing runv

Script em [`genlanding.py`](genlanding.py) (Python 3, stdlib) que configura o **Apache** em Debian para:

- servir a landing estática (`site/public/`) num **VirtualHost** dedicado;
- activar **`mod_userdir`** e **`mod_rewrite`** (redirect **www → apex** em HTTP);
- em **produção** e em **`--dev`**: por omissão desactiva `000-default.conf` (salvo `--keep-default-site`) para pedidos por IP servirem a landing; opcional **Certbot** em produção (`--certbot`).

Não substitui o manual de [`scripts/docs/2 - server setup.md`](../scripts/docs/2%20-%20server%20setup.md) para aprender permissões e diagnóstico; automatiza o caminho habitual após DNS e pacotes base.

## Pré-requisitos

- **Debian** com `apache2` instalado (recomendado: [`scripts/admin/starthere.py`](../scripts/admin/starthere.py) antes).
- **Produção:** DNS de `runv.club` e `www.runv.club` a apontar para o servidor; porta **80** acessível se fores usar **Certbot**.
- Executar como **root** (`sudo`), excepto `--dry-run` (permite pré-visualizar noutra máquina).

## Uso rápido

```bash
cd /caminho/ao/runv-server
sudo python3 site/genlanding.py
```

Produção (valores por omissão: `ServerName` **runv.club**, `DocumentRoot` **`/var/www/runv.club/html`**, ficheiro **`/etc/apache2/sites-available/runv.club.conf`**).

Pré-visualizar sem alterar nada:

```bash
python3 site/genlanding.py --dry-run
```

## Flags principais

| Flag | Descrição |
|------|-----------|
| `--dev` | Modo **teste local**: `runv.local`, `DocumentRoot` `/var/www/runv-dev/html`, ficheiro `runv-dev.conf`; por omissão **desactiva** `000-default` (igual à produção). |
| `--domain NAME` | Substitui o `ServerName` (e `www.NAME` como alias). |
| `--document-root PATH` | Substitui o `DocumentRoot`. |
| `--source PATH` | Origem da landing (default: `site/public` relativo ao script). |
| `--keep-default-site` | Mantém `000-default.conf` activo (**produção** e **`--dev`**). Com `000-default` activo, pedidos por **IP** não casam com `ServerName` e continuam a mostrar a página Debian; ver secção abaixo. |
| `--certbot` | Depois de configurar HTTP, executa `certbot --apache -d <domínio> -d www.<domínio>`. **Incompatível com `--dev`.** |
| `--dry-run` | Mostra o VirtualHost e comandos; não exige root. |

## Pedidos por IP vs `ServerName`

Com **vários** `VirtualHost *:80`, o Apache escolhe o vhost pelo cabeçalho **`Host`**. Se pedires `http://192.168.50.85/`, o `Host` é o IP (ou não coincide com `runv.local`) → o servidor usa o vhost **por defeito** na porta 80, que no Debian costuma ser **`000-default`** (`/var/www/html`, página “It works!”).

- **Por omissão** (`--dev` ou produção **sem** `--keep-default-site`): o script desactiva `000-default`; o vhost runv fica como único (ou primeiro) em `:80` e **pedidos por IP** passam a servir a **landing** no `DocumentRoot` configurado.
- Com **`--keep-default-site`**: mantém-se `000-default`; para ver a landing usa **`http://runv.local/`** (com `/etc/hosts`) ou força o host no cliente:

  ```bash
  curl -sI -H 'Host: runv.local' http://192.168.50.85/
  ```

Se `curl http://runv.local/` não devolver nada na VM, confirma que **`runv.local`** está em **`/etc/hosts`** a apontar para o IP correcto (ex. `127.0.0.1` ou o IP da interface).

## Modo `--dev` (VM ou laptop)

1. Correr: `sudo python3 site/genlanding.py --dev` (por omissão desactiva `000-default`; usa `--keep-default-site` se quiseres manter a página Debian em paralelo).
2. Opcional: no **cliente** ou na VM, editar `/etc/hosts` para nome bonito:

   ```text
   127.0.0.1  runv.local  www.runv.local
   ```

   (Se o Apache estiver noutra máquina, usa o IP dessa máquina em vez de `127.0.0.1`.)

3. Abrir `http://runv.local/` ou `http://IP_DA_VM/` no browser (sem `--keep-default-site`). O redirect **www → apex** usa **HTTP** (não uses Certbot em `--dev`).

## Ordem sugerida (produção)

1. `starthere.py` — pacotes, Apache a correr, quotas, etc.
2. `genlanding.py` — VirtualHost + cópia da landing.
3. Opcional: `genlanding.py --certbot` **numa segunda execução** (ou a primeira já com `--certbot` se tudo estiver pronto), **depois** de confirmar HTTP no domínio.
4. **Cron** para [`build_directory.py`](build_directory.py) gerar `members.json` no `DocumentRoot` (ver [README.md](README.md)).

## Relação com `build_directory.py`

- `genlanding.py` **copia** o conteúdo actual de `public/` (incluindo `data/members.json` se existir).
- A lista de membros actualizada vem do **cron** que corre `build_directory.py` com `-o` apontando para  
  `.../html/data/members.json` (o mesmo `DocumentRoot` que usaste no genlanding).

### Lista pública (só utilizadores reais)

- **`public/data/members.json`** no repositório deve ser **`[]`** (placeholder). **Não** versionar nomes fictícios como membros da comunidade; a única fonte de verdade para quem aparece no site é **`/var/lib/runv/users.json`**, filtrada por `build_directory.py`.
- **`site/example-users.json`** existe só para desenvolvimento / testes locais com `build_directory.py --users-json`, não para ship em produção como se fossem contas reais.
- **Atenção:** cada execução de `genlanding.py` **substitui** o `DocumentRoot` pela cópia de `public/`; isso repõe `members.json` para o que está no repo (tipicamente `[]`). Depois de um deploy com `genlanding.py`, volta a correr **`build_directory.py`** (ou espera o cron) para repor a lista gerada a partir de `users.json`.

## O que o script não faz

- Não cria utilizadores Unix nem mexe em `users.json`.
- Não configura **firewall** nem **DNS**.
- Não valida certificados além do que o **Certbot** fizer se invocares `--certbot`.

## Ficheiros tocados

| Caminho | Acção |
|---------|--------|
| `/etc/apache2/sites-available/runv.club.conf` ou `runv-dev.conf` | Criado / sobrescrito |
| `DocumentRoot` (ex. `/var/www/runv.club/html`) | Conteúdo substituído pela cópia de `public/` |
| `a2enmod userdir`, `rewrite` | Activados |
| `a2dissite 000-default` | Sem `--keep-default-site` (produção ou `--dev`); falha silenciosa se já desactivado |
| `a2ensite` | Activa o site runv |

Versão do script: ver `python3 site/genlanding.py --version`.
