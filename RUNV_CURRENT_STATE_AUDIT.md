# RUNV_CURRENT_STATE_AUDIT.md

Auditoria do **estado actual** do repositório **runv-server**, tratado como linha de base nova.  
**Não** se inferem regressões a partir do histórico Git; apenas o que está presente **agora** no working tree e o que foi **verificado** por leitura de ficheiros e comandos indicados.

**Comandos executados nesta passagem**

| Comando | Resultado |
|---------|-----------|
| `python -m compileall -q scripts terminal site tools email patches` | Exit code **0** (sem erros reportados). |
| `python -m pytest tests/ -q` em `email/` | **11 passed** em ~0,25 s. |
| `python site/build_directory.py --users-json site/example-users.json --dry-run` | Emitiu JSON no stdout (amostra com `alice`); **não verificado** código de saída no shell (PowerShell reportou -1 sem indicar falha lógica do script). |
| `git status -sb` | `## main...origin/main [ahead 1]` e ` D RUNV_SERVER_AUDIT.md`. |

**Não executado:** `bandit`, `ruff`, `mypy`, testes fora de `email/tests/`, workflows CI (não existem em `.github/` na raiz do repo — **ver secção 10**).

---

## 1. Resumo executivo

O snapshot actual contém um conjunto **coerente** de módulos Python (stdlib) e documentação para operar um pubnix Debian: separação **explícita** entre o fluxo SSH `entre` (fila) e o provisionamento via `create_runv_user.py`; geração de dados públicos **filtrada** em `build_directory.py`; fila de pedidos com criação de ficheiro **exclusiva** (`O_EXCL`). Não há `shell=True` / `os.system` / `eval` nos `.py` verificados em `scripts/`, `terminal/`, `site/`, `tools/`, `email/`, `patches/` (além de **comentários** em `tools/tools.py` e `email/lib/mailer.py`). A qualidade de barreira automática global é **fraca** (sem CI na raiz, um único pacote de testes em `email/tests/`). A higiene Git no momento da verificação mostra **um ficheiro de auditoria anterior removido** do índice (`RUNV_SERVER_AUDIT.md`) e ramo **ahead 1** face a `origin/main`. A pasta `.cursor/skills/` existe no disco local e **não** está em `.gitignore` — risco de ruído se alguém fizer `git add .`.

---

## 2. Veredito global

**Coherent enough to continue** (pt: *coerente o suficiente para continuar*).

**Justificativa:** invariantes arquitecturais principais estão **reflectidas no código actual** e a árvore **compila**; há testes **passando** onde foram corridos. Os problemas são sobretudo **manutenibilidade** (script de provisionamento muito grande, política duplicada), **ausência de CI**, e **higiene/ignore** — não contradições estruturais que impeçam evolução incremental segura com disciplina.

---

## 3. O que está claramente correcto neste momento

| Item | Evidência |
|------|-----------|
| `entre_app` declara não criar contas Linux | `terminal/entre_app.py` L5–L6. |
| `entre_app` não invoca `adduser`/`useradd` | Grep sem matches em `terminal/entre_app.py`. |
| Provisionamento de **membros** via `adduser` no script canónico | `scripts/admin/create_runv_user.py` L722–L741 (`run_adduser` com lista de argumentos). |
| Fila: ficheiro novo não substitui existente | `terminal/entre_core.py` `save_request_json` L487–L490 (`O_CREAT\|O_EXCL`). |
| Dataset público mínimo | `site/build_directory.py` L96–L105 (`username`, `since`, `path`, opcional `homepage_mtime`). |
| Caminhos default alinhados entre example e docs de produto | `terminal/config.example.toml` L5–7 (`queue_dir`, `log_file`, `templates_dir`); `build_directory.py` default `--users-json` L31–33 (`/var/lib/runv/users.json`). |
| Compilação Python dos pacotes listados | `compileall` exit 0 (**verificado**). |
| Testes do submódulo email | `pytest` **11 passed** (**verificado**). |

---

## 4. Problemas críticos

**Nenhum bloqueador estrutural** identificado só com base no código e verificações acima: a separação fila vs provisionamento mantém-se; o output público analisado não inclui email nem fingerprint.

**Atenção operacional (não é “bug” de código, mas risco de uso):** `create_runv_user.py` omite refresh da landing se `--landing-document-root` não existir (help L1565–L1568). Operador pode assumir lista actualizada sem verificar path — **documentação** deve deixar isso explícito em runbook (parcialmente já no help).

---

## 5. Achados por severidade

### Alta

- **(Nenhum)** com evidência de falha de segurança directa no código revisto (subprocess inseguro, leak público de campos sensíveis no `build_directory`, overwrite de fila).

### Média

- **M1 — Política de validação duplicada:** `USERNAME_PATTERN`, `EMAIL_PATTERN`, listas de nomes reservados e tipos de chave aparecem em `terminal/entre_core.py` (ex. L33–L74) e em `scripts/admin/create_runv_user.py` (ex. L72–80); comentário em `entre_core.py` L31–L32 admite **não** importar em runtime — risco de **deriva**.

- **M2 — Concentração de complexidade:** `create_runv_user.py` é ficheiro **muito grande** (ordem de ~2000 linhas com docstring inicial extensa) — **difícil** de rever e testar de ponta a ponta sem suite dedicada (**NOT VERIFIED:** contagem exacta de linhas nesta passagem).

- **M3 — Ausência de CI na raiz do projecto:** glob `.github/*` na raiz devolveu **0** ficheiros; workflows encontram-se apenas sob `.cursor/skills/...` (não fazem parte do produto runv). **NOT VERIFIED:** existência de CI noutro remoto ou branch.

### Baixa

- **L1 — `.gitignore` não ignora `.cursor/`:** `.gitignore` actual L1–28 não menciona `.cursor`; se a pasta `skills` for grande, `git add .` pode poluir o índice.

- **L2 — `site/README.md` vs `INSTALL.md` sobre cron:** `INSTALL.md` recomenda exemplo de cron para `build_directory.py` (L87–91); `site/README.md` L19 menciona regeneração via `create_runv_user` / `genlanding` “(sem cron)”. São **modos alternativos**, mas a redacção pode confundir quem procura uma única verdade operacional.

- **L3 — Estado Git:** ` D RUNV_SERVER_AUDIT.md` — ficheiro marcado como removido no índice/working tree no momento do `git status`; resolver antes de push (**snapshot only**).

---

## 6. Segurança

| Tema | Avaliação |
|------|-----------|
| `shell=True` / `os.system` / `eval` em `.py` dos dirs de produto | **Não encontrado** (grep em `scripts`, `terminal`, `site`, `tools`, `email`, `patches`; excepção: linhas de **comentário** em `tools/tools.py` L5, `email/lib/mailer.py` L5). |
| Fila — corrida / overwrite | **Mitigado** por `O_EXCL` (`entre_core.py` L487–L490). |
| Dados sensíveis no JSON da fila | Presentes no **payload** (`entre_core.py` L512–L518: `email`, `public_key_fingerprint`) — **esperado** para revisão admin; **não** copiados para `members.json` pelo `build_directory.py` (L96–L105). |
| `useradd` no terminal | Apenas para criar o utilizador de sistema **`entre`** em `setup_entre.py` L246–254 — **distinto** do provisionamento de membros. |
| Temp files para `ssh-keygen` | `tempfile.mkstemp` + `unlink` em `finally` (`entre_core.py` L218–L242). |
| Config example `entre` | `config.example.toml` L11–14: `admin_email` vazio, remetente `noreply@runv.club` — não expõe segredos; paths padrão sensatos. |
| Análise estática de segurança (bandit) | **NOT VERIFIED** (não executado). |

---

## 7. Operação

- **Ordem em `INSTALL.md` L22–31** (bootstrap → tools → site → build público → email → terminal → operações) é **logicamente consistente** com dependências típicas (Apache antes de publicar; metadados antes de consumo no site).

- **Paths hardcoded** (`/var/lib/runv/...`, `/opt/runv/terminal`, `/etc/runv-email.json`) são **consistentes** entre example TOML, defaults em scripts e `until.md` / `INSTALL.md` — adequados a um deploy Debian único; ambientes multi-tenant exigiriam overrides (**fora do escopo verificado**).

- **Debian / ext4 / quotas:** `starthere.py` docstring L14–18 restringe automatismo de quota a **ext4** — assumido e documentado; **NOT VERIFIED** em VM.

---

## 8. Documentação vs código

| Tópico | Situação |
|--------|----------|
| `entre` não cria membros | **Alinhado** (`entre_app.py` L5–L6; sem `adduser` no `entre_app`). |
| `create_runv_user` canónico | **Alinhado** (docstring L3–L37; `run_adduser` L722+). |
| Membros públicos filtrados | **Alinhado** (`build_directory.py` L96–L105). |
| Cron vs hooks de refresh | **Nuance:** dois discursos (`INSTALL` vs `site/README`); **não** contradição lógica, falta harmonização de linguagem. |
| Refresh landing após user | **Código** exige DocumentRoot existente (`create_runv_user.py` L1565–L1568, fluxo ~L1872+); **operadores** devem ler o help — risco de suposição errada. |

---

## 9. Qualidade de código / manutenibilidade

- **Grande:** `scripts/admin/create_runv_user.py` concentra política, I/O, subprocess, jail, quota, metadata, refresh landing — **serviceable** mas **pesado** para onboarding de novos contribuidores.

- **Duplicação:** regras de validação entre `entre_core.py` e `create_runv_user.py` (**médio** risco de deriva).

- **Testes:** `email/tests/test_mailgun_client.py` cobre cliente Mailgun (**11** testes, **verificado**). **Sem** suite equivalente visível para `entre_core`, `build_directory`, ou locks de `users.json` (**NOT VERIFIED:** outros testes escondidos).

- **“Feio mas seguro” vs “perigoso”:** o código analisado cai sobretudo em **feio mas seguro** no que toca a subprocess e dados públicos; **perigoso** seria `shell=True` com entrada do utilizador — **não observado** nos dirs de produto.

---

## 10. Higiene do repositório (snapshot actual)

- **`git status -sb`:** `main...origin/main [ahead 1]`; ` D RUNV_SERVER_AUDIT.md`.

- **`.github/workflows` na raiz:** **ausente** (0 ficheiros em `z:/Code/runv-server/.github/*`).

- **`.cursor/skills`:** pasta presente sob `.cursor/` no ambiente local (**NOT VERIFIED** tamanho total); **não** listada no `.gitignore`.

- **`.gitignore`:** ignora `terminal/config.toml`, artefactos de news, segredos de email — **razoável** para deploy.

---

## 11. Matriz: manter / corrigir leve / refactor / rebuild

| Área | Classificação | Nota |
|------|---------------|------|
| **terminal/** | **Refactor** (leve) | Extrair política partilhada ou testes de contrato reduziriam deriva. |
| **scripts/admin/** | **Fix lightly** + **Refactor** (faseado) | Manter como fonte de verdade; quebrar em módulos seria refactor **sem urgência** se houver testes primeiro. |
| **site/** | **Manter** | `build_directory.py` claro. |
| **tools/** | **Manter** | Manifest + cópias; alinhado a comentários de segurança. |
| **email/** | **Manter** | Testes existentes passam. |
| **docs/** | **Fix lightly** | Harmonizar cron vs “sem cron”; realçar pré-requisito do DocumentRoot. |
| **patches/** | **Manter** | Auxiliar. |

**Rebuild:** **não** justificado pelo estado actual verificado.

---

## 12. Ficheiros que merecem atenção primeiro

1. `scripts/admin/create_runv_user.py` — tamanho, refresh condicional da landing.  
2. `terminal/entre_core.py` + `scripts/admin/create_runv_user.py` — duplicação de regex/listas.  
3. `site/README.md` + `INSTALL.md` — narrativa cron / refresh.  
4. `.gitignore` — considerar `.cursor/` ou documentar “nunca adicionar skills ao repo runv”.  
5. Estado Git — `RUNV_SERVER_AUDIT.md` removido: decidir commit ou restauração.  
6. `until.md` — bom índice; manter coerente com defaults dos scripts.

---

## 13. Próximas 10 acções (ordenadas)

1. Resolver `git status` (commit ou descartar remoção de `RUNV_SERVER_AUDIT.md`; alinhar `ahead 1`).  
2. Garantir que `.cursor/` não entra no histórico do runv (ignore ou política de equipa).  
3. Adicionar CI mínimo na **raiz**: `python -m compileall -q …` + `pytest email/tests`.  
4. Checklist de release: comparar `USERNAME_PATTERN` / reservados entre `entre_core` e `create_runv_user`.  
5. Runbook: “DocumentRoot tem de existir para refresh automático de `members.json`”.  
6. Unificar parágrafo sobre cron em `site/README.md` / `INSTALL.md`.  
7. (Opcional) `bandit -r scripts terminal site tools email patches` e registar resultados.  
8. Smoke: `python3 site/build_directory.py --dry-run` com cópia de `users.json` de teste.  
9. Smoke: `python3 -m py_compile terminal/entre_app.py terminal/entre_core.py`.  
10. Documentar ausência de `.github/workflows` no projecto ou adicionar um workflow simples.

---

## 14. Smoke tests manuais seguros (próximos)

- `python -m compileall -q scripts terminal site tools email patches`  
- `cd email && python -m pytest tests/ -q`  
- `python site/build_directory.py --users-json site/example-users.json --dry-run`  
- `python scripts/admin/create_runv_user.py --help` (rever flags de landing/quota)  
- `python terminal/setup_entre.py --help` (em máquina de desenvolvimento, sem sudo se possível)

---

## 15. Questões abertas / incertezas

- **Conteúdo do commit “ahead 1”** local face a `origin/main` — **NOT VERIFIED** (`git show` não executado).  
- **Bandit / Ruff / mypy** — **NOT VERIFIED**.  
- **Páginas HTML em `public/`** cumprem regra de rodapé em 100% dos ficheiros — **NOT VERIFIED** (não revisto ficheiro a ficheiro).  
- **Configuração real em produção** (PAM, Mailgun, Apache) — **NOT VERIFIED**.

---

## 16. Apêndice de evidências

| ID | Afirmação | Evidência |
|----|-----------|-----------|
| E1 | `entre` não provisiona membro no app | `terminal/entre_app.py` L5–L6 |
| E2 | Sem adduser no entre_app | grep vazio em `terminal/entre_app.py` |
| E3 | Fila atómica | `terminal/entre_core.py` L487–L490 |
| E4 | Payload fila com PII técnico | `terminal/entre_core.py` L512–L518 |
| E5 | Público mínimo | `site/build_directory.py` L96–L105 |
| E6 | adduser para membros | `scripts/admin/create_runv_user.py` L729 |
| E7 | useradd só `entre` | `terminal/setup_entre.py` L246–254 |
| E8 | Default users.json | `site/build_directory.py` L31–33 |
| E9 | Defaults fila/log TOML | `terminal/config.example.toml` L5–7 |
| E10 | Landing default path | `scripts/admin/create_runv_user.py` L1562–L1568 |
| E11 | compileall OK | comando executado, exit 0 |
| E12 | pytest email | 11 passed |
| E13 | Sem shell=True (prod dirs) | grep nos seis caminhos de produto |
| E14 | git status snapshot | `main...origin/main [ahead 1]`, ` D RUNV_SERVER_AUDIT.md` |
| E15 | Sem workflows na raiz | glob `z:/Code/runv-server/.github/*` → 0 |
| E16 | .gitignore actual | `.gitignore` L1–28 |

---

*Fim do relatório — estado actual apenas, sem inferência de histórico.*
