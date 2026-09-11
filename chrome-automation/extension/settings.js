(function () {
  "use strict";
  const defaults = {
    matches: ["http://localhost:8765/chrome-automation/demo-crm/*", "https://gomamonaka.github.io/webautolab-portfolio/chrome-automation/demo-crm/*"],
    tableSelector: "#customerTable",
    headerSelector: "thead tr",
    rowSelector: "#customerTableBody tr",
    columns: [
      { name: "会社名", index: 1, attribute: "data-company" },
      { name: "担当者", index: 2, attribute: "data-person" },
      { name: "電話", index: 3, attribute: "data-phone" },
      { name: "メール", index: 4, attribute: "data-email" },
      { name: "ステータス", index: 5, attribute: "data-status" },
      { name: "最終更新", index: 6, attribute: "data-updated" }
    ],
    mappings: ["company", "person", "phone", "email", "plan", "note"].map(column => ({ column, selector: "#" + column })),
    toolbar: true
  };
  function pattern(value) {
    const match = /^(https?|\*):\/\/(\*|(?:\*\.)?[a-z0-9.-]+(?::\d+)?)(\/[^\s]*)$/i.exec(value);
    if (!match) throw new Error("URLパターンは http(s)://ホスト/パス の形式で指定してください。");
    return match;
  }
  function matches(url, patterns) {
    const u = new URL(url);
    return patterns.some(value => {
      const [, scheme, host, path] = pattern(value);
      const hostName = host.toLowerCase();
      const actual = host.includes(":") ? u.host : u.hostname;
      const hostOK = hostName === "*" || actual === hostName ||
        (hostName.startsWith("*.") && (actual === hostName.slice(2) || actual.endsWith(hostName.slice(1))));
      const escaped = path.split("*").map(part => part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join(".*");
      return /^https?:$/.test(u.protocol) && (scheme === "*" || u.protocol === scheme + ":") && hostOK && new RegExp("^" + escaped + "$").test(u.pathname + u.search);
    });
  }
  function validate(value) {
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("設定はJSONオブジェクトにしてください。");
    const s = { ...defaults, ...value };
    const text = v => typeof v === "string" && v.trim().length > 0;
    if (!Array.isArray(s.matches) || !s.matches.length) throw new Error("対象URLを1件以上指定してください。");
    s.matches.forEach(pattern);
    [s.tableSelector, s.headerSelector, s.rowSelector].forEach(selector => {
      if (!text(selector)) throw new Error("セレクターを入力してください。");
      if (typeof document !== "undefined") document.querySelector(selector);
    });
    if (!Array.isArray(s.columns) || !s.columns.length || s.columns.some(c => !c || typeof c.name !== "string" || !Number.isInteger(c.index) || c.index < 1 || typeof c.attribute !== "string")) throw new Error("出力列の列番号・列名・属性を確認してください。");
    if (new Set(s.columns.map(c => c.name || "#" + c.index)).size !== s.columns.length) throw new Error("出力列名は重複できません。");
    if (!Array.isArray(s.mappings) || !s.mappings.length || s.mappings.some(m => !m || !text(m.column) || !text(m.selector))) throw new Error("入力対応を1件以上指定してください。");
    s.mappings.forEach(m => { if (typeof document !== "undefined") document.querySelector(m.selector); });
    if (typeof s.toolbar !== "boolean") throw new Error("ツールバー設定が不正です。");
    return Object.fromEntries(Object.keys(defaults).map(key => [key, s[key]]));
  }
  async function read() {
    const stored = await chrome.storage.sync.get("settings");
    if (!stored.settings) {
      await chrome.storage.sync.set({ settings: defaults });
      return structuredClone(defaults);
    }
    try { return validate(stored.settings); } catch (_) { return structuredClone(defaults); }
  }
  globalThis.WebAutoLabSettings = { defaults, read, validate, matches };
})();
