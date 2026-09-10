/*
 * extension/popup.js
 * アクティブタブが demo-crm の対応ページかを確認し、
 * 対応するアクションを content script にメッセージで依頼する。
 */
(function () {
  "use strict";

  var statusEl = document.getElementById("popupStatus");
  var btnExport = document.getElementById("btnExport");
  var btnImport = document.getElementById("btnImport");

  function setStatus(text) {
    statusEl.textContent = text;
  }

  chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
    var tab = tabs && tabs[0];
    if (!tab) {
      setStatus("タブが見つかりません。");
      return;
    }

    chrome.tabs.sendMessage(tab.id, { action: "wal-ping" }, function (resp) {
      if (chrome.runtime.lastError || !resp) {
        setStatus("demo-crm のページで開いてください。");
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
      chrome.tabs.sendMessage(tab.id, { action: "wal-export-csv" }, function () {
        setStatus("CSVをダウンロードしました。");
      });
    });
  });

  btnImport.addEventListener("click", function () {
    chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
      var tab = tabs && tabs[0];
      if (!tab) return;
      chrome.tabs.sendMessage(tab.id, { action: "wal-open-import" }, function () {
        window.close();
      });
    });
  });
})();
