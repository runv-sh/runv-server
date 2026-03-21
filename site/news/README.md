# Publicar notícias (`publish_news.py`)

1. Crie um ficheiro **`.md`** nesta pasta (`site/news/`) com **qualquer nome** (excepto `_*`, que são ignorados). O ficheiro **`README.md`** nunca é publicado.
2. **Linha 1:** título da notícia.  
3. **Linhas seguintes:** corpo em Markdown leve:
   - `**negrito**`
   - `*itálico*` ou `_itálico_`
   - `++sublinhado++`
4. No servidor (ou no clone), a partir da raiz do repositório:

   ```bash
   python3 site/news/publish_news.py --verbose
   ```

5. O script:
   - acrescenta a notícia a `site/public/news/data/news.json` (data **DD-MM-AAAA**, fuso `America/Sao_Paulo` quando o pacote **tzdata** está disponível; caso contrário usa **UTC−3** fixo);
   - regera `site/public/news/feed.rss`;
   - actualiza `lastmod` da URL `/news/` em `site/public/sitemap.xml`;
   - **apaga** o `.md` processado.

**Git:** `news.json` está em `.gitignore` para evitar conflitos em `git pull` no servidor. No repositório há só `site/public/news/data/news.json.example` (lista vazia). Em produção, após o primeiro `publish_news.py`, copie o `DocumentRoot` com `genlanding.py` ou mantenha `news.json` só no servidor.

**Windows:** instale `tzdata` (`pip install tzdata`) para o fuso `America/Sao_Paulo` exacto.

**Modelo:** veja `_exemplo.md` (não é publicado).
