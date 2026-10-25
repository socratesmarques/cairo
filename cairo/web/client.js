"use strict";
(function(root) {
  function errorMessage(body, status) {
    if (typeof body?.detail === "string") return body.detail;
    if (typeof body?.error === "string") return body.error;
    if (typeof body?.error?.message === "string") return body.error.message;
    return `Não foi possível concluir a operação (${status}).`;
  }
  async function fetchJSON(path, options = {}, fetcher = globalThis.fetch) {
    const {timeoutMs = 20000, ...request} = options;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetcher(path, {...request, signal: controller.signal,
        headers: {"Content-Type":"application/json", "X-Cairo-Client":"web", ...request.headers}});
      let body;
      try { body = await response.json(); }
      catch (_) { throw new Error("O servidor retornou uma resposta inválida. Confira a conexão e reinicie o Cairo se acabou de atualizar."); }
      if (!response.ok) {
        const error = new Error(errorMessage(body, response.status));
        error.status = response.status;
        throw error;
      }
      return body;
    } catch (error) {
      if (error.name === "AbortError") throw new Error("A conexão excedeu o tempo limite. Confira o histórico antes de reenviar o pedido.");
      if (error instanceof TypeError) throw new Error("Não foi possível conectar ao Cairo. Confira se ele está aberto.");
      throw error;
    } finally { clearTimeout(timer); }
  }
  function shortcuts(value) {
    if (!Array.isArray(value)) return [];
    const seen = new Set();
    return value.filter(item => item && typeof item.name === "string" && typeof item.prompt === "string" && item.name.trim() && item.prompt.trim() && item.name.length <= 40 && item.prompt.length <= 16000)
      .filter(item => { if (seen.has(item.prompt.trim())) return false; seen.add(item.prompt.trim()); return true; })
      .slice(0, 12).map(item => ({name:item.name.trim(), prompt:item.prompt.trim()}));
  }
  const api = {errorMessage, fetchJSON, shortcuts};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.CairoClient = api;
})(globalThis);
