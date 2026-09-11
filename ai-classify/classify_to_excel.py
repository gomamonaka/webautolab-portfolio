# -*- coding: utf-8 -*-
"""
classify_to_excel.py

問い合わせ・自由記述のCSV/XLSXを読み込み、LLM（Anthropic / OpenAI / claude CLI）で
カテゴリ・要約・緊急度・返信要否・返信案を付与し、見やすく整形したExcelを出力する。

使い方:
    python classify_to_excel.py input/inquiries.csv --out output/result.xlsx
    python classify_to_excel.py input/inquiries.csv --out output/result.xlsx --provider anthropic --model claude-haiku-4-5
    python classify_to_excel.py input/inquiries.csv --out output/result.xlsx --provider claude-cli
    python classify_to_excel.py input/inquiries.csv --out output/result.xlsx --dry-run

主なオプション:
    --out          出力Excelパス（既定: output/result.xlsx）
    --provider     anthropic / openai / claude-cli（既定: 自動判定）
    --model        使用モデル（既定はプロバイダごとの既定値）
    --text-col     分類対象の本文カラム名（既定: 問い合わせ本文）
    --rules        カテゴリ定義YAML（既定: rules.example.yaml）
    --batch-size   1リクエストあたりの件数（既定: 20）
    --dry-run      APIを呼ばず "(dry)" で埋めてレイアウトのみ確認
    --no-cache     再実行時のキャッシュ再利用をしない
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass

import yaml
from openpyxl import Workbook, load_workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

NEW_COLS = ["カテゴリ", "要約", "緊急度", "返信要否", "返信案"]
DEFAULT_TEXT_COL = "問い合わせ本文"

# ------------------------------------------------------------------
# プロバイダごとのモデル既定値・概算単価（USD / 1M tokens）
# ------------------------------------------------------------------
DEFAULT_MODELS = {
    "anthropic": "claude-haiku-4-5",
    "openai": "gpt-4o-mini",
    "claude-cli": "claude-haiku-4-5-20251001",
}
PRICE_PER_MTOK = {  # (input, output) USD / 1,000,000 tokens
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-opus-5": (5.00, 25.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
}
USD_JPY = 155  # 概算換算レート（実行ログ表示用）


# ------------------------------------------------------------------
# 入出力ヘルパー
# ------------------------------------------------------------------
def read_rows(path: str) -> tuple[list[str], list[dict]]:
    """CSV/XLSXを読み込み、(列名リスト, 行dictリスト) を返す。"""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xlsm"):
        wb = load_workbook(path, data_only=True)
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        header = [str(c) if c is not None else "" for c in next(rows_iter)]
        rows = []
        for r in rows_iter:
            if all(v is None for v in r):
                continue
            rows.append({header[i]: ("" if r[i] is None else str(r[i])) for i in range(len(header))})
        return header, rows
    else:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            header = reader.fieldnames or []
            rows = [dict(r) for r in reader]
        return header, rows


def load_rules(path: str | None) -> dict:
    if path is None:
        here = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(here, "rules.example.yaml")
    with open(path, "r", encoding="utf-8") as f:
        rules = yaml.safe_load(f)
    return rules


def category_names(rules: dict) -> list[str]:
    return [c["name"] for c in rules["categories"]]


# ------------------------------------------------------------------
# プロンプト構築
# ------------------------------------------------------------------
def build_system_prompt(rules: dict) -> str:
    names = [c["name"] for c in rules["categories"]]
    cat_lines = "\n".join(f"{i}: {c['name']} - {c['definition']}" for i, c in enumerate(rules["categories"]))
    return f"""あなたは日本語のカスタマーサポートの問い合わせ分類アシスタントです。
以下のカテゴリ一覧「だけ」を使って、与えられた問い合わせ本文を分類してください。
新しいカテゴリ名を作ったり、意訳・要約した独自の呼び方をしてはいけません。
判断に迷う場合は最も近いものを選び、どうしても当てはまらない場合のみ「その他」を選んでください。

【カテゴリ一覧（番号: 名称 - 説明）】
{cat_lines}

【緊急度の目安】
{rules.get('urgency_guide', '').strip()}

【返信案の書き方】
{rules.get('reply_tone', '').strip()}
返信案の長さの目安: {rules.get('reply_length_hint', '2〜3文')}

# 厳守事項（違反しないこと。これはコード処理用の機械可読出力であり、会話ではない）
- 出力はJSON配列「そのもの」のみ。前置き・説明・後書き・見出し・箇条書きの理由説明・要約文は一切書かない。
- Markdownのコードフェンス（```）も付けない。1文字目は "[" 、最後の文字は "]" にすること。
- 各オブジェクトのキーは必ず次の7個「だけ」を、必ずこの名前のまま使うこと。
  他の名前（例: subcategory, priority, text, order_number, company_name など）を追加したり
  言い換えたりしてはいけない。
    "id", "quote", "category", "summary", "urgency", "reply_needed", "reply_draft"
  - "id": 入力と同じ整数ID（数値）
  - "quote": その問い合わせ本文の「冒頭15文字」をそのまま一字一句コピーしたもの。
    これは、以降のcategory等を答える前に本文を読み直したことを確認するための項目。
    要約や言い換えは禁止、本文の先頭から連続した文字をそのまま切り出すこと。
  - "category": "quote"で引用した本文の内容にもとづいて判断した、上のカテゴリ一覧の
    「番号」を表す整数（0〜{len(names) - 1}）。文字列のカテゴリ名を書いてはいけません。
    必ず番号（整数）だけを書くこと。他の問い合わせと混同しないよう、必ず直前の
    "quote"の内容だけを見て判断すること。
  - "summary": 40字以内の要約（文字列）。これも"quote"の内容だけにもとづくこと。
  - "urgency": 必ず "高" か "中" か "低" のいずれか1文字の文字列（この3値以外禁止。true/false禁止）
  - "reply_needed": 必ず "要" か "不要" のいずれかの文字列（この2値以外禁止。true/false禁止）
  - "reply_draft": 丁寧な返信案（2〜3文の日本語）
- 入力の件数と出力の件数・idは必ず一致させること。分類理由の説明は不要。
- 複数件をまとめて処理するときも、1件ごとに quote→category→summary→urgency→reply_needed→
  reply_draft の順で、その1件の本文だけを見ながら独立して判断すること。前後の件の内容を
  混同しないこと。

出力例（キー名・値の型の例。内容はダミー。categoryが整数である点に注意）:
[{{"id": 0, "quote": "配送状況の確認をお願いし", "category": 0, "summary": "サンプル要約", "urgency": "低", "reply_needed": "不要", "reply_draft": "お問い合わせいただきありがとうございます。担当者より改めてご連絡いたします。"}}]
"""


def build_user_prompt(batch: list[tuple[int, str]]) -> str:
    lines = [f'{{"id": {i}, "text": {json.dumps(t, ensure_ascii=False)}}}' for i, t in batch]
    body = "以下は問い合わせのJSON配列です。それぞれをJSON配列で分類してください。\n[\n" + ",\n".join(lines) + "\n]"
    reminder = (
        "\n\n上記 {n}件を分類し、id/quote/category/summary/urgency/reply_needed/reply_draft の"
        "7キーのみを持つJSONオブジェクトの配列だけを出力してください。"
        "quote は各本文の冒頭15文字をそのまま引用したものにしてください（要約・言い換え禁止）。"
        "category はカテゴリ名の文字列ではなく、カテゴリ一覧の番号（整数）にしてください。"
        "1件ずつ、その本文だけを見て独立に判断し、他の件と混同しないでください。"
        "説明文・コードフェンス・他のキー名は一切禁止です。1文字目は [ 、最後の文字は ] にしてください。"
    ).format(n=len(batch))
    return body + reminder


def extract_json_array(text: str):
    text = text.strip()
    text = re.sub(r"^```(json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError("JSON配列が見つかりませんでした: " + text[:200])
    return json.loads(text[start : end + 1])


# ------------------------------------------------------------------
# プロバイダ実装
# ------------------------------------------------------------------
@dataclass
class BatchResult:
    items: list[dict]
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class BaseProvider:
    name = "base"

    def __init__(self, model: str):
        self.model = model

    def classify_batch(self, batch: list[tuple[int, str]], system_prompt: str) -> BatchResult:
        raise NotImplementedError


class AnthropicProvider(BaseProvider):
    name = "anthropic"

    def __init__(self, model: str):
        super().__init__(model)
        import anthropic

        self.client = anthropic.Anthropic()

    def classify_batch(self, batch, system_prompt) -> BatchResult:
        user_prompt = build_user_prompt(batch)
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        items = extract_json_array(text)
        in_tok = resp.usage.input_tokens
        out_tok = resp.usage.output_tokens
        price = PRICE_PER_MTOK.get(self.model, (0.0, 0.0))
        cost = in_tok / 1_000_000 * price[0] + out_tok / 1_000_000 * price[1]
        return BatchResult(items=items, input_tokens=in_tok, output_tokens=out_tok, cost_usd=cost)


class OpenAIProvider(BaseProvider):
    name = "openai"

    def __init__(self, model: str):
        super().__init__(model)
        from openai import OpenAI

        self.client = OpenAI()

    def classify_batch(self, batch, system_prompt) -> BatchResult:
        user_prompt = build_user_prompt(batch)
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        text = resp.choices[0].message.content or ""
        items = extract_json_array(text)
        usage = getattr(resp, "usage", None)
        in_tok = getattr(usage, "prompt_tokens", 0) if usage else 0
        out_tok = getattr(usage, "completion_tokens", 0) if usage else 0
        price = PRICE_PER_MTOK.get(self.model, (0.0, 0.0))
        cost = in_tok / 1_000_000 * price[0] + out_tok / 1_000_000 * price[1]
        return BatchResult(items=items, input_tokens=in_tok, output_tokens=out_tok, cost_usd=cost)


class ClaudeCliProvider(BaseProvider):
    """ローカルの `claude` CLI (Claude Code) をサブプロセスとして呼び出すフォールバック。
    オーナーのサブスクリプションを使用するため、デモ出力生成のみに用途を限定すること。
    """

    name = "claude-cli"

    def classify_batch(self, batch, system_prompt) -> BatchResult:
        import shutil

        exe = shutil.which("claude")
        if exe is None:
            raise RuntimeError("claude CLI not found on PATH")
        user_prompt = build_user_prompt(batch)
        # システムプロンプトは引数、本文（可変長）は標準入力経由で渡す
        # （Windowsのコマンドライン長制限を避け、claude .cmd ラッパーの解決問題も回避するため
        #  shutil.which で解決したフルパスを使う）
        cmd = [
            exe,
            "-p",
            "--model",
            self.model,
            "--output-format",
            "json",
            "--system-prompt",
            system_prompt,
        ]
        proc = subprocess.run(
            cmd,
            input=user_prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"claude CLI failed (code {proc.returncode}): {proc.stderr[:500]}")
        outer = json.loads(proc.stdout)
        if outer.get("is_error"):
            raise RuntimeError(f"claude CLI returned error: {outer.get('result')}")
        result_text = outer.get("result", "")
        items = extract_json_array(result_text)
        usage = outer.get("usage", {}) or {}
        in_tok = usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0)
        out_tok = usage.get("output_tokens", 0)
        cost = outer.get("total_cost_usd", 0.0) or 0.0
        return BatchResult(items=items, input_tokens=in_tok, output_tokens=out_tok, cost_usd=cost)


def make_provider(name: str, model: str) -> BaseProvider:
    if name == "anthropic":
        return AnthropicProvider(model)
    if name == "openai":
        return OpenAIProvider(model)
    if name == "claude-cli":
        return ClaudeCliProvider(model)
    raise ValueError(f"unknown provider: {name}")


def auto_detect_provider() -> str:
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    return "claude-cli"


# ------------------------------------------------------------------
# キャッシュ（再実行時にAPIを呼び直さないための resumable cache）
# ------------------------------------------------------------------
def cache_key_for(input_path: str, provider: str, model: str, rules_path: str) -> str:
    raw = f"{os.path.abspath(input_path)}|{provider}|{model}|{os.path.abspath(rules_path)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def row_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def load_cache(cache_path: str) -> dict:
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache_path: str, cache: dict) -> None:
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    tmp = cache_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=0)
    os.replace(tmp, cache_path)


REQUIRED_KEYS = ("category", "summary", "urgency", "reply_needed", "reply_draft")
# "quote" は必須スキーマではなく、id⇄本文の対応が合っているかを検証するための
# グラウンディング用フィールド(あれば使う。無ければ id ベースの対応にフォールバック)。


def validate_schema(
    items: list[dict],
    expected_n: int,
    valid_categories: list[str] | None = None,
    max_missing_ratio: float = 0.3,
) -> None:
    """モデルが指示したキー名そのものを無視した場合(全く違う構造を返す等)に検出し、
    呼び出し側でリトライさせるための検証。値の表記ゆれ(英語表記・真偽値など)は
    normalize_* 側で吸収するため、ここではキーの存在有無だけを見る。"""
    if not items:
        raise ValueError("empty JSON array returned")
    bad = 0
    for it in items:
        if not isinstance(it, dict) or any(k not in it for k in REQUIRED_KEYS):
            bad += 1
    if bad / max(len(items), 1) > max_missing_ratio:
        raise ValueError(
            f"response ignored requested schema: {bad}/{len(items)} items missing required keys "
            f"{REQUIRED_KEYS}"
        )


_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "配送遅延": ["配送", "発送", "到着", "shipping", "delivery", "deliver", "shipment", "logistics", "late", "delay"],
    "返品・交換": ["返品", "交換", "return", "exchange"],
    "不良品": ["不良", "破損", "故障", "defect", "damaged", "broken", "quality_issue", "faulty"],
    "請求・領収書": ["請求", "領収書", "課金", "invoice", "billing", "receipt", "payment", "charge"],
    "使い方の質問": ["使い方", "使用方法", "howto", "how_to", "usage", "instructions"],
    "予約変更": ["予約", "reservation", "booking", "appointment", "schedule"],
    "クレーム": ["クレーム", "苦情", "complaint", "dissatisf", "unhappy"],
    "感謝・好意的な感想": ["感謝", "お礼", "好意的", "thanks", "gratitude", "praise", "compliment", "positive_feedback"],
    "営業・売り込み": ["営業", "売り込み", "提案", "sales", "marketing", "promotion", "vendor", "partnership", "b2b"],
    "採用問い合わせ": ["採用", "求人", "recruitment", "hiring", "recruiting", "career", "employment"],
    "その他": ["その他", "other", "misc", "general"],
}


def normalize_category(raw, valid_categories: list[str]) -> str:
    # 1) 整数インデックス（想定どおりの形式）
    if isinstance(raw, bool):
        pass  # bool は int のサブクラスなので明示的に除外
    elif isinstance(raw, int) and 0 <= raw < len(valid_categories):
        return valid_categories[raw]
    elif isinstance(raw, str) and re.fullmatch(r"\d+", raw.strip()):
        idx = int(raw.strip())
        if 0 <= idx < len(valid_categories):
            return valid_categories[idx]

    # 2) 万一モデルが文字列カテゴリ名を返した場合のフォールバック
    raw_s = "" if raw is None else str(raw)
    if raw_s in valid_categories:
        return raw_s
    s = raw_s.strip().lower()
    for cat in valid_categories:
        for kw in _CATEGORY_KEYWORDS.get(cat, [cat]):
            if kw.lower() in s:
                return cat
    return "その他" if "その他" in valid_categories else valid_categories[-1]


def normalize_urgency(raw) -> str:
    s = str(raw).strip().lower()
    if s in ("高", "high", "urgent", "critical", "severe"):
        return "高"
    if s in ("低", "low", "minor"):
        return "低"
    return "中"


# 本文そのものに対するキーワード照合(カテゴリの最終ガードレール)。
# エージェント型CLI経由のモデルは、カテゴリの「番号」自体を独自の内部順序で
# 解釈してしまい、番号方式でも文字列方式でも取り違えることが実測で確認された
# (id/quoteによる行の対応付けは正しく機能する一方、category値だけが信頼できない)。
# そのため、本文中の明確なキーワードで一意にカテゴリを推定できる場合は、
# モデルの出力よりもキーワード一致を優先する安全策を設ける。
TEXT_KEYWORDS: dict[str, list[str]] = {
    "配送遅延": ["配送", "発送", "到着", "届きません", "届いて", "追跡番号", "配達", "配送状況", "発送予定"],
    "返品・交換": ["返品", "交換したい", "サイズ違い", "色違い", "イメージと違", "サイズが思っていた"],
    "不良品": ["不良品", "破損", "故障", "ひび割れ", "汚れ", "カビ", "ほつれ", "縫製", "電源が入りません", "初期不良", "色ムラ", "ファスナーが壊れ"],
    "請求・領収書": ["領収書", "請求書", "請求金額", "二重決済", "引き落とし", "宛名", "確定申告"],
    "使い方の質問": ["使い方", "使用方法", "お手入れ", "洗濯", "食洗機", "分解方法", "サイズ展開", "手入れ方法"],
    "予約変更": ["予約番号", "予約を", "予約の", "予約して", "日程を変更", "日程変更", "振り替え", "体験教室", "陶芸体験", "ワークショップ", "人数を"],
    "クレーム": ["クレーム", "苦情", "対応が悪", "接客態度", "つながりません", "折り返しをください", "二度と利用したくない", "責任者"],
    "感謝・好意的な感想": ["ありがとうございました", "感動しました", "満足", "梱包が丁寧", "気に入っています", "驚きました", "応援しています"],
    "営業・売り込み": ["ご提案させてください", "代行", "コンサルティング", "広告運用", "卸売", "お打ち合わせ", "コラボ企画", "無料診断"],
    "採用問い合わせ": ["採用", "求人", "応募方法", "選考", "アルバイトの募集", "新卒", "ポートフォリオを送付", "勤務地"],
}


def keyword_guess(text: str, valid_categories: list[str]) -> str | None:
    """本文の強いキーワードから一意にカテゴリを推定できる場合のみ返す。
    複数カテゴリが同点で当てはまる、またはヒットが無い場合は None(判断不可)を返す。"""
    scores: dict[str, int] = {}
    for cat in valid_categories:
        n = sum(1 for kw in TEXT_KEYWORDS.get(cat, []) if kw in text)
        if n:
            scores[cat] = n
    if not scores:
        return None
    best = max(scores.values())
    top = [c for c, n in scores.items() if n == best]
    return top[0] if len(top) == 1 else None


def normalize_reply_needed(raw) -> str:
    if isinstance(raw, bool):
        return "要" if raw else "不要"
    s = str(raw).strip().lower()
    if s in ("不要", "false", "no", "not_needed", "none", "n"):
        return "不要"
    return "要"


def fallback_reply_draft(reply_needed: str) -> str:
    """モデルが reply_draft を省略した場合(主に「返信不要」の好意的な感想などで
    まれに発生)に補う、最低限の汎用文面。"""
    if reply_needed == "不要":
        return "温かいお言葉をありがとうございます。今後のサービス向上の参考にさせていただきます。"
    return "お問い合わせいただきありがとうございます。内容を確認のうえ、担当者より改めてご連絡いたします。"


def match_items_to_rows(
    items: list[dict], chunk_idx: list[int], rows: list[dict], text_col: str
) -> dict[int, dict]:
    """モデルの返した各要素を、バッチ内での本来の位置(pos, 0-index)に対応付ける。

    エージェント型CLI経由のモデルは、複数件をまとめて処理すると id と本文の対応が
    ズレることがある(観測済み)。"quote"(本文冒頭の引用)が実際の本文と一致する行を
    優先的に探し、そちらを正として使う。一致しない場合のみ、モデルが返した "id"
    (バッチ内0-indexのつもり)にフォールバックする。
    """
    pos_by_rowidx = {row_i: pos for pos, row_i in enumerate(chunk_idx)}
    used_rows: set[int] = set()
    result: dict[int, dict] = {}

    # 1st pass: quote による内容ベースのマッチング
    remaining_items = []
    for it in items:
        if not isinstance(it, dict):
            continue
        quote = str(it.get("quote", "")).strip()
        matched_row = None
        if len(quote) >= 6:
            for row_i in chunk_idx:
                if row_i in used_rows:
                    continue
                text = rows[row_i][text_col]
                if text.startswith(quote) or quote in text[: len(quote) + 20]:
                    matched_row = row_i
                    break
        if matched_row is not None:
            used_rows.add(matched_row)
            result[pos_by_rowidx[matched_row]] = it
        else:
            remaining_items.append(it)

    # 2nd pass: quote で決着しなかった要素は id(バッチ内0-index)でフォールバック
    for it in remaining_items:
        try:
            pos = int(it["id"])
        except (KeyError, ValueError, TypeError):
            continue
        if 0 <= pos < len(chunk_idx) and pos not in result:
            row_i = chunk_idx[pos]
            if row_i not in used_rows:
                used_rows.add(row_i)
                result[pos] = it

    return result


# ------------------------------------------------------------------
# 分類の実行（リトライ・バックオフ付き）
# ------------------------------------------------------------------
def classify_all(
    rows: list[dict],
    text_col: str,
    provider: BaseProvider,
    system_prompt: str,
    valid_categories: list[str],
    cache: dict,
    cache_path: str,
    batch_size: int,
    use_cache: bool,
    max_retries: int = 4,
) -> dict:
    """cache: {row_hash: {category, summary, urgency, reply_needed, reply_draft}} を更新して返す。"""
    stats = {"batches": 0, "api_calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "elapsed_s": 0.0}

    pending_idx = []
    for i, r in enumerate(rows):
        h = row_hash(r[text_col])
        if use_cache and h in cache:
            continue
        pending_idx.append(i)

    for start in range(0, len(pending_idx), batch_size):
        chunk_idx = pending_idx[start : start + batch_size]
        if not chunk_idx:
            continue
        batch = [(pos, rows[i][text_col]) for pos, i in enumerate(chunk_idx)]
        stats["batches"] += 1

        last_err = None
        for attempt in range(1, max_retries + 1):
            t0 = time.time()
            try:
                stats["api_calls"] += 1
                result = provider.classify_batch(batch, system_prompt)
                stats["elapsed_s"] += time.time() - t0
                stats["input_tokens"] += result.input_tokens
                stats["output_tokens"] += result.output_tokens
                stats["cost_usd"] += result.cost_usd

                validate_schema(result.items, expected_n=len(batch))
                pos_to_item = match_items_to_rows(result.items, chunk_idx, rows, text_col)
                for pos, row_i in enumerate(chunk_idx):
                    item = pos_to_item.get(pos)
                    if item is None:
                        item = {
                            "category": "その他",
                            "summary": "(分類失敗)",
                            "urgency": "中",
                            "reply_needed": "要",
                            "reply_draft": "お問い合わせ内容を確認のうえ、担当者より改めてご連絡いたします。",
                        }
                    cat = normalize_category(item.get("category"), valid_categories)
                    # 本文中に強いキーワードがあればそちらを優先(モデルのカテゴリ番号の
                    # 取り違えに対するガードレール。詳細は keyword_guess のコメント参照)
                    kw_cat = keyword_guess(rows[row_i][text_col], valid_categories)
                    if kw_cat is not None:
                        cat = kw_cat
                    h = row_hash(rows[row_i][text_col])
                    reply_needed = normalize_reply_needed(item.get("reply_needed", "要"))
                    reply_draft = str(item.get("reply_draft", "")).strip() or fallback_reply_draft(reply_needed)
                    cache[h] = {
                        "category": cat,
                        "summary": str(item.get("summary", ""))[:60],
                        "urgency": normalize_urgency(item.get("urgency", "中")),
                        "reply_needed": reply_needed,
                        "reply_draft": reply_draft,
                    }
                save_cache(cache_path, cache)
                last_err = None
                break
            except Exception as e:  # noqa: BLE001
                stats["elapsed_s"] += time.time() - t0
                last_err = e
                wait = min(2 ** attempt, 30)
                print(f"  [warn] batch {stats['batches']} attempt {attempt} failed: {e}. retry in {wait}s", file=sys.stderr)
                time.sleep(wait)
        if last_err is not None:
            print(f"  [error] batch {stats['batches']} failed after {max_retries} attempts, filling fallback values", file=sys.stderr)
            for pos, row_i in enumerate(chunk_idx):
                h = row_hash(rows[row_i][text_col])
                if h not in cache:
                    cache[h] = {
                        "category": "その他",
                        "summary": "(分類失敗)",
                        "urgency": "中",
                        "reply_needed": "要",
                        "reply_draft": "お問い合わせ内容を確認のうえ、担当者より改めてご連絡いたします。",
                    }
            save_cache(cache_path, cache)

    return stats


# ------------------------------------------------------------------
# Excel 出力
# ------------------------------------------------------------------
HEADER_FILL = PatternFill(start_color="FF2F5496", end_color="FF2F5496", fill_type="solid")
HEADER_FONT = Font(color="FFFFFFFF", bold=True)
URGENT_FILL = PatternFill(start_color="FFFFC7CE", end_color="FFFFC7CE", fill_type="solid")
THIN = Side(style="thin", color="FFCCCCCC")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP_COLS = {"問い合わせ本文", "返信案", "要約"}


def autosize_and_style(ws, header: list[str]):
    ws.freeze_panes = "A2"
    for col_i, name in enumerate(header, start=1):
        cell = ws.cell(row=1, column=col_i, value=name)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER

    max_row = ws.max_row
    max_col = len(header)
    for col_i, name in enumerate(header, start=1):
        letter = get_column_letter(col_i)
        max_len = len(name)
        wrap = name in WRAP_COLS
        for row_i in range(2, max_row + 1):
            v = ws.cell(row=row_i, column=col_i).value
            v = "" if v is None else str(v)
            max_len = max(max_len, min(len(v), 60))
            ws.cell(row=row_i, column=col_i).alignment = Alignment(
                wrap_text=wrap, vertical="top", horizontal="left"
            )
            ws.cell(row=row_i, column=col_i).border = BORDER
        width = max(10, min(max_len + 2, 60 if wrap else 22))
        ws.column_dimensions[letter].width = width

    ws.auto_filter.ref = f"A1:{get_column_letter(max_col)}{max_row}"

    # 緊急度=高 の行に条件付き書式（行全体を塗る）
    if "緊急度" in header:
        urg_col = header.index("緊急度") + 1
        urg_letter = get_column_letter(urg_col)
        rng = f"A2:{get_column_letter(max_col)}{max_row}"
        rule = FormulaRule(formula=[f'${urg_letter}2="高"'], fill=URGENT_FILL)
        ws.conditional_formatting.add(rng, rule)


def write_result_sheet(wb: Workbook, header: list[str], rows: list[dict]):
    ws = wb.active
    ws.title = "分類結果"
    ws.append(header)  # 先にヘッダー行(1行目)を確保してから本文を追記する
    for r in rows:
        ws.append([r.get(h, "") for h in header])
    autosize_and_style(ws, header)
    return ws


def write_summary_sheet(wb: Workbook, rows: list[dict]):
    ws = wb.create_sheet("集計")
    ws["A1"] = "カテゴリ別件数"
    ws["A1"].font = Font(bold=True)
    cats = {}
    urg = {"高": 0, "中": 0, "低": 0}
    for r in rows:
        cats[r.get("カテゴリ", "")] = cats.get(r.get("カテゴリ", ""), 0) + 1
        u = r.get("緊急度", "")
        if u in urg:
            urg[u] += 1

    ws.append([])
    ws["A2"] = "カテゴリ"
    ws["B2"] = "件数"
    ws["A2"].font = ws["B2"].font = Font(bold=True)
    row_i = 3
    for cat, cnt in sorted(cats.items(), key=lambda x: -x[1]):
        ws.cell(row=row_i, column=1, value=cat)
        ws.cell(row=row_i, column=2, value=cnt)
        row_i += 1
    cat_end = row_i - 1

    urg_start = row_i + 2
    ws.cell(row=urg_start - 1, column=1, value="緊急度別件数").font = Font(bold=True)
    ws.cell(row=urg_start, column=1, value="緊急度").font = Font(bold=True)
    ws.cell(row=urg_start, column=2, value="件数").font = Font(bold=True)
    for j, level in enumerate(["高", "中", "低"]):
        ws.cell(row=urg_start + 1 + j, column=1, value=level)
        ws.cell(row=urg_start + 1 + j, column=2, value=urg[level])
    urg_end = urg_start + 3

    for col_letter, width in [("A", 22), ("B", 10)]:
        ws.column_dimensions[col_letter].width = width

    # カテゴリ別棒グラフ
    chart1 = BarChart()
    chart1.title = "カテゴリ別件数"
    chart1.y_axis.title = "件数"
    chart1.x_axis.title = "カテゴリ"
    data = Reference(ws, min_col=2, min_row=2, max_row=cat_end)
    cats_ref = Reference(ws, min_col=1, min_row=3, max_row=cat_end)
    chart1.add_data(data, titles_from_data=True)
    chart1.set_categories(cats_ref)
    chart1.width, chart1.height = 18, 9
    ws.add_chart(chart1, "D2")

    # 緊急度別棒グラフ
    chart2 = BarChart()
    chart2.title = "緊急度別件数"
    chart2.y_axis.title = "件数"
    data2 = Reference(ws, min_col=2, min_row=urg_start, max_row=urg_end)
    cats_ref2 = Reference(ws, min_col=1, min_row=urg_start + 1, max_row=urg_end)
    chart2.add_data(data2, titles_from_data=True)
    chart2.set_categories(cats_ref2)
    chart2.width, chart2.height = 18, 9
    ws.add_chart(chart2, "D20")


def write_log_sheet(wb: Workbook, log: dict):
    ws = wb.create_sheet("実行ログ")
    ws["A1"] = "実行ログ"
    ws["A1"].font = Font(bold=True, size=13)
    items = [
        ("実行日時", log["run_at"]),
        ("入力ファイル", log["input_path"]),
        ("処理件数", log["n_rows"]),
        ("バッチ数", log["batches"]),
        ("1バッチあたり件数", log["batch_size"]),
        ("API呼び出し回数", log["api_calls"]),
        ("プロバイダ", log["provider"]),
        ("モデル", log["model"]),
        ("処理時間(秒)", round(log["elapsed_s"], 1)),
        ("入力トークン数(概算)", log["input_tokens"]),
        ("出力トークン数(概算)", log["output_tokens"]),
        ("概算コスト(USD)", round(log["cost_usd"], 4)),
        ("概算コスト(円 @{}円/USD)".format(USD_JPY), round(log["cost_usd"] * USD_JPY, 1)),
        ("dry-run", log["dry_run"]),
        ("キャッシュ利用", log["used_cache"]),
    ]
    row_i = 3
    for k, v in items:
        ws.cell(row=row_i, column=1, value=k).font = Font(bold=True)
        ws.cell(row=row_i, column=2, value=v)
        row_i += 1
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 50


def write_preview_csv(header: list[str], rows: list[dict], out_xlsx_path: str, n: int = 15):
    stem, _ = os.path.splitext(out_xlsx_path)
    preview_path = stem + "_preview.csv"
    with open(preview_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        for r in rows[:n]:
            w.writerow({h: r.get(h, "") for h in header})
    return preview_path


# ------------------------------------------------------------------
# main
# ------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description="問い合わせ自由記述をAI分類しExcel化するツール")
    ap.add_argument("input", help="入力CSV/XLSXパス")
    ap.add_argument("--out", default=os.path.join("output", "result.xlsx"), help="出力Excelパス")
    ap.add_argument("--provider", choices=["anthropic", "openai", "claude-cli"], default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--text-col", default=DEFAULT_TEXT_COL)
    ap.add_argument("--rules", default=None, help="カテゴリ定義YAML（既定: rules.example.yaml）")
    ap.add_argument("--batch-size", type=int, default=20)
    ap.add_argument("--dry-run", action="store_true", help="APIを呼ばずレイアウトのみ確認")
    ap.add_argument("--no-cache", action="store_true", help="キャッシュを使わず全件呼び直す")
    args = ap.parse_args(argv)

    t_start = time.time()

    provider_name = args.provider or auto_detect_provider()
    model = args.model or DEFAULT_MODELS[provider_name]
    rules_path = args.rules or os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules.example.yaml")
    rules = load_rules(args.rules)
    valid_categories = category_names(rules)

    header, rows = read_rows(args.input)
    if args.text_col not in header:
        print(f"[error] text column '{args.text_col}' not found in {header}", file=sys.stderr)
        sys.exit(1)

    print(f"Loaded {len(rows)} rows from {args.input}")
    print(f"Provider: {provider_name}, Model: {model}, dry-run: {args.dry_run}")

    out_header = header + [c for c in NEW_COLS if c not in header]

    cache_dir = os.path.join(os.path.dirname(os.path.abspath(args.out)) or ".", ".cache")
    ck = cache_key_for(args.input, provider_name, model, rules_path)
    cache_path = os.path.join(cache_dir, f"{ck}.json")

    log = {
        "run_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "input_path": args.input,
        "n_rows": len(rows),
        "batch_size": args.batch_size,
        "provider": provider_name,
        "model": model,
        "dry_run": args.dry_run,
        "used_cache": not args.no_cache,
        "batches": 0,
        "api_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0,
        "elapsed_s": 0.0,
    }

    if args.dry_run:
        for r in rows:
            for c in NEW_COLS:
                r[c] = "(dry)"
        log["batches"] = (len(rows) + args.batch_size - 1) // args.batch_size
    else:
        cache = {} if args.no_cache else load_cache(cache_path)
        provider = make_provider(provider_name, model)
        system_prompt = build_system_prompt(rules)
        stats = classify_all(
            rows=rows,
            text_col=args.text_col,
            provider=provider,
            system_prompt=system_prompt,
            valid_categories=valid_categories,
            cache=cache,
            cache_path=cache_path,
            batch_size=args.batch_size,
            use_cache=not args.no_cache,
        )
        log.update(stats)
        for r in rows:
            h = row_hash(r[args.text_col])
            c = cache.get(h, {})
            r["カテゴリ"] = c.get("category", "その他")
            r["要約"] = c.get("summary", "")
            r["緊急度"] = c.get("urgency", "中")
            reply_needed = c.get("reply_needed", "要")
            r["返信要否"] = reply_needed
            r["返信案"] = c.get("reply_draft", "").strip() or fallback_reply_draft(reply_needed)

    log["elapsed_s"] = time.time() - t_start

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    wb = Workbook()
    write_result_sheet(wb, out_header, rows)
    write_summary_sheet(wb, rows)
    write_log_sheet(wb, log)
    wb.save(args.out)
    print(f"Wrote {args.out}")

    preview_path = write_preview_csv(out_header, rows, args.out, n=15)
    print(f"Wrote {preview_path}")

    print(
        f"Done. rows={len(rows)} batches={log['batches']} api_calls={log.get('api_calls', 0)} "
        f"elapsed={log['elapsed_s']:.1f}s cost=${log.get('cost_usd', 0):.4f}"
    )


if __name__ == "__main__":
    main()
