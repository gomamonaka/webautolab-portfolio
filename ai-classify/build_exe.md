# build_exe.md — PyInstallerでexe化する手順（未実施・手順のみ）

納品先のPCにPython環境がない場合、`gui.py` を単体の `.exe` にまとめて配布できます。
このドキュメントは手順の説明のみで、実際のビルドはまだ行っていません。

## 1. 依存関係をインストール

```bat
pip install pyinstaller openpyxl PyYAML anthropic
```

（`openai` プロバイダを使う場合は `pip install openai` も追加）

## 2. ビルドコマンド（1ファイル・コンソール非表示）

```bat
pyinstaller --onefile --noconsole --name "AI問い合わせ分類" ^
    --add-data "rules.example.yaml;." ^
    gui.py
```

- `--onefile`: 1つのexeにまとめる
- `--noconsole`: コンソールウィンドウを出さない（GUIのみ）。エラー内容を見たい場合は
  一時的に `--console` に変えてビルドし直すとログが見える
- `--add-data "rules.example.yaml;."`: ルール定義ファイルをexeに同梱

生成物は `dist/AI問い合わせ分類.exe` にできます。

## 3. classify_to_excel.py もまとめて同梱する場合

`gui.py` は `subprocess.run([sys.executable, "classify_to_excel.py", ...])` で
別プロセスを呼び出す設計のため、exe化する場合は以下のいずれかの対応が必要です。

- **A（簡単）**: `dist/` フォルダに `classify_to_excel.py` と `rules.example.yaml` を
  同じフォルダに置いて配布する（exeと同じフォルダにPythonスクリプトを置く運用）。
  この場合、配布先PCにも別途Pythonが必要になる点に注意。
- **B（完全スタンドアロン）**: `classify_to_excel.py` の `main()` をモジュールとして
  `import` し、`subprocess.run` の代わりに直接関数呼び出しする形にリファクタリングして
  1つのexeにまとめる。配布先PCにPythonが不要になる。

社内配布・単発案件であれば A で十分です。継続的に販売するツールにする場合は B を推奨します。

## 4. 動作確認チェックリスト

- [ ] `dist/AI問い合わせ分類.exe` をダブルクリックし、ファイル選択ダイアログが出るか
- [ ] サンプルCSV（`input/inquiries.csv`）を選んで正常に `output/result.xlsx` が生成されるか
- [ ] `ANTHROPIC_API_KEY` 等の環境変数が配布先PCに設定されているか（未設定なら
      `--provider claude-cli` は使えないので、事前にAPIキーの取得・設定案内が必要）
- [ ] Windows Defender / SmartScreen の警告が出た場合の案内文を用意する
      （署名なしexeは初回実行時に警告が出ることが多い）

## 5. 配布時の注意

- APIキーをexeやコードに埋め込まない。実行時に環境変数 or 初回起動時の設定画面で
  入力させる方式にすること。
- `--provider claude-cli` はオーナーのClaude Codeサブスクリプションを使う開発者向けの
  デモ生成専用フォールバックです。**エンドユーザー配布版では anthropic または openai
  プロバイダを既定にし、claude-cli は使わないこと。**
