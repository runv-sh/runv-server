/**
 * Carrega notícias de data/news.json (gerado por site/news/publish_news.py).
 */
(function () {
  async function run() {
    const root = document.getElementById("news-feed");
    const empty = document.getElementById("news-empty");
    if (!root) return;

    try {
      const r = await fetch("data/news.json", { cache: "no-store" });
      if (!r.ok) throw new Error("news.json indisponível");
      const data = await r.json();
      const articles = Array.isArray(data.articles) ? data.articles : [];
      if (articles.length === 0) {
        if (empty) {
          empty.hidden = false;
          empty.textContent =
            "Ainda não há entradas publicadas. Quando houver, aparecem aqui em destaque.";
        }
        return;
      }
      if (empty) empty.hidden = true;

      const frag = document.createDocumentFragment();
      for (const a of articles) {
        const art = document.createElement("article");
        art.className = "news-card";
        if (a.id) art.id = "post-" + a.id;

        const head = document.createElement("header");
        head.className = "news-card__head";

        const time = document.createElement("time");
        time.className = "news-card__date";
        if (a.w3c_published) time.dateTime = a.w3c_published;
        time.textContent = a.date || "";

        const h2 = document.createElement("h2");
        h2.className = "news-card__title";
        h2.textContent = a.title || "";

        head.appendChild(time);
        head.appendChild(h2);

        const body = document.createElement("div");
        body.className = "news-card__body prose-news";
        body.innerHTML = a.body_html || "";

        art.appendChild(head);
        art.appendChild(body);
        frag.appendChild(art);
      }
      root.appendChild(frag);
    } catch (_e) {
      if (empty) {
        empty.hidden = false;
        empty.textContent =
          "Não foi possível carregar a lista (ficheiro data/news.json ausente ou indisponível). Use o feed RSS ou tente mais tarde.";
      }
    }
  }

  run();
})();
