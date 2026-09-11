/*
 * extension/popup.js
 * アクティブタブが demo-crm の対応ページかを確認し、
 * 対応するアクションを content script にメッセージで依頼する。
 */
(async function () {
  "use strict";

  var statusEl = document.getElementById("popupStatus");
  var btnExport = document.getElementById("btnExport");
  var btnImport = document.getElementById("btnImport");

  function setStatus(text) {
    statusEl.textContent = text;
  }

  document.getElementById("btnSettings").addEventListener("click", function () { chrome.runtime.openOptionsPage(); });
  var settings;
  try { settings = await WebAutoLabSettings.read(); }
  catch (_) { settings = structuredClone(WebAutoLabSettings.defaults); }

  chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
    var tab = tabs && tabs[0];
    if (!tab) {
      setStatus("タブが見つかりません。");
      return;
    }

    if (!tab.url || !WebAutoLabSettings.matches(tab.url, settings.matches)) {
      setStatus("設定した対象URLのページで開いてください。");
      return;
    }
    chrome.tabs.sendMessage(tab.id, { action: "wal-ping" }, function (resp) {
      if (chrome.runtime.lastError || !resp) {
        setStatus("対象ページを再読み込みしてください。");
        return;
      }
      if (resp.page === "index") {
        setStatus("顧客一覧ページを検出しました。");
        btnExport.disabled = false;
      } else if (resp.page === "new") {
        setStatus("新規登録ページを検出しました。");
        btnImport.disabled = false;
      } else {
        setStatus("このページでは利用できません。");
      }
    });
  });

  btnExport.addEventListener("click", function () {
    chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
      var tab = tabs && tabs[0];
      if (!tab) return;
      chrome.tabs.sendMessage(tab.id, { action: "wal-export-csv" }, function (resp) {
        setStatus(chrome.runtime.lastError ? "通信できません。対象ページを再読み込みしてください。" : (!resp || !resp.ok ? (resp && resp.error || "CSV保存に失敗しました。") : "CSVをダウンロードしました。"));
      });
    });
  });

  btnImport.addEventListener("click", function () {
    chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
      var tab = tabs && tabs[0];
      if (!tab) return;
      chrome.tabs.sendMessage(tab.id, { action: "wal-open-import" }, function (resp) {
        if (chrome.runtime.lastError || !resp || !resp.ok) { setStatus("通信できません。対象ページを再読み込みしてください。"); return; }
        window.close();
      });
    });
  });
})();
