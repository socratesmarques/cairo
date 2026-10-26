"use strict";
// Model content enters through text nodes; HTML and executable URLs stay inert.
(function(root) {
  function element(tag, text) {
    const result = document.createElement(tag);
    if (text !== undefined) result.textContent = text;
    return result;
  }
  function inline(parent, text) {
    const pattern = /(`[^`\n]+`|\*\*[^*\n]+\*\*|\[[^\]\n]+\]\(https?:\/\/[^\s)]+\))/g;
    let cursor = 0;
    for (const match of text.matchAll(pattern)) {
      parent.append(document.createTextNode(text.slice(cursor, match.index)));
      const token = match[0];
      if (token.startsWith("`")) parent.append(element("code", token.slice(1, -1)));
      else if (token.startsWith("**")) parent.append(element("strong", token.slice(2, -2)));
      else {
        const split = token.indexOf("](");
        const link = element("a", token.slice(1, split));
        link.href = token.slice(split + 2, -1); link.target = "_blank"; link.rel = "noopener noreferrer";
        parent.append(link);
      }
      cursor = match.index + token.length;
    }
    parent.append(document.createTextNode(text.slice(cursor)));
  }
  function render(text) {
    const fragment = document.createDocumentFragment();
    const lines = String(text).replace(/\r\n?/g, "\n").split("\n");
    for (let i = 0; i < lines.length;) {
      const line = lines[i];
      if (!line.trim()) { i++; continue; }
      if (/^\s*```/.test(line)) {
        const block = element("div"); block.className = "code-block";
        const bar = element("div"); bar.className = "code-bar";
        bar.append(element("span", line.trim().slice(3).trim().slice(0, 40) || "Código"));
        const copy = element("button", "Copiar código"); copy.type = "button";
        const source = []; i++;
        while (i < lines.length && !/^\s*```/.test(lines[i])) source.push(lines[i++]);
        if (i < lines.length) i++;
        const value = source.join("\n");
        copy.addEventListener("click", async () => {
          try { await navigator.clipboard.writeText(value); copy.textContent = "Copiado"; }
          catch (_) { copy.textContent = "Selecione e copie"; }
        });
        bar.append(copy); const pre = element("pre"); pre.append(element("code", value));
        block.append(bar, pre); fragment.append(block); continue;
      }
      const heading = /^(#{1,4})\s+(.+)$/.exec(line);
      if (heading) {
        const title = element("h" + Math.min(heading[1].length + 1, 6));
        inline(title, heading[2]); fragment.append(title); i++; continue;
      }
      if (/^\s*([-*_])(?:\s*\1){2,}\s*$/.test(line)) { fragment.append(element("hr")); i++; continue; }
      if (line.includes("|") && i + 1 < lines.length && /^\s*\|?\s*:?-{3,}/.test(lines[i + 1])) {
        const cells = (row) => row.trim().replace(/^\||\|$/g, "").split("|").map(v => v.trim());
        const wrapper = element("div"); wrapper.className = "table-scroll";
        const table = element("table"); const head = element("thead"); const tr = element("tr");
        for (const value of cells(line)) { const th = element("th"); inline(th, value); tr.append(th); }
        head.append(tr); table.append(head); i += 2; const body = element("tbody");
        while (i < lines.length && lines[i].includes("|") && lines[i].trim()) {
          const row = element("tr");
          for (const value of cells(lines[i++])) { const td = element("td"); inline(td, value); row.append(td); }
          body.append(row);
        }
        table.append(body); wrapper.append(table); fragment.append(wrapper); continue;
      }
      const item = /^\s*(?:([-+*])|\d+[.)])\s+(.+)$/.exec(line);
      if (item) {
        const list = element(item[1] ? "ul" : "ol");
        while (i < lines.length) {
          const next = /^\s*(?:([-+*])|\d+[.)])\s+(.+)$/.exec(lines[i]);
          if (!next || Boolean(next[1]) !== Boolean(item[1])) break;
          const li = element("li"); inline(li, next[2]); list.append(li); i++;
        }
        fragment.append(list); continue;
      }
      const paragraph = element(line.startsWith("> ") ? "blockquote" : "p");
      inline(paragraph, line.startsWith("> ") ? line.slice(2) : line);
      fragment.append(paragraph); i++;
    }
    return fragment;
  }
  root.CairoMarkdown = {render};
})(globalThis);
