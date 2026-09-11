# -*- coding: utf-8 -*-
"""
gui.py

ダブルクリックで使う簡易GUI。
1. tkinterのファイル選択ダイアログで入力CSV/XLSXを選ぶ
2. classify_to_excel.py を実行して output/result.xlsx を作る
3. 出力フォルダをエクスプローラで開く

tkinterが使えない環境では、コンソールでのパス入力にフォールバックする。
"""

import os
import subprocess
import sys
import traceback
from contextlib import redirect_stdout, redirect_stderr

from classify_to_excel import main as classify_main

ROOT = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))


def pick_input_path() -> str | None:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox
    except Exception:
        print("tkinterが利用できないため、コンソール入力にフォールバックします。")
        path = input("分類したいCSV/XLSXファイルのパスを入力してください: ").strip().strip('"')
        return path or None

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    messagebox.showinfo(
        "AI問い合わせ分類ツール",
        "分類したい問い合わせCSV/XLSXファイルを選択してください。\n"
        "(サンプル: input/inquiries.csv)",
        parent=root,
    )
    path = filedialog.askopenfilename(
        title="分類する問い合わせファイルを選択",
        initialdir=os.path.join(ROOT, "input"),
        filetypes=[("CSV/Excel", "*.csv *.xlsx *.xlsm"), ("すべてのファイル", "*.*")],
        parent=root,
    )
    root.destroy()
    return path or None


def open_folder(path: str):
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.run(["open", path])
        else:
            subprocess.run(["xdg-open", path])
    except Exception as e:  # noqa: BLE001
        print(f"フォルダを開けませんでした: {e}")


def main():
    input_path = pick_input_path()
    if not input_path:
        print("ファイルが選択されませんでした。終了します。")
        return

    out_dir = os.path.join(ROOT, "output")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "result.xlsx")

    args = [
        input_path,
        "--out",
        out_path,
    ]
    log_path = os.path.join(out_dir, "classify.log")
    returncode = 0
    with open(log_path, "w", encoding="utf-8") as log:
        with redirect_stdout(log), redirect_stderr(log):
            try:
                classify_main(args)
            except SystemExit as exc:
                returncode = exc.code or 0
            except Exception:
                traceback.print_exc()
                returncode = 1

    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        if returncode == 0:
            messagebox.showinfo("完了", f"分類が完了しました。\n{out_path}", parent=root)
        else:
            messagebox.showerror("エラー", f"分類処理でエラーが発生しました。\nログを確認してください: {log_path}", parent=root)
        root.destroy()
    except Exception:
        pass

    if returncode == 0:
        open_folder(out_dir)


if __name__ == "__main__":
    main()
