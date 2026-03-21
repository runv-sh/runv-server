# Experiência do usuário — runv.club (`tools/`)

Visão para **quem entra no servidor** pela primeira vez (e para quem documenta suporte).

## O que aparece no login

1. **MOTD** — O Debian executa os scripts em `/etc/update-motd.d/`. O fragmento **`60-runv`** mostra:
   - logótipo **RUNV** (mesmo desenho UTF-8 da landing) **só nesse bloco** em verde;
   - tagline `.club — um computador para compartilhar` (sem estatísticas no MOTD; o comando **`runv-status`** existe mas **não** é listado aqui e só o utilizador **`pmurad-admin`** pode executá-lo);
   - **Comandos úteis** em lista, com nome a verde e descrição a cinza (ANSI), alinhada ao texto do `runv-help`;
   - secção **Últimos usuários online**: grelha **3×3** com até **9 nomes únicos** (fonte: **`last`** / wtmp; ordem = atividade recente; cada utilizador só aparece **uma** vez; ignora linhas `reboot` / `wtmp` e os utilizadores **`entre`** e **`root`**). Em **Debian 13+**, o binário **`last`** vem do pacote **`wtmpdb`** (o `tools.py` instala-o). O fragmento tenta **`/usr/bin/last`** se o PATH de `update-motd.d` não incluir `last`. Se aparecer *sem registos recentes em wtmp*, o ficheiro de logins ainda não tem entradas (ex.: sem logins SSH registados).
   - linha final: **digite `runv-help` para começar**.

2. **Prompt da shell** — Depende do shell padrão (geralmente Bash no Debian). O que o usuário **herda** da home vem do **`/etc/skel`** no momento em que a conta foi criada.

## Comandos locais do runv

| Comando | Função |
|---------|--------|
| **`runv-help`** | Texto de ajuda: o que é o runv, comandos úteis, dicas, link do site. |
| **`runv-links`** | Links: runv.club, Portal IDEA, etc. |
| **`runv-status`** | (Só **`pmurad-admin`**) hostname, uptime, memória, disco, `who`. Não aparece no MOTD nem em `runv-help`. |

Todos são **shell scripts** em **`/usr/local/bin`**, com cores ANSI simples, texto em **português**. Não dependem de Python na sessão do usuário.

## O que o usuário recebe na home (contas novas)

Quando um administrador cria a conta com **`adduser`**, o Debian copia **`/etc/skel`** para a home. Depois de rodar o módulo **`tools/`**, o skel inclui (entre o que o Debian já traz, como `.bashrc` quando aplicável):

- **`.bash_aliases`** — atalhos (`ll`, `la`, `l`, `help-runv`).
- **`public_html/index.html`** — página inicial mínima em HTML estático (sem JS, sem CDN), em português.

**Não** há **`README.md`** no skel runv: orientação inicial está no **MOTD** e no comando **`runv-help`**. Quem quiser um README na home pode criar manualmente ou o admin pode usar **`create_runv_user.py --with-readme`** ao provisionar.

**Observação:** no Bash do Debian, o arquivo **`~/.bashrc`** costuma ter (por padrão) um bloco que carrega **`~/.bash_aliases`** se existir. Se o usuário remover esse trecho do `.bashrc`, os aliases deixam de carregar — isso é comportamento padrão do Debian, não do runv.

## Programas globais (apt)

Pacotes listados em **`manifests/apt_packages.txt`** (incluindo ferramentas de terminal e IRC) ficam **instalados no sistema**. O comando global **`chat`** em `/usr/local/bin` é o único nome que o utilizador precisa para IRC na rede da casa; a config é aplicada pelo admin com **`patches/patch_irc.py`**. O usuário **não** precisa de nada no skel para **executá-los**: após o admin rodar `tools.py`, eles passam a existir no `PATH`. Ou seja:

- **Skel** ≠ instalar programas.
- **Skel** = arquivos iniciais na home.
- **apt** = programas para todos.

## Byobu

- Está **disponível** após a instalação dos pacotes.
- **Não** abre sozinho para todos no login.
- Quem quiser pode rodar **`byobu-enable`** na própria conta, quando fizer sentido.

## Como isso ajuda iniciantes

- **MOTD** orienta na hora do login (**`runv-help`**).
- **`runv-help`** e **`runv-links`** explicam o pubnix, permissões e URLs oficiais.
- Administradores com a conta **`pmurad-admin`** podem usar **`runv-status`** para contexto do servidor (outros utilizadores recebem recusa explícita).

Juntos, reduzem fricção para quem nunca usou pubnix ou SSH no dia a dia.
