/**
 * gas-invoice — 請求書の自動作成ツール（Google Apps Script）
 *
 * スプレッドシート「請求データ」の内容をもとに、
 *   1. 「請求書テンプレート」シートへ転記
 *   2. PDF 化して Google Drive へ保存
 *   3. PDF を添付した Gmail の下書きを作成
 * までを一括で行います。
 *
 * ウェブオートラボ ポートフォリオ用デモ
 */

// ==============================
// 設定（ここを自社の内容に書き換えて使います）
// ==============================
const CONFIG = {
  // シート名
  DATA_SHEET_NAME: '請求データ',
  TEMPLATE_SHEET_NAME: '請求書テンプレート',
  LOG_SHEET_NAME: '処理ログ',

  // PDF の保存先フォルダ名（マイドライブ直下に自動作成されます）
  PDF_FOLDER_NAME: '請求書PDF',

  // 消費税率（10%）
  TAX_RATE: 0.10,

  // 請求書番号の接頭辞（例: INV-202611-001）
  INVOICE_NUMBER_PREFIX: 'INV',

  // 発行者情報
  ISSUER: {
    NAME: 'ウェブオートラボ',
    ZIP: '〒000-0000',
    ADDRESS: '（発行者の住所を入力してください）',
    EMAIL: 'invoice@example.com',
    BANK_INFO: '（振込先：○○銀行 ○○支店 普通 0000000）',
  },

  // メールの件名・本文
  // {customerName} {contactName} {invoiceNumber} {total} {dueDate} {issuerName} が使えます
  MAIL_SUBJECT: '請求書送付のご案内（{invoiceNumber}）',
  MAIL_BODY: [
    '{customerName} {contactName} 様',
    '',
    'いつもお世話になっております。{issuerName}です。',
    '請求書（{invoiceNumber}）を PDF で添付いたします。',
    '',
    '請求金額：{total} 円（税込）',
    'お支払期限：{dueDate}',
    '',
    'ご不明点がございましたら、本メールへご返信ください。',
    'よろしくお願いいたします。',
  ].join('\n'),

  // テンプレートシートのセル配置（README のレイアウト表と対応しています）
  CELLS: {
    CUSTOMER_NAME: 'B2',   // 請求先会社名
    INVOICE_NUMBER: 'G2',  // 請求書番号
    ISSUE_DATE: 'G3',      // 発行日（請求日）
    DUE_DATE: 'G4',        // 支払期限
    ITEM_START_ROW: 7,     // 明細の開始行（6行目は見出し）
    ITEM_MAX_ROWS: 12,     // 明細の最大行数
    COL_ITEM_NAME: 'B',    // 品目
    COL_QTY: 'D',          // 数量
    COL_UNIT: 'E',         // 単位
    COL_PRICE: 'F',        // 単価
    COL_AMOUNT: 'G',       // 金額
    SUBTOTAL: 'G20',       // 小計
    TAX: 'G21',            // 消費税
    TOTAL: 'G22',          // 合計金額
    ISSUER_INFO: 'B20',    // 発行者情報
    BANK_INFO: 'B24',      // 振込先
  },
};

// 「請求データ」シートの列名（1行目のヘッダーと一致させる）
const COLUMNS = {
  CUSTOMER: '請求先会社名',
  CONTACT: '担当者名',
  EMAIL: 'メールアドレス',
  ISSUE_DATE: '請求日',
  DUE_DATE: '支払期限',
  ITEM_NAME: '品目',
  QTY: '数量',
  UNIT: '単位',
  PRICE: '単価',
  INVOICE_NUMBER: '請求書番号',
};

// ==============================
// メニュー
// ==============================
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('請求書ツール')
    .addItem('未処理の請求書を作成（PDF＋下書き）', 'createInvoices')
    .addItem('使い方', 'showHelp')
    .addToUi();
}

function showHelp() {
  SpreadsheetApp.getUi().alert(
    '「請求データ」シートに請求先と明細を入力し、' +
    'メニューから「未処理の請求書を作成」を実行してください。\n' +
    '請求書番号が空の行が処理対象です。作成された PDF は Drive の「' +
    CONFIG.PDF_FOLDER_NAME + '」フォルダに保存され、Gmail に下書きが作成されます。'
  );
}

// ==============================
// メイン処理
// ==============================
function createInvoices() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const dataSheet = ss.getSheetByName(CONFIG.DATA_SHEET_NAME);
  if (!dataSheet) {
    throw new Error('シート「' + CONFIG.DATA_SHEET_NAME + '」が見つかりません。');
  }
  if (!ss.getSheetByName(CONFIG.TEMPLATE_SHEET_NAME)) {
    throw new Error('シート「' + CONFIG.TEMPLATE_SHEET_NAME + '」が見つかりません。');
  }

  const rows = readInvoiceRows_(dataSheet);
  const groups = groupRows_(rows);
  const sequence = { value: countExistingInvoiceNumbers_(dataSheet) };

  let created = 0;
  let skipped = 0;
  let failed = 0;

  groups.forEach(function (group) {
    // 請求書番号が入っているグループは処理済みとしてスキップ
    if (group.rows.every(function (r) { return r.invoiceNumber !== ''; })) {
      skipped++;
      return;
    }
    try {
      const invoiceNumber = nextInvoiceNumber_(group.issueDate, sequence);
      processGroup_(ss, dataSheet, group, invoiceNumber);
      created++;
      log_(ss, '作成: ' + invoiceNumber + ' / ' + group.customerName + ' / 明細 ' + group.rows.length + ' 件');
    } catch (e) {
      failed++;
      log_(ss, 'エラー: ' + group.customerName + ' - ' + e.message);
    }
  });

  const message = '処理が完了しました。作成 ' + created + ' 件 / スキップ ' + skipped + ' 件 / エラー ' + failed + ' 件';
  log_(ss, message);
  try {
    SpreadsheetApp.getUi().alert(message);
  } catch (e) {
    // トリガー実行時など UI が無い場合は何もしない
  }
}

// ==============================
// データ読み取り
// ==============================
function readInvoiceRows_(sheet) {
  const values = sheet.getDataRange().getValues();
  if (values.length < 2) return [];

  const headers = values[0];
  const idx = {};
  Object.keys(COLUMNS).forEach(function (key) {
    idx[key] = headers.indexOf(COLUMNS[key]);
    if (idx[key] === -1) {
      throw new Error('「請求データ」シートに列「' + COLUMNS[key] + '」がありません。');
    }
  });

  const rows = [];
  for (let i = 1; i < values.length; i++) {
    const v = values[i];
    if (v[idx.CUSTOMER] === '' && v[idx.ITEM_NAME] === '') continue; // 空行は無視
    rows.push({
      rowNumber: i + 1, // シート上の行番号（1始まり）
      customerName: String(v[idx.CUSTOMER]).trim(),
      contactName: String(v[idx.CONTACT]).trim(),
      email: String(v[idx.EMAIL]).trim(),
      issueDate: v[idx.ISSUE_DATE],
      dueDate: v[idx.DUE_DATE],
      itemName: String(v[idx.ITEM_NAME]).trim(),
      qty: Number(v[idx.QTY]) || 0,
      unit: String(v[idx.UNIT]).trim(),
      price: Number(v[idx.PRICE]) || 0,
      invoiceNumber: String(v[idx.INVOICE_NUMBER]).trim(),
      invoiceNumberCol: idx.INVOICE_NUMBER + 1, // 列番号（1始まり）
    });
  }
  return rows;
}

// 請求先＋請求日でグループ化する（1グループ＝請求書1枚）
function groupRows_(rows) {
  const map = {};
  const order = [];
  rows.forEach(function (row) {
    const key = row.customerName + '|' + formatDate_(row.issueDate, 'yyyyMMdd');
    if (!map[key]) {
      map[key] = {
        customerName: row.customerName,
        contactName: row.contactName,
        email: row.email,
        issueDate: row.issueDate,
        dueDate: row.dueDate,
        rows: [],
      };
      order.push(key);
    }
    map[key].rows.push(row);
  });
  return order.map(function (key) { return map[key]; });
}

// 既存の請求書番号の件数（採番の開始位置に使う）
function countExistingInvoiceNumbers_(sheet) {
  const values = sheet.getDataRange().getValues();
  const colIdx = values[0].indexOf(COLUMNS.INVOICE_NUMBER);
  if (colIdx === -1) return 0;
  const seen = {};
  let count = 0;
  for (let i = 1; i < values.length; i++) {
    const num = String(values[i][colIdx]).trim();
    if (num !== '' && !seen[num]) {
      seen[num] = true;
      count++;
    }
  }
  return count;
}

function nextInvoiceNumber_(issueDate, sequence) {
  sequence.value++;
  const ym = formatDate_(issueDate, 'yyyyMM');
  const seq = ('000' + sequence.value).slice(-3);
  return CONFIG.INVOICE_NUMBER_PREFIX + '-' + ym + '-' + seq;
}

// ==============================
// 請求書1枚分の処理
// ==============================
function processGroup_(ss, dataSheet, group, invoiceNumber) {
  if (!group.email) {
    throw new Error('メールアドレスが未入力です。');
  }
  if (group.rows.length === 0) {
    throw new Error('明細がありません。');
  }
  if (group.rows.length > CONFIG.CELLS.ITEM_MAX_ROWS) {
    throw new Error('明細が ' + CONFIG.CELLS.ITEM_MAX_ROWS + ' 行を超えています。テンプレートの明細行を増やしてください。');
  }

  // 金額計算
  let subtotal = 0;
  const items = group.rows.map(function (row) {
    const amount = row.qty * row.price;
    subtotal += amount;
    return { name: row.itemName, qty: row.qty, unit: row.unit, price: row.price, amount: amount };
  });
  const tax = Math.floor(subtotal * CONFIG.TAX_RATE); // 消費税は切り捨て
  const total = subtotal + tax;

  // テンプレートを複製して転記し、PDF 化する（原本のテンプレートは汚さない）
  const template = ss.getSheetByName(CONFIG.TEMPLATE_SHEET_NAME);
  const work = template.copyTo(ss);
  work.setName('tmp_' + invoiceNumber);
  try {
    fillTemplate_(work, group, invoiceNumber, items, subtotal, tax, total);
    SpreadsheetApp.flush();
    const pdfBlob = exportSheetToPdf_(ss, work);

    // Drive へ保存
    const folder = getOrCreateFolder_(CONFIG.PDF_FOLDER_NAME);
    const fileName = invoiceNumber + '_' + group.customerName + '.pdf';
    const file = folder.createFile(pdfBlob.setName(fileName));

    // Gmail の下書きを作成（送信はしない）
    const subject = applyPlaceholders_(CONFIG.MAIL_SUBJECT, group, invoiceNumber, total);
    const body = applyPlaceholders_(CONFIG.MAIL_BODY, group, invoiceNumber, total);
    GmailApp.createDraft(group.email, subject, body, {
      attachments: [file.getBlob()],
      name: CONFIG.ISSUER.NAME,
    });
  } finally {
    ss.deleteSheet(work);
  }

  // 処理済みの印として、グループ全行に請求書番号を書き戻す
  group.rows.forEach(function (row) {
    dataSheet.getRange(row.rowNumber, row.invoiceNumberCol).setValue(invoiceNumber);
  });
}

function fillTemplate_(sheet, group, invoiceNumber, items, subtotal, tax, total) {
  const c = CONFIG.CELLS;
  sheet.getRange(c.CUSTOMER_NAME).setValue(group.customerName + ' 御中');
  sheet.getRange(c.INVOICE_NUMBER).setValue(invoiceNumber);
  sheet.getRange(c.ISSUE_DATE).setValue(formatDate_(group.issueDate, 'yyyy/MM/dd'));
  sheet.getRange(c.DUE_DATE).setValue(formatDate_(group.dueDate, 'yyyy/MM/dd'));

  // 明細エリアをいったんクリアしてから書き込む
  for (let i = 0; i < c.ITEM_MAX_ROWS; i++) {
    const r = c.ITEM_START_ROW + i;
    sheet.getRange(c.COL_ITEM_NAME + r).setValue('');
    sheet.getRange(c.COL_QTY + r).setValue('');
    sheet.getRange(c.COL_UNIT + r).setValue('');
    sheet.getRange(c.COL_PRICE + r).setValue('');
    sheet.getRange(c.COL_AMOUNT + r).setValue('');
  }
  items.forEach(function (item, i) {
    const r = c.ITEM_START_ROW + i;
    sheet.getRange(c.COL_ITEM_NAME + r).setValue(item.name);
    sheet.getRange(c.COL_QTY + r).setValue(item.qty);
    sheet.getRange(c.COL_UNIT + r).setValue(item.unit);
    sheet.getRange(c.COL_PRICE + r).setValue(item.price);
    sheet.getRange(c.COL_AMOUNT + r).setValue(item.amount);
  });

  sheet.getRange(c.SUBTOTAL).setValue(subtotal);
  sheet.getRange(c.TAX).setValue(tax);
  sheet.getRange(c.TOTAL).setValue(total);

  const issuer = CONFIG.ISSUER;
  sheet.getRange(c.ISSUER_INFO).setValue(
    issuer.NAME + '\n' + issuer.ZIP + ' ' + issuer.ADDRESS + '\n' + issuer.EMAIL
  );
  sheet.getRange(c.BANK_INFO).setValue('お振込先：' + issuer.BANK_INFO);
}

function applyPlaceholders_(text, group, invoiceNumber, total) {
  return text
    .replace(/\{customerName\}/g, group.customerName)
    .replace(/\{contactName\}/g, group.contactName || 'ご担当者')
    .replace(/\{invoiceNumber\}/g, invoiceNumber)
    .replace(/\{total\}/g, formatMoney_(total))
    .replace(/\{dueDate\}/g, formatDate_(group.dueDate, 'yyyy/MM/dd'))
    .replace(/\{issuerName\}/g, CONFIG.ISSUER.NAME);
}

// ==============================
// PDF・Drive・ログ
// ==============================
function exportSheetToPdf_(ss, sheet) {
  const url = 'https://docs.google.com/spreadsheets/d/' + ss.getId() + '/export'
    + '?format=pdf'
    + '&gid=' + sheet.getSheetId()
    + '&size=A4'
    + '&portrait=true'
    + '&fitw=true'
    + '&gridlines=false';
  const response = UrlFetchApp.fetch(url, {
    headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
    muteHttpExceptions: true,
  });
  if (response.getResponseCode() !== 200) {
    throw new Error('PDF の生成に失敗しました（HTTP ' + response.getResponseCode() + '）。');
  }
  return response.getBlob();
}

function getOrCreateFolder_(name) {
  const folders = DriveApp.getFoldersByName(name);
  return folders.hasNext() ? folders.next() : DriveApp.createFolder(name);
}

function log_(ss, message) {
  Logger.log(message);
  let sheet = ss.getSheetByName(CONFIG.LOG_SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(CONFIG.LOG_SHEET_NAME);
    sheet.appendRow(['日時', '内容']);
  }
  sheet.appendRow([new Date(), message]);
}

// ==============================
// ユーティリティ
// ==============================
function formatDate_(value, pattern) {
  if (value === '' || value === null || value === undefined) return '';
  const date = value instanceof Date ? value : new Date(value);
  if (isNaN(date.getTime())) return String(value);
  return Utilities.formatDate(date, Session.getScriptTimeZone(), pattern);
}

function formatMoney_(num) {
  return String(num).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}
