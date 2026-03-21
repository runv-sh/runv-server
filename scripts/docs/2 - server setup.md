# runv.club – Fase 2: Apache, UserDir e o primeiro utilizador com site pessoal

## Objetivo

Este documento continua a configuração inicial do servidor **runv.club** em **Debian 13**.

Neste ponto, o servidor já tem:

- um usuário administrador sem root (`pmurad`)
- login por chave SSH funcionando
- login como root desativado no SSH
- autenticação por senha desativada no SSH

Agora o objetivo é montar o **primeiro caminho real de publicação web por utilizador** (`~username`):

- instalar o Apache
- habilitar páginas `~username`
- criar um usuário de teste
- fazer `~/public_html` funcionar
- confirmar que `http://SERVIDOR/~testuser/` carrega

Esta é a primeira prova concreta de que a máquina serve sites pessoais por conta Unix no runv.club.

---

## O que estamos construindo

Neste desenho, cada utilizador publica um site a partir do diretório home.

O padrão clássico é:

- existe conta de usuário
- o usuário tem uma pasta chamada `public_html`
- o Apache serve essa pasta em:

```text
http://seu-dominio/~username/
```

Por exemplo, no runv.club, o alvo futuro é:

```text
http://runv.club/~testuser/
```

Para testes em VM local antes do DNS estar pronto, pode ser algo como:

```text
http://192.168.x.x/~testuser/
```

ou

```text
http://runv-debian/~testuser/
```

conforme sua rede e resolução de nomes.

---

## Aviso importante antes de começar

**Não** instale pacotes extras aleatórios ainda.

Você **não** precisa agora de:

- PHP
- MariaDB
- PostgreSQL
- Node.js
- Docker
- Certbot
- servidor de e-mail
- BBJ
- ttbp
- botany

Isso seria prematuro e desnecessário.

Por enquanto você só precisa do mínimo para provar:

1. Apache funciona
2. `mod_userdir` funciona
3. permissões estão corretas
4. publicação a partir do home do usuário funciona

Até isso funcionar, o resto é ruído.

---

## Passo 1 – Atualizar listas de pacotes

Entre como `pmurad` e execute:

```bash
sudo apt update
```

Em seguida, atualize os pacotes instalados:

```bash
sudo apt upgrade -y
```

Assim a máquina fica atualizada antes de instalar o Apache.

---

## Passo 2 – Instalar o Apache

Instale o Apache com:

```bash
sudo apt install -y apache2
```

Após a instalação, verifique se o serviço está em execução:

```bash
sudo systemctl status apache2
```

Você deve ver algo como:

```text
active (running)
```

Se quiser uma verificação mais curta:

```bash
systemctl is-active apache2
```

Resultado esperado:

```text
active
```

Se o Apache não estiver em execução, inicie-o:

```bash
sudo systemctl start apache2
```

E habilite na inicialização:

```bash
sudo systemctl enable apache2
```

---

## Passo 3 – Testar o Apache a partir da própria VM

Teste localmente primeiro, de dentro do Debian:

```bash
curl http://localhost
```

Você deve receber HTML da página padrão do Apache.

Se o `curl` não estiver instalado:

```bash
sudo apt install -y curl
```

Se o Apache estiver funcionando, isso confirma que o servidor web está ativo antes de mexer no `UserDir`.

---

## Passo 4 – Liberar HTTP no firewall

Se você habilitou o UFW antes, é preciso liberar o tráfego web.

Verifique o status do firewall:

```bash
sudo ufw status
```

Libere o Apache:

```bash
sudo ufw allow 'Apache'
```

Verifique de novo:

```bash
sudo ufw status
```

Você deve ver a porta 80 liberada.

Se o UFW ainda não estiver habilitado, não é fatal em um sandbox de VM. Mesmo assim, se você pretende usá-lo, este é o momento certo para abrir o HTTP.

---

## Passo 5 – Testar o Apache de outra máquina

No seu Windows, abra o navegador e tente:

```text
http://IP_DA_VM/
```

Exemplo:

```text
http://192.168.50.120/
```

Você deve ver a página padrão do Apache.

Se **não** vir, o problema é um destes:

- Apache não está em execução
- firewall bloqueando a porta 80
- IP da VM errado
- problema de bridge/rede no Proxmox
- o navegador está batendo na máquina errada

**Não** continue até a página padrão do Apache funcionar.

---

## Passo 6 – Habilitar o módulo UserDir

É o recurso que permite:

```text
/~username/
```

Habilite com:

```bash
sudo a2enmod userdir
```

Verifique a sintaxe da configuração do Apache:

```bash
sudo apache2ctl configtest
```

Resultado esperado:

```text
Syntax OK
```

Em seguida, recarregue o Apache:

```bash
sudo systemctl reload apache2
```

Neste ponto o Apache já conhece `~username`, mas ainda não há conteúdo de usuário para servir.

---

## Passo 7 – Inspecionar a configuração do UserDir

O pacote Apache do Debian costuma colocar a configuração do módulo em:

```text
/etc/apache2/mods-available/userdir.conf
```

Leia o arquivo:

```bash
cat /etc/apache2/mods-available/userdir.conf
```

Provavelmente você verá algo como:

```apache
UserDir public_html
<Directory /home/*/public_html>
    AllowOverride FileInfo AuthConfig Limit Indexes
    Options MultiViews Indexes SymLinksIfOwnerMatch IncludesNoExec
    Require method GET POST OPTIONS
</Directory>
```

O ponto principal é este:

```apache
UserDir public_html
```

Isso significa que o Apache procurará conteúdo em:

```text
/home/NOME_DO_USUARIO/public_html
```

Ótimo. É o que queremos.

---

## Passo 8 – Criar um usuário de teste

Crie uma conta de teste não administrativa para o teste de publicação via UserDir.

**Não** use `pmurad` nesse teste.  
Mantenha papéis de admin e usuário comum separados.

Crie o usuário:

```bash
sudo adduser testuser
```

Você pode dar uma senha temporária simples para uso em laboratório.

Confirme que o home existe:

```bash
ls -ld /home/testuser
```

---

## Passo 9 – Criar public_html e uma página de teste

Crie a pasta de publicação:

```bash
sudo -u testuser mkdir -p /home/testuser/public_html
```

Crie um arquivo HTML básico:

```bash
sudo -u testuser tee /home/testuser/public_html/index.html > /dev/null <<'EOF'
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>testuser no runv.club</title>
</head>
<body>
  <h1>Funcionou.</h1>
  <p>Esta é a primeira página pessoal no runv.club.</p>
</body>
</html>
EOF
```

Verifique o arquivo:

```bash
ls -l /home/testuser/public_html/index.html
```

---

## Passo 10 – Ajustar permissões do jeito certo

É aqui que iniciantes costumam errar.

O Apache precisa conseguir:

1. entrar em `/home/testuser`
2. entrar em `/home/testuser/public_html`
3. ler `/home/testuser/public_html/index.html`

Defina as permissões assim:

```bash
sudo chmod 755 /home/testuser
sudo chmod 755 /home/testuser/public_html
sudo chmod 644 /home/testuser/public_html/index.html
```

Confira:

```bash
namei -l /home/testuser/public_html/index.html
```

Se o `namei` não for encontrado, instale o pacote que o fornece:

```bash
sudo apt install -y util-linux
```

O importante é que o usuário do Apache (`www-data`) consiga percorrer e ler o que precisa.

---

## Passo 11 – Testar a página do usuário localmente

De dentro do Debian:

```bash
curl http://localhost/~testuser/
```

A saída esperada deve incluir o seu HTML.

Você também pode testar só o cabeçalho:

```bash
curl -I http://localhost/~testuser/
```

Um resultado saudável parece com:

```text
HTTP/1.1 200 OK
```

Se aparecer:

```text
403 Forbidden
```

o problema quase certamente são permissões.

Se aparecer:

```text
404 Not Found
```

o caminho, o nome de usuário ou a configuração do módulo está errado.

---

## Passo 12 – Testar no navegador

Agora, no Windows, abra:

```text
http://IP_DA_VM/~testuser/
```

Se a página carregar, você tem o primeiro caminho real de publicação por utilizador.

Esse é o marco.

---

## Passo 13 – Entender os três modos de falha mais comuns

### Falha 1 – 403 Forbidden

Causa:
- `/home/testuser` está muito restritivo
- permissões de `public_html` erradas
- permissões do arquivo erradas

Correção:
```bash
sudo chmod 755 /home/testuser
sudo chmod 755 /home/testuser/public_html
sudo chmod 644 /home/testuser/public_html/index.html
```

### Falha 2 – 404 Not Found

Causa:
- módulo `userdir` não habilitado
- nome da pasta errado
- nome do arquivo ausente
- erro de digitação no nome de usuário

Verifique:
```bash
sudo a2query -m userdir
ls -l /home/testuser/public_html
```

### Falha 3 – Página do Apache funciona, mas `~testuser` não

Causa:
- módulo carregado, mas permissões quebradas
- `userdir.conf` alterado incorretamente
- Apache não recarregado após habilitar o módulo

Correção:
```bash
sudo apache2ctl configtest
sudo systemctl reload apache2
```

---

## Passo 14 – Comandos úteis para diagnóstico

Se algo falhar, estes são os primeiros comandos a usar.

### Status do Apache
```bash
sudo systemctl status apache2
```

### Verificar sintaxe da configuração
```bash
sudo apache2ctl configtest
```

### Confirmar que o módulo está habilitado
```bash
sudo a2query -m userdir
```

### Ler o log de erro do Apache
```bash
sudo tail -n 50 /var/log/apache2/error.log
```

### Ler o log de acesso
```bash
sudo tail -n 50 /var/log/apache2/access.log
```

### Testar localmente
```bash
curl -I http://localhost/~testuser/
```

Esses logs importam. Não adivinhe quando o Apache já está dizendo o que está quebrado.

---

## Passo 15 – Como fica o sucesso

Você termina esta fase quando **tudo** isto for verdade:

- Apache instalado
- Apache inicia automaticamente
- página padrão acessível
- módulo `userdir` habilitado
- `testuser` existe
- `/home/testuser/public_html/index.html` existe
- `http://localhost/~testuser/` retorna `200 OK`
- `http://IP_DA_VM/~testuser/` abre no navegador

Se algum item for falso, a fase não terminou.

---

## Passo 16 – O que vem depois

Só depois disso funcionando você deve ir para a camada seguinte:

1. preparar `/etc/skel`
2. definir os arquivos padrão que novos usuários recebem
3. criar um modelo de homepage inicial mais limpo
4. documentar como novos usuários publicam páginas
5. mais tarde: adicionar ttbp, botany e outras ferramentas sociais

**Não** pule para software de comunidade antes de provar que o caminho de publicação web funciona.

---

## Resumo rápido de comandos

Para conveniência, o fluxo principal de novo:

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y apache2 curl
sudo systemctl enable apache2
sudo systemctl start apache2

curl http://localhost

sudo ufw allow 'Apache'

sudo a2enmod userdir
sudo apache2ctl configtest
sudo systemctl reload apache2

sudo adduser testuser

sudo -u testuser mkdir -p /home/testuser/public_html

sudo -u testuser tee /home/testuser/public_html/index.html > /dev/null <<'EOF'
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>testuser no runv.club</title>
</head>
<body>
  <h1>Funcionou.</h1>
  <p>Esta é a primeira página pessoal no runv.club.</p>
</body>
</html>
EOF

sudo chmod 755 /home/testuser
sudo chmod 755 /home/testuser/public_html
sudo chmod 644 /home/testuser/public_html/index.html

curl -I http://localhost/~testuser/
```

---

## Nota final

Este documento é propositalmente detalhado porque iniciantes costumam falhar aqui por motivos chatos:

- permissões erradas
- esquecer de recarregar o serviço
- IP errado
- firewall não aberto
- testar na ordem errada

Faça na ordem e funciona.  
Faça aleatoriamente e você perde tempo.
