# Guia do Administrador

Manual prático para operações administrativas do `runv-server` no servidor Debian do `runv.club`.

Use este documento como folha de referência rápida. Quando houver dúvida sobre comportamento detalhado, a fonte de verdade continua sendo o código dos scripts em `scripts/`, `tools/`, `site/`, `terminal/`, `patches/` e a árvore `docs/`.

## Convenções

Assuma:

```bash
cd /caminho/para/runv-server
```

Nos exemplos abaixo, substitua:

- `REPO` pelo caminho real do clone
- `USER` pelo username Unix do membro
- `EMAIL` pelo email do membro
- `PUBKEY.pub` pelo arquivo `.pub` aprovado

## Pré-requisitos

- Executar como `root` ou com `sudo`
- Servidor Debian com Python 3
- Quotas ext4 prontas se for usar quota automática
- Apache / DocumentRoot configurados se quiser refresh público automático

## Bootstrap inicial do servidor

Bootstrap conservador do host:

```bash
sudo python3 REPO/scripts/admin/starthere.py --verbose
```

Simular sem alterar:

```bash
sudo python3 REPO/scripts/admin/starthere.py --dry-run --verbose
```

## Ferramentas globais, MOTD, skel e IRC

Aplicar ferramentas globais, `MOTD`, `skel`, drop-in SSH jailed e patch IRC:

```bash
sudo python3 REPO/tools/tools.py
```

Simular:

```bash
sudo python3 REPO/tools/tools.py --dry-run --verbose
```

Reaplicar só arquivos e patch IRC, sem APT:

```bash
sudo python3 REPO/tools/tools.py --skip-apt
```

## Setup do onboarding via SSH (`entre`)

Instalar/configurar o usuário `entre` e o fluxo de pedido:

```bash
sudo python3 REPO/terminal/setup_entre.py --help
```

Exemplo de execução:

```bash
sudo python3 REPO/terminal/setup_entre.py
```

## Fila de pedidos

Fila padrão:

- `/var/lib/runv/entre-queue/`

Listar pedidos:

```bash
sudo ls -lah /var/lib/runv/entre-queue
```

Inspecionar um pedido JSON:

```bash
sudo cat /var/lib/runv/entre-queue/ID_DO_PEDIDO.json
```

Ou com formatação:

```bash
sudo jq . /var/lib/runv/entre-queue/ID_DO_PEDIDO.json
```

Log do onboarding:

```bash
sudo tail -n 200 /var/log/runv/entre.log
```

## Criar usuário novo

Fluxo canônico de provisionamento:

```bash
sudo python3 REPO/scripts/admin/create_runv_user.py \
  --username USER \
  --email EMAIL \
  --public-key-file PUBKEY.pub
```

Simular:

```bash
sudo python3 REPO/scripts/admin/create_runv_user.py \
  --username USER \
  --email EMAIL \
  --public-key-file PUBKEY.pub \
  --dry-run --verbose
```

Exigir quota pronta antes de criar:

```bash
sudo python3 REPO/scripts/admin/create_runv_user.py \
  --username USER \
  --email EMAIL \
  --public-key-file PUBKEY.pub \
  --require-quota
```

Criar sem quota:

```bash
sudo python3 REPO/scripts/admin/create_runv_user.py \
  --username USER \
  --email EMAIL \
  --public-key-file PUBKEY.pub \
  --no-quota
```

Criar sem jail:

```bash
sudo python3 REPO/scripts/admin/create_runv_user.py \
  --username USER \
  --email EMAIL \
  --public-key-file PUBKEY.pub \
  --no-jail
```

Criar com valores de quota explícitos:

```bash
sudo python3 REPO/scripts/admin/create_runv_user.py \
  --username USER \
  --email EMAIL \
  --public-key-file PUBKEY.pub \
  --quota-soft-mb 450 \
  --quota-hard-mb 500 \
  --quota-inode-soft 10000 \
  --quota-inode-hard 12000
```

Modo interativo:

```bash
sudo python3 REPO/scripts/admin/create_runv_user.py --interactive
```

## Atualizar usuário existente

Abrir menu interativo:

```bash
sudo python3 REPO/scripts/admin/update_user.py --interactive --username USER
```

Atualizar email:

```bash
sudo python3 REPO/scripts/admin/update_user.py --username USER --email EMAIL
```

Substituir chave pública:

```bash
sudo python3 REPO/scripts/admin/update_user.py \
  --username USER \
  --ssh-replace-file PUBKEY.pub
```

Acrescentar chave pública:

```bash
sudo python3 REPO/scripts/admin/update_user.py \
  --username USER \
  --ssh-append-file PUBKEY.pub
```

Definir nova senha de login:

```bash
sudo python3 REPO/scripts/admin/update_user.py --username USER --set-password
```

Alterar quota:

```bash
sudo python3 REPO/scripts/admin/update_user.py \
  --username USER \
  --quota-soft-mb 450 \
  --quota-hard-mb 500 \
  --quota-inode-soft 10000 \
  --quota-inode-hard 12000
```

Simular:

```bash
sudo python3 REPO/scripts/admin/update_user.py \
  --username USER \
  --email EMAIL \
  --dry-run
```

## Remover usuário / banimento técnico

Remover conta e home:

```bash
sudo python3 REPO/scripts/admin/del-user.py --username USER
```

Execução não interativa:

```bash
sudo python3 REPO/scripts/admin/del-user.py --username USER -y
```

Simular:

```bash
sudo python3 REPO/scripts/admin/del-user.py --username USER --dry-run
```

Observações:

- o script desmonta jail/binds antes de remover
- atualiza `users.json`
- pode sincronizar a landing pública após a remoção

## Remoção em massa

Ferramenta perigosa, só com backup:

```bash
sudo python3 REPO/scripts/doom/doom.py --help
```

Simular:

```bash
sudo python3 REPO/scripts/doom/doom.py --dry-run
```

## Reparar Gopher e Gemini

Reconfigurar infraestrutura de Gopher e Gemini:

```bash
sudo python3 REPO/scripts/admin/setup_alt_protocols.py
```

Simular:

```bash
sudo python3 REPO/scripts/admin/setup_alt_protocols.py --dry-run --verbose
```

Sem instalar pacotes:

```bash
sudo python3 REPO/scripts/admin/setup_alt_protocols.py --skip-install
```

Sem backfill de usuários:

```bash
sudo python3 REPO/scripts/admin/setup_alt_protocols.py --skip-backfill
```

## Site público e landing

Primeira montagem completa da landing / Apache:

```bash
sudo python3 REPO/site/genlanding.py
```

Somente sincronizar `site/public` + `members.json` para o DocumentRoot:

```bash
sudo python3 REPO/site/genlanding.py --sync-public-only \
  --document-root /var/www/runv.club/html \
  --members-users-json /var/lib/runv/users.json
```

Atualizar só `members.json`:

```bash
sudo python3 REPO/site/build_directory.py \
  --users-json /var/lib/runv/users.json \
  -o /var/www/runv.club/html/data/members.json
```

## Notícias

Publicar notícias novas:

```bash
sudo python3 REPO/site/news/publish_news.py
```

Simular:

```bash
sudo python3 REPO/site/news/publish_news.py --dry-run
```

Publicar sem sincronizar Apache:

```bash
sudo python3 REPO/site/news/publish_news.py --skip-genlanding
```

## Wiki

Gerar a wiki estática localmente a partir de `site/wiki/*.txt`:

```bash
python3 REPO/site/wiki/build_wiki.py
```

Depois, sincronizar a landing:

```bash
sudo python3 REPO/site/genlanding.py --sync-public-only \
  --document-root /var/www/runv.club/html \
  --members-users-json /var/lib/runv/users.json
```

## Email

Configurar Mailgun:

```bash
sudo python3 REPO/email/configure_mailgun.py --help
```

Configurar msmtp:

```bash
sudo python3 REPO/email/configure_msmtp.py --help
```

Modo legado SMTP/msmtp:

```bash
sudo python3 REPO/email/configure_msmtp_legacy.py --help
```

Diagnóstico:

```bash
sudo sh REPO/email/scripts/diagnose_msmtp.sh
```

Teste de envio:

```bash
sudo sh REPO/email/scripts/send_test_mail.sh
```

## IRC da casa

Aplicar/reaplicar a configuração IRC em todos os usuários:

```bash
sudo python3 REPO/patches/patch_irc.py --all-users
```

Aplicar a um único usuário:

```bash
sudo python3 REPO/patches/patch_irc.py --user USER
```

Simular:

```bash
sudo python3 REPO/patches/patch_irc.py --all-users --dry-run --verbose
```

Padrão atual:

- servidor `irc.tilde.chat`
- porta `6697`
- TLS ligado
- canal `#runv`
- comando de uso do membro: `chat`

## Moderação da comunidade e square

### Política

A política editorial e disciplinar está em:

- [site/wiki/05_punicoes-e-moderacao.txt](/Z:/Códigos/runv-server/site/wiki/05_punicoes-e-moderacao.txt)
- [site/wiki/04_regras-da-comunidade.txt](/Z:/Códigos/runv-server/site/wiki/04_regras-da-comunidade.txt)

### O que este repositório faz

Este repositório fornece os comandos para:

- criar conta
- atualizar conta
- remover conta
- regenerar presença pública
- aplicar infraestrutura e serviços

### O que este repositório não fornece

Este snapshot **não inclui** um CLI canônico próprio para moderar a `square` em nível de posts, salas, threads, silenciamento, suspensão comunitária ou revisão de conteúdo dentro da aplicação social.

Então, para `square`, a orientação operacional é:

- aplicar a moderação pelos controles nativos da própria plataforma `square` que vocês já operam
- registrar internamente a medida tomada
- se a medida envolver perda de acesso ao servidor, complementar com `del-user.py` ou `update_user.py`, conforme o caso

Exemplos de fluxo:

1. Advertência ou limitação comunitária na `square`: usar a ferramenta da própria `square`; não há comando neste repo.
2. Suspensão temporária na `square` sem remover conta Unix: executar na `square`; se necessário, ajustar quota, senha ou chaves com `update_user.py`.
3. Banimento permanente com encerramento de conta no servidor: moderar na `square` e depois executar `del-user.py`.

## Comandos de inspeção úteis

Ver quotas:

```bash
quota -vs USER
sudo repquota -s /home
```

Ver mounts:

```bash
mount | grep usrquota
findmnt /home
```

Ver Apache:

```bash
sudo apache2ctl configtest
sudo systemctl status apache2
```

Ver SSH:

```bash
sudo sshd -t
sudo systemctl status ssh
```

Ver usuários com sessão:

```bash
who
last
```

Ver logs do onboarding:

```bash
sudo tail -n 200 /var/log/runv/entre.log
```

## Fluxos rápidos

### Aprovar pedido e criar conta

```bash
sudo jq . /var/lib/runv/entre-queue/ID_DO_PEDIDO.json
sudo python3 REPO/scripts/admin/create_runv_user.py \
  --username USER \
  --email EMAIL \
  --public-key-file PUBKEY.pub
```

### Corrigir perfil público

```bash
sudo python3 REPO/site/genlanding.py --sync-public-only \
  --document-root /var/www/runv.club/html \
  --members-users-json /var/lib/runv/users.json
```

### Corrigir IRC de todos os usuários

```bash
sudo python3 REPO/patches/patch_irc.py --all-users
```

### Banir tecnicamente uma conta

```bash
sudo python3 REPO/scripts/admin/del-user.py --username USER -y
```

## Referências rápidas

- [docs/10-user-provisioning-and-admin-ops.md](/Z:/Códigos/runv-server/docs/10-user-provisioning-and-admin-ops.md)
- [docs/11-daily-operations.md](/Z:/Códigos/runv-server/docs/11-daily-operations.md)
- [docs/05-tools-and-system-experience.md](/Z:/Códigos/runv-server/docs/05-tools-and-system-experience.md)
- [docs/06-site-and-apache.md](/Z:/Códigos/runv-server/docs/06-site-and-apache.md)
- [docs/08-email.md](/Z:/Códigos/runv-server/docs/08-email.md)
- [docs/09-terminal-entre.md](/Z:/Códigos/runv-server/docs/09-terminal-entre.md)
