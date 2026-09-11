(async function () {
  "use strict";
  const S = WebAutoLabSettings;
  const $ = id => document.getElementById(id);
  const status = message => { $("status").textContent = message; };
  function addRow(kind, value) {
    const tr = document.createElement("tr");
    const keys = kind === "columns" ? ["name", "index", "attribute"] : ["column", "selector"];
    keys.forEach(key => {
      const td = tr.insertCell();
      const input = document.createElement("input");
      input.value = value[key] ?? "";
      input.dataset.key = key;
      input.setAttribute("aria-label", ({ name: "CSV列名", index: "列番号", attribute: "行の属性", column: "CSV列名", selector: "入力CSSセレクター" })[key]);
      if (key === "index") { input.type = "number"; input.min = "1"; input.required = true; }
      td.appendChild(input);
    });
    const remove = document.createElement("button");
    remove.type = "button"; remove.textContent = "削除";
    remove.onclick = () => tr.remove();
    tr.insertCell().appendChild(remove);
    $(kind).appendChild(tr);
  }
  function render(s) {
    $("matches").value = s.matches.join("\n");
    ["tableSelector", "headerSelector", "rowSelector"].forEach(key => { $(key).value = s[key]; });
    $("toolbar").checked = s.toolbar;
    ["columns", "mappings"].forEach(kind => { $(kind).replaceChildren(); s[kind].forEach(v => addRow(kind, v)); });
  }
  function collect() {
    const s = { matches: $("matches").value.split(/\r?\n/).map(x => x.trim()).filter(Boolean), toolbar: $("toolbar").checked };
    ["tableSelector", "headerSelector", "rowSelector"].forEach(key => { s[key] = $(key).value.trim(); });
    ["columns", "mappings"].forEach(kind => {
      s[kind] = Array.from($(kind).rows, row => Object.fromEntries(Array.from(row.querySelectorAll("input"), input => [input.dataset.key, input.dataset.key === "index" ? Number(input.value) : input.value.trim()])));
    });
    return S.validate(s);
  }
  $("addColumn").onclick = () => addRow("columns", { index: $("columns").rows.length + 1 });
  $("addMapping").onclick = () => addRow("mappings", {});
  $("settingsForm").onsubmit = async event => {
    event.preventDefault();
    try { await chrome.storage.sync.set({ settings: collect() }); status("保存しました。対象ページを再読み込みしてください。"); }
    catch (e) { status("保存できませんでした：" + e.message); }
  };
  $("reset").onclick = async () => {
    try { await chrome.storage.sync.set({ settings: S.defaults }); render(S.defaults); status("初期設定にリセットしました。対象ページを再読み込みしてください。"); }
    catch (e) { status("リセットできませんでした：" + e.message); }
  };
  $("export").onclick = () => {
    try {
      const url = URL.createObjectURL(new Blob([JSON.stringify(collect(), null, 2)], { type: "application/json" }));
      const a = document.createElement("a"); a.href = url; a.download = "webautolab-settings.json"; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
      status("編集欄の設定を書き出しました。");
    } catch (e) { status("書き出しできませんでした：" + e.message); }
  };
  $("import").onclick = () => $("jsonFile").click();
  $("jsonFile").onchange = async event => {
    const file = event.target.files[0]; if (!file) return;
    try { render(S.validate(JSON.parse(await file.text()))); status("読み込みました。「設定を保存」で確定してください。"); }
    catch (e) { status("読み込みできませんでした：" + e.message); }
    event.target.value = "";
  };
  try { render(await S.read()); } catch (e) { render(S.defaults); status("設定を取得できませんでした：" + e.message); }
})();
