# -*- coding: utf-8 -*-
"""
check_links.py

index.html 内のすべての相対 href / src が、実在するファイルを指しているかを確認する
簡易チェッカー。外部URL（http/https/mailto等）とページ内アンカー（#...）はスキップする。
"""

import html.parser
import os
import sys
import urllib.parse

ROOT = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(ROOT, "index.html")

SKIP_SCHEMES = ("http://", "https://", "mailto:", "tel:", "javascript:")


class LinkParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []  # list of (attr_name, value)

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name in ("href", "src") and value:
                self.links.append((tag, name, value))


def main():
    with open(TARGET, "r", encoding="utf-8") as f:
        content = f.read()

    parser = LinkParser()
    parser.feed(content)

    checked = 0
    missing = []
    skipped = 0

    for tag, attr, value in parser.links:
        v = value.strip()
        if not v or v.startswith("#"):
            skipped += 1
            continue
        if v.lower().startswith(SKIP_SCHEMES):
            skipped += 1
            continue
        if v.startswith("//"):
            skipped += 1
            continue

        # 相対パス: フラグメント/クエリを取り除いてファイルパスとして解決
        path_part = urllib.parse.unquote(v.split("#")[0].split("?")[0])
        if not path_part:
            skipped += 1
            continue

        full_path = os.path.normpath(os.path.join(ROOT, path_part))
        checked += 1
        if not os.path.isfile(full_path):
            missing.append((tag, attr, value, full_path))

    print(f"checked relative links: {checked}")
    print(f"skipped (external/anchor): {skipped}")

    if missing:
        print(f"\n[NG] missing targets: {len(missing)}")
        for tag, attr, value, full_path in missing:
            print(f"  <{tag} {attr}=\"{value}\">  ->  {full_path}")
        sys.exit(1)

    print("[OK] all relative href/src resolve to existing files")


if __name__ == "__main__":
    main()
