/*
 * extension/lib/csv.js
 * 依存ライブラリなしの最小 CSV パーサー/シリアライザ。
 * ブラウザ(content script)と Node.js(単体テスト)の両方から読み込めるように
 * UMD 風のエクスポートにしている。
 */
(function (root, factory) {
  var mod = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = mod; // Node.js (unit tests)
  }
  if (root) {
    root.WebAutoLabCSV = mod; // ブラウザ content script
  }
})(typeof window !== "undefined" ? window : (typeof globalThis !== "undefined" ? globalThis : null), function () {
  "use strict";

  var BOM = "﻿";

  /**
   * RFC4180 相当の簡易 CSV パーサー。
   * ダブルクォート囲み・カンマ/改行を含むフィールド・"" エスケープに対応。
   * 1 行目をヘッダとして扱い、各行をオブジェクトの配列で返す。
   * @param {string} text
   * @returns {Array<Object>}
   */
  function parseCSV(text) {
    if (text == null) return [];
    // 先頭 BOM を除去し、CRLF/CR を LF に統一
    var s = String(text).replace(/^﻿/, "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");

    var rows = [];
    var row = [];
    var field = "";
    var inQuotes = false;
    var i = 0;
    var len = s.length;

    function pushField() {
      row.push(field);
      field = "";
    }
    function pushRow() {
      pushField();
      rows.push(row);
      row = [];
    }

    while (i < len) {
      var ch = s[i];

      if (inQuotes) {
        if (ch === '"') {
          if (s[i + 1] === '"') {
            field += '"';
            i += 2;
            continue;
          }
          inQuotes = false;
          i++;
          continue;
        }
        field += ch;
        i++;
        continue;
      }

      if (ch === '"') {
        inQuotes = true;
        i++;
        continue;
      }
      if (ch === ",") {
        pushField();
        i++;
        continue;
      }
      if (ch === "\n") {
        pushRow();
        i++;
        continue;
      }
      field += ch;
      i++;
    }
    // 最終フィールド/行（末尾に改行が無いケース）
    if (field.length > 0 || row.length > 0) {
      pushRow();
    }

    // 完全な空行を除去（末尾の空行など）
    rows = rows.filter(function (r) {
      return !(r.length === 1 && r[0] === "");
    });

    if (rows.length === 0) return [];

    var headers = rows[0].map(function (h) { return String(h).trim(); });
    var out = [];
    for (var r = 1; r < rows.length; r++) {
      var obj = {};
      for (var c = 0; c < headers.length; c++) {
        obj[headers[c]] = rows[r][c] !== undefined ? rows[r][c] : "";
      }
      out.push(obj);
    }
    return out;
  }

  /**
   * 1 フィールドを CSV 用にエスケープする。
   * @param {*} value
   * @returns {string}
   */
  function escapeField(value) {
    var s = value == null ? "" : String(value);
    if (/[",\n]/.test(s)) {
      s = '"' + s.replace(/"/g, '""') + '"';
    }
    return s;
  }

  /**
   * オブジェクト配列を CSV 文字列（BOM なし）に変換する。
   * @param {Array<Object>} rows
   * @param {Array<string>} headers
   * @returns {string}
   */
  function toCSV(rows, headers) {
    var lines = [];
    lines.push(headers.map(escapeField).join(","));
    rows.forEach(function (row) {
      var line = headers.map(function (h) { return escapeField(row[h]); }).join(",");
      lines.push(line);
    });
    return lines.join("\r\n");
  }

  /**
   * Excel 互換のため UTF-8 BOM を付与した CSV 文字列を返す。
   * @param {Array<Object>} rows
   * @param {Array<string>} headers
   * @returns {string}
   */
  function toCSVWithBOM(rows, headers) {
    return BOM + toCSV(rows, headers);
  }

  return {
    BOM: BOM,
    parseCSV: parseCSV,
    toCSV: toCSV,
    toCSVWithBOM: toCSVWithBOM,
    escapeField: escapeField
  };
});
