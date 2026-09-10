/*
 * extension/content.js
 * demo-crm (顧客一覧 / 新規顧客登録) にフローティングツールバーを注入し、
 * 「一覧をCSV保存」「CSVから自動入力」を提供する。
 * CSV の読み書きは lib/csv.js の純粋関数 (WebAutoLabCSV) を利用する。
 */
(function () {
  "use strict";

  var CSV_HEADERS = ["company", "person", "phone", "email", "plan", "note"];
  var HEADER_LABEL = {
    company: "会社名",
    person: "担当者",
    phone: "電話",
    email: "メール",
    plan: "プラン",
    note: "備考"
  };

  var isIndexPage = !!document.getElementById("customerTable");
  var isNewPage = !!document.getElementById("newCustomerForm");

  // ------------------------------------------------------------------
  // ツールバー DOM 構築
  // ------------------------------------------------------------------
  function buildToolbar() {
    var box = document.createElement("div");
    box.id = "wal-toolbar";
    box.innerHTML =
      '<span class="wal-close" id="wal-close" title="閉じる">×</span>' +
      '<div class="wal-title"><span class="wal-dot"></span>WebAutoLab 1クリック自動化</div>';

    if (isIndexPage) {
      var exportBtn = document.createElement("button");
      exportBtn.className = "wal-btn";
      exportBtn.id = "wal-export-btn";
      exportBtn.textContent = "一覧をCSV保存";
      box.appendChild(exportBtn);
      exportBtn.addEventListener("click", handleExportCSV);
    }

    if (isNewPage) {
      var importBtn = document.createElement("button");
      importBtn.className = "wal-btn";
      importBtn.id = "wal-import-btn";
      importBtn.textContent = "CSVから自動入力";
      box.appendChild(importBtn);
      importBtn.addEventListener("click", function () { fileInput.click(); });

      var nextBtn = document.createElement("button");
      nextBtn.className = "wal-btn wal-secondary";
      nextBtn.id = "wal-next-btn";
      nextBtn.textContent = "次の行";
      nextBtn.disabled = true;
      box.appendChild(nextBtn);
      nextBtn.addEventListener("click", handleNextRow);

      var allBtn = document.createElement("button");
      allBtn.className = "wal-btn wal-secondary";
      allBtn.id = "wal-all-btn";
      allBtn.textContent = "全件登録";
      allBtn.disabled = true;
      box.appendChild(allBtn);
      allBtn.addEventListener("click", handleRegisterAll);

      var rowInfo = document.createElement("div");
      rowInfo.className = "wal-row-info";
      rowInfo.id = "wal-row-info";
      rowInfo.textContent = "CSV未読込";
      box.appendChild(rowInfo);

      var fileInput = document.createElement("input");
      fileInput.type = "file";
      fileInput.accept = ".csv,text/csv";
      fileInput.style.display = "none";
      fileInput.id = "wal-file-input";
      box.appendChild(fileInput);
      fileInput.addEventListener("change", handleFileSelected);
    }

    var status = document.createElement("div");
    status.className = "wal-status";
    status.id = "wal-status";
    status.textContent = isIndexPage
      ? "顧客一覧のCSVエクスポートができます。"
      : "CSVファイルを選択すると入力欄を自動入力します。";
    box.appendChild(status);

    document.body.appendChild(box);

    document.getElementById("wal-close").addEventListener("click", function () {
      box.style.display = "none";
    });
  }

  function log(msg) {
    var el = document.getElementById("wal-status");
    if (el) el.textContent = msg;
  }

  // ------------------------------------------------------------------
  // 顧客一覧: CSV エクスポート
  // ------------------------------------------------------------------
  function scrapeTableRows() {
    var trs = document.querySelectorAll("#customerTableBody tr");
    var rows = [];
    trs.forEach(function (tr) {
      rows.push({
        company: tr.getAttribute("data-company") || "",
        person: tr.getAttribute("data-person") || "",
        phone: tr.getAttribute("data-phone") || "",
        email: tr.getAttribute("data-email") || "",
        plan: "",
        note: tr.getAttribute("data-status") || ""
      });
    });
    return rows;
  }

  function downloadTextFile(filename, text, mime) {
    var blob = new Blob([text], { type: mime || "text/csv;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
  }

  function handleExportCSV() {
    // 一覧向けのヘッダ（日本語表示に合わせる）
    var jaHeaders = ["会社名", "担当者", "電話", "メール", "ステータス", "最終更新"];
    var trs = document.querySelectorAll("#customerTableBody tr");
    var rows = [];
    trs.forEach(function (tr) {
      rows.push({
        "会社名": tr.getAttribute("data-company") || "",
        "担当者": tr.getAttribute("data-person") || "",
        "電話": tr.getAttribute("data-phone") || "",
        "メール": tr.getAttribute("data-email") || "",
        "ステータス": tr.getAttribute("data-status") || "",
        "最終更新": tr.getAttribute("data-updated") || ""
      });
    });
    var csv = window.WebAutoLabCSV.toCSVWithBOM(rows, jaHeaders);
    downloadTextFile("customers_export.csv", csv);
    log(rows.length + " 件を customers_export.csv として保存しました。");
  }

  // ------------------------------------------------------------------
  // 新規登録: CSV から自動入力
  // ------------------------------------------------------------------
  var importedRows = [];
  var currentRowIndex = -1;

  function handleFileSelected(ev) {
    var file = ev.target.files && ev.target.files[0];
    if (!file) return;
    var reader = new FileReader();
    reader.onload = function () {
      var text = reader.result;
      importedRows = window.WebAutoLabCSV.parseCSV(text);
      currentRowIndex = -1;
      if (importedRows.length === 0) {
        log("CSVを読み込みましたが、データ行がありませんでした。");
        return;
      }
      document.getElementById("wal-next-btn").disabled = false;
      document.getElementById("wal-all-btn").disabled = false;
      log(importedRows.length + " 件のCSVを読み込みました。「次の行」または「全件登録」を押してください。");
      handleNextRow();
    };
    reader.readAsText(file, "UTF-8");
    ev.target.value = ""; // 同じファイルを選び直せるようにする
  }

  function fillFormFromRow(row) {
    CSV_HEADERS.forEach(function (key) {
      var el = document.getElementById(key);
      if (!el || row[key] === undefined) return;
      if (el.tagName === "SELECT") {
        el.value = row[key];
      } else {
        el.value = row[key];
      }
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    });
  }

  function handleNextRow() {
    if (importedRows.length === 0) return;
    currentRowIndex++;
    if (currentRowIndex >= importedRows.length) {
      currentRowIndex = importedRows.length - 1;
      log("最後の行です。");
      return;
    }
    fillFormFromRow(importedRows[currentRowIndex]);
    var info = document.getElementById("wal-row-info");
    info.textContent = (currentRowIndex + 1) + " / " + importedRows.length + " 行目: " +
      (importedRows[currentRowIndex].company || "");
  }

  function waitForToast(timeoutMs) {
    return new Promise(function (resolve) {
      var toast = document.getElementById("toast");
      if (!toast) { resolve(false); return; }
      var done = false;
      var observer = new MutationObserver(function () {
        if (toast.classList.contains("show") && !done) {
          done = true;
          observer.disconnect();
          resolve(true);
        }
      });
      observer.observe(toast, { attributes: true, attributeFilter: ["class"] });
      setTimeout(function () {
        if (!done) {
          done = true;
          observer.disconnect();
          resolve(false);
        }
      }, timeoutMs || 3000);
    });
  }

  function sleep(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
  }

  function handleRegisterAll() {
    if (importedRows.length === 0) return;
    var allBtn = document.getElementById("wal-all-btn");
    var nextBtn = document.getElementById("wal-next-btn");
    allBtn.disabled = true;
    nextBtn.disabled = true;

    var startIndex = currentRowIndex < 0 ? 0 : currentRowIndex;
    var submitBtn = document.getElementById("submitBtn");

    (async function run() {
      for (var i = startIndex; i < importedRows.length; i++) {
        currentRowIndex = i;
        fillFormFromRow(importedRows[i]);
        var info = document.getElementById("wal-row-info");
        info.textContent = "登録中... " + (i + 1) + " / " + importedRows.length + ": " + (importedRows[i].company || "");
        log("登録中: " + (importedRows[i].company || "(" + (i + 1) + "行目)"));

        await sleep(150); // フォーム反映を待つ
        submitBtn.click();
        await waitForToast(3000);
        await sleep(400); // トーストを目視できる程度の間隔
      }
      log("全 " + importedRows.length + " 件の登録が完了しました。");
      document.getElementById("wal-row-info").textContent = "完了: " + importedRows.length + " 件登録";
      allBtn.disabled = false;
      nextBtn.disabled = false;
    })();
  }

  // ------------------------------------------------------------------
  // popup からのメッセージ対応（同じ操作をpopupのボタンからも実行できるように）
  // ------------------------------------------------------------------
  if (chrome && chrome.runtime && chrome.runtime.onMessage) {
    chrome.runtime.onMessage.addListener(function (msg, sender, sendResponse) {
      if (!msg) return;
      if (msg.action === "wal-export-csv" && isIndexPage) {
        handleExportCSV();
        sendResponse({ ok: true });
      } else if (msg.action === "wal-open-import" && isNewPage) {
        var input = document.getElementById("wal-file-input");
        if (input) input.click();
        sendResponse({ ok: true });
      } else if (msg.action === "wal-ping") {
        sendResponse({ ok: true, page: isIndexPage ? "index" : (isNewPage ? "new" : "unknown") });
      }
    });
  }

  // ------------------------------------------------------------------
  if (isIndexPage || isNewPage) {
    buildToolbar();
  }
})();
