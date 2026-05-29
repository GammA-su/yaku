# Yaku — AI Visual Novel Translator

Yaku is a real-time translator for Japanese visual novels. It captures the game
on screen, runs OCR on the dialogue, translates it (DeepL or a local llama.cpp
model), and shows the English either as a floating overlay or inside a mirrored
copy of the game window.

It runs **Windows-first** but the core works cross-platform; features that need
Windows APIs (input forwarding, dxcam/pywin32 capture) degrade gracefully
elsewhere.

---
<p>
  <img width="501" height="414" alt="image" src="https://github.com/user-attachments/assets/ac9b428a-0974-4155-b2f4-bf491c375970" />
  <img width="652" height="414" alt="image" src="https://github.com/user-attachments/assets/f3ba360c-f1c1-4162-a249-543d1a863348" />
</p>


## V1 vs V2

| | `v1-overlay` | `v2-mirror` |
|---|---|---|
| **What it does** | Floating, draggable translation box on top of the game | A separate window that mirrors the game frame with text rendered *into* it |
| **Original text** | Left visible underneath | Covered / inpainted and replaced |
| **Input** | You play the real game directly | Clicks/keys in the mirror are forwarded to the game (Windows) |
| **Best for** | Quick setup, any game, lowest overhead | A cleaner "translated game" look, streaming |
| **Render modes** | n/a | `mask-text`, `inpaint-text`, `ai-text-edit` (experimental) |
| **Maturity** | Stable | Stable for `mask-text`/`inpaint-text` |

**Recommendation:** start with `v1-overlay`. Move to `v2-mirror` with
`mask-text` or `inpaint-text` when you want the text rendered into the frame.

---

## Quick start (recommended first run)

```bash
uv sync
uv run yaku --setup
uv run yaku --profile my-vn --mode v1-overlay --run
```

`--setup` walks you through picking the window, drawing the OCR region, and
choosing a mode/translator, then prints the exact command to run.

Prefer to wire it up by hand? See [Profiles](#profiles) below.

---

## Optional installs

Yaku keeps heavy/native dependencies optional so it installs cleanly everywhere.

```bash
uv add manga-ocr          # Japanese OCR (recommended)
uv add paddleocr          # alternative OCR backend
uv add dxcam pywin32 mss  # capture + Windows window/input support
```

| Need | Install |
|------|---------|
| Japanese OCR | `uv add manga-ocr` |
| Alternative OCR | `uv add paddleocr` |
| Fast Windows capture | `uv add dxcam` |
| Cross-platform capture | `uv add mss` |
| Window picking / input forwarding (Windows) | `uv add pywin32` |

> `dxcam` is not always on PyPI; install from its source if `uv add dxcam` fails.

Run `uv run yaku --health-check` to see exactly what's available and what's missing.

---

## Translators

### DeepL

Set your API key in the environment (Yaku never stores the key in config):

```powershell
# Windows PowerShell
$env:DEEPL_API_KEY="your-key-here"
```

```bash
# macOS / Linux bash
export DEEPL_API_KEY="your-key-here"
```

```bash
uv run yaku --profile my-vn --translator deepl --run
```

### llama.cpp (local model)

Start a llama.cpp server, then point Yaku at it:

```bash
llama-server -m path/to/model.gguf --host 127.0.0.1 --port 8080
```

```bash
uv run yaku --translator llama-cpp --run
```

The base URL defaults to `http://127.0.0.1:8080/v1` and is configurable per
profile under `translator.llama_cpp.base_url`.

---

## Render modes (v2-mirror)

| Render mode | Description |
|-------------|-------------|
| `mask-text` | Draw a semi-transparent box over the text region and render the translation on top (most robust). |
| `inpaint-text` | Erase the original text via OpenCV inpaint, then render exact English on the cleaned background. |
| `ai-text-edit` | **Experimental.** Use a local AI editor (e.g. AnyText2 / SD-inpainting server) to clean/style the region. |

### AI text editing is experimental

> **Warning:** `ai-text-edit` is experimental and **off by default**.
>
> - It requires a separate local AI server; no AI package ships with Yaku.
> - AI-generated text **may misspell or distort English**.
> - It is never trusted by default: with `deterministic_text_after_ai: true` the
>   exact English is re-rendered by code after the AI pass.
> - If the backend is disabled, missing, or fails, Yaku automatically falls back
>   to the configured `fallback` mode and keeps running.
>
> **Recommended default is `inpaint-text` or `mask-text`.**

---

## Profiles

A profile is a full config stored at `profiles/<name>.yaml`. Use one per game so
window selection, OCR region, overlay geometry, and replacement region are saved
separately. A missing profile is created from `configs/default.yaml`.

```bash
uv run yaku --profile game-name --pick-window
uv run yaku --profile game-name --select-ocr-region
uv run yaku --profile game-name --select-replacement-region   # v2 only
uv run yaku --profile game-name --run
```

See [`configs/profile.example.yaml`](configs/profile.example.yaml) for a fully
commented template.

---

## Setup wizard

```bash
uv run yaku --setup
```

Steps: choose a profile name -> pick the VN window -> draw the OCR region ->
choose mode (`v1-overlay`/`v2-mirror`) -> choose translator (`deepl`/`llama-cpp`)
-> (V2) draw the replacement region -> save -> print the exact run command.

---

## Health check

```bash
uv run yaku --health-check
```

Reports `pass` / `warn` / `fail` for: config loading, translator validity, DeepL
key presence (without calling the API), llama.cpp reachability (warning only),
OCR backend availability, capture backend availability, Windows input support
(for V2 when forwarding is on), and that the cache DB and `out/` are writable.
Each failure/warning includes the command to fix it. Exit code is non-zero only
on a hard failure.

---

## CLI reference

```
--profile NAME              use/create profiles/<NAME>.yaml
--config PATH               use a specific config file (default: configs/default.yaml)
--mode                      v1-overlay | v2-mirror
--translator                deepl | llama-cpp
--target-lang               ISO language code (e.g. en, de)
--render-mode               mask-text | inpaint-text | ai-text-edit   (v2 only)
--debug                     verbose logging

# actions (mutually exclusive)
--run                       start the application
--setup                     run the interactive setup wizard
--health-check              run environment/config checks and exit
--pick-window               pick the target VN window
--select-ocr-region         draw the OCR capture region
--select-replacement-region draw the v2 text replacement region
```

### Hotkeys

- **v1-overlay:** F6 OCR region, F7 lock, F8 force OCR, Shift+F8 retranslate, F9 pause, F10 debug, F11 settings
- **v2-mirror:** F8 force OCR, F9 pause, F10 debug, F11 fullscreen, Esc exit

---

## Logs

Logs are written to `out/yaku.log` (rotating, 5 MB x 2 backups) and the console.
API keys and auth tokens are redacted from all log output. Use `--debug` for
verbose logs.

---

## Troubleshooting

- **Black / empty capture.** The game may use fullscreen-exclusive mode or a
  protected surface. Switch the game to *borderless windowed*, or try a different
  capture backend (`window.capture_backend: dxcam` or `mss`).
- **Fullscreen exclusive mode.** DXGI/GDI capture often can't read exclusive
  fullscreen. Use borderless windowed mode in the game.
- **OCR returns the wrong text.** Re-draw a tighter OCR region around just the
  dialogue (`--select-ocr-region`). Make sure `ocr.backend` is installed
  (`uv add manga-ocr`). Increase `ocr.hash_threshold` if it re-reads too often.
- **DeepL key missing.** Set `DEEPL_API_KEY` (see [DeepL](#deepl)). Verify with
  `uv run yaku --health-check`.
- **llama.cpp server unreachable.** Start `llama-server` first and confirm the
  host/port match `translator.llama_cpp.base_url`. Health check shows this as a
  warning, not a crash.
- **pywin32 missing.** Window picking and input forwarding need it on Windows:
  `uv add pywin32`.
- **Wayland limitations (Linux).** Screen capture and global input injection are
  restricted under Wayland. Use an X11 session, or expect capture/forwarding to
  be unavailable; the overlay/mirror display still works.
- **Click forwarding not working (v2).** Forwarding is Windows-only. Ensure
  `v2_mirror.forward_input: true` and a window is selected (`--pick-window`).
  Keyboard keys (Enter/Space/Ctrl) only reach the game in
  `input_focus_mode: focus_then_send`; mouse clicks work in any mode. Clicks in
  the letterbox bars (outside the displayed frame) are intentionally ignored.

---

## Legal / ethical note

Use Yaku only with games you have legally obtained, and respect each game's
license terms, EULA, and the translation/redistribution rights of its
publishers. Yaku is a personal accessibility/translation aid; do not use it to
redistribute copyrighted text or to violate a game's terms of service.

---

## Development

```bash
uv run pytest -q          # run the test suite
uv run yaku --health-check
```

Config lives in `configs/default.yaml`; per-game overrides live in
`profiles/<name>.yaml`. Cache and edited frames are written under `out/`.
