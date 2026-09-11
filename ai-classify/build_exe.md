# Windows executable build

Built on 2026-09-11 with Windows 11 x64, Python 3.12.10 and PyInstaller 6.15.0 (contrib hooks 2025.8). Destination PCs do not need Python.

## Exact commands

Run from the project directory in PowerShell. `rtk proxy` is the workspace command wrapper; it can be omitted elsewhere.

PyInstaller was already installed, so no pip installation was needed. Availability check:

```powershell
rtk proxy python -c "import sys, importlib.util; print(sys.version); print(sys.executable); print({m: bool(importlib.util.find_spec(m)) for m in ['PyInstaller', 'yaml', 'openpyxl', 'anthropic', 'openai', 'tkinter']})"
```

For a new environment, use `python -m pip install pyinstaller openpyxl PyYAML anthropic`. These builds **do not include the optional OpenAI SDK**: install `openai` and rebuild both executables before using that provider.

Initial build commands:

```powershell
rtk proxy python -m PyInstaller --noconfirm --onefile --windowed --name classify_to_excel --add-data "rules.example.yaml;." gui.py
rtk proxy python -m PyInstaller --noconfirm --onefile --console --name classify_cli --add-data "rules.example.yaml;." classify_to_excel.py
```

The initial GUI build excluded Tkinter: the build-time Tcl probe could not read `init.tcl`, although Python could read it. The final GUI rebuild retains Tkinter using the checked-in hook and explicitly bundles the matching Tcl/Tk data:

```powershell
rtk proxy python -m PyInstaller --noconfirm --clean --onefile --windowed --name classify_to_excel --additional-hooks-dir pyinstaller_hooks --add-data "rules.example.yaml;." --add-data "C:/Users/gomam/AppData/Local/Programs/Python/Python312/tcl/tcl8.6;_tcl_data" --add-data "C:/Users/gomam/AppData/Local/Programs/Python/Python312/tcl/tk8.6;_tk_data" gui.py
```

Adjust the two absolute Tcl/Tk paths for another build interpreter. Use runtime data from the same Python installation.

## Outputs

- `dist/classify_to_excel.exe`: windowed, onefile GUI; classifier, default rules and Tcl/Tk included. Does not require the CLI exe alongside it.
- `dist/classify_cli.exe`: console, onefile CLI with default rules.
- `classify_to_excel.spec`, `classify_cli.spec`, and `build/`: generated intermediates.
- `.gitignore`: ignores `build/`, `dist/`, `*.spec`, and `__pycache__/`.
- `pyinstaller_hooks/pre_find_module_path/hook-tkinter.py`: retains Tkinter despite the restricted build-time probe.

The GUI calls the imported classifier directly instead of launching a Python script through the frozen executable. The classifier's `main(argv=None)` preserves normal CLI parsing. GUI output and logs are saved beside the executable at `output/result.xlsx` and `output/classify.log`; use a writable folder. Cancelling the picker exits without a console prompt. The GUI has no CLI passthrough.

Default rules are read from the onefile extraction directory using `__file__`. CLI users can override them with `--rules path/to/rules.yaml`. Relative CLI output paths resolve against the working directory.

## Verification

```powershell
rtk proxy .\dist\classify_cli.exe --help
rtk proxy .\dist\classify_cli.exe input\inquiries.csv --out build\smoke\result.xlsx --dry-run --no-cache --provider anthropic
rtk git diff --check
rtk git check-ignore build/ dist/ classify_cli.spec classify_to_excel.spec
```

Both executable invocations exited **0**. The dry run processed 100 rows with `api_calls=0` and `cost=$0.0000`. Reopening the workbook with openpyxl confirmed 100 data rows, `dry-run=True`, and zero API calls. It also generated `build/smoke/result_preview.csv`. No paid API or Claude CLI calls were made.

GUI interactive operation and live provider requests have not been tested. Japanese help text may look garbled with a mismatched console encoding. GUI processing is synchronous and may appear busy.

## Caveats

- Executables are unsigned; Windows SmartScreen may warn about an unrecognized publisher. Consider signing for distribution.
- Antivirus products can flag PyInstaller onefile executables falsely. Verify provenance and submit suspected false positives to the vendor; do not disable protection globally.
- Onefile executables extract into temporary storage on startup, requiring writable temporary space and adding startup time.
- Credentials are not bundled. Live classification requires environment variables and can incur provider charges.
- Existing provider selection chooses Anthropic for `ANTHROPIC_API_KEY`, OpenAI for only `OPENAI_API_KEY`, otherwise external `claude`. The optional OpenAI SDK is absent from these builds. Claude CLI requires separate installation/authentication and is intended for the existing developer demo workflow; configure a supported API provider for end-user use.

## Executable sizes

- dist/classify_to_excel.exe: 45,583,086 bytes (43.47 MiB).
- dist/classify_cli.exe: 42,287,990 bytes (40.33 MiB).

Archive inspection confirmed the rules in both executables and _tkinter.pyd, Tcl and Tk data in the GUI executable.
