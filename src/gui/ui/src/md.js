/**
 * Minimal, dependency-free Markdown renderer for chat messages.
 *
 * Security: input is HTML-escaped BEFORE any formatting is applied, so raw
 * HTML in model output cannot inject nodes. Only a safe subset is supported:
 * fenced/inline code, bold, italic, headings, links, and unordered lists.
 */

/** @param {string} s */
function escapeHtml(s) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/**
 * Render a limited subset of Markdown to safe HTML.
 * @param {string} text
 * @returns {string}
 */
export function renderMarkdown(text) {
  if (!text) return "";
  const src = escapeHtml(String(text));

  // Fenced code blocks: ```lang\n ... ```
  const codeBlocks = [];
  let out = src.replace(/```([\w+-]*)\n?([\s\S]*?)```/g, (_m, lang, code) => {
    const idx = codeBlocks.length;
    const cls = lang ? ` data-lang="${lang}"` : "";
    codeBlocks.push(`<pre class="md-pre"><code${cls}>${code.replace(/\n$/, "")}</code></pre>`);
    return `\u0000CB${idx}\u0000`;
  });

  const lines = out.split("\n");
  const html = [];
  let inList = false;
  const closeList = () => { if (inList) { html.push("</ul>"); inList = false; } };

  for (const line of lines) {
    if (/^\u0000CB\d+\u0000$/.test(line.trim())) {
      closeList();
      html.push(line.trim());
      continue;
    }
    const h = line.match(/^(#{1,4})\s+(.*)$/);
    if (h) {
      closeList();
      const level = h[1].length + 2; // h3..h6
      html.push(`<h${level}>${inline(h[2])}</h${level}>`);
      continue;
    }
    const li = line.match(/^\s*[-*]\s+(.*)$/);
    if (li) {
      if (!inList) { html.push("<ul>"); inList = true; }
      html.push(`<li>${inline(li[1])}</li>`);
      continue;
    }
    if (!line.trim()) { closeList(); html.push("<br>"); continue; }
    closeList();
    html.push(`<p>${inline(line)}</p>`);
  }
  closeList();

  let result = html.join("");
  result = result.replace(/\u0000CB(\d+)\u0000/g, (_m, i) => codeBlocks[Number(i)] || "");
  return result;
}

/** Inline formatting: code, bold, italic, links. @param {string} s */
function inline(s) {
  return s
    .replace(/`([^`]+)`/g, '<code class="md-code">$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
}
