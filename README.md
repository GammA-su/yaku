# Yaku — AI Visual Novel Translator

Yaku is a real-time translator for Japanese visual novels. It captures the game
on screen, runs OCR on the dialogue, translates it (DeepL or a local llama.cpp
model), and shows the English either as a floating overlay or inside a mirrored
copy of the game window.

It runs **Windows-first** but the core works cross-platform; features that need
Windows APIs (input forwarding, dxcam/pywin32 capture) degrade gracefully
elsewhere.

---

## Modes Comparison

| | `v1-overlay` | `v1-overlay-max` | `v2-mirror` | `v3-audio-overlay` | `v4-yomitan` |
|---|---|---|---|---|---|
| **What it does** | Floating translation box over the game window | Draws mini-labels next to every detected Japanese text region | Separate mirrored game window with in-place text replacement | Captures game audio, transcribes with ASR, and displays translation in a floating overlay | Native Yomitan-style Japanese-English dictionary lookup on hover |
| **Input Source** | Screen capture (OCR) | Screen capture (OCR) | Screen capture (OCR) | Audio capture (ASR - Kotoba Whisper) | Screen capture (OCR of region) |
| **Original text** | Left visible underneath | Left visible (labels drawn next to it) | Covered / inpainted and replaced | Hidden (listens to game audio/system voices) | Left visible (dictionary popup overlay displayed on hover) |
| **Best for** | Text OCR, quick setup, any game | Settings menus, buttons, options, choice screens | Dialogue replacement, visual integration | Audio/Voice translation, hands-free listening | Vocabulary lookup, dictionary integration, learning Japanese |
| **Render modes** | n/a | n/a | `mask-text`, `inpaint-text`, `ai-text-edit` (experimental) | n/a (uses V1 overlay display) | n/a (uses native Qt popup) |
| **Maturity** | Stable | Stable | Stable | Stable | Stable |

**Recommendation:** start with `v1-overlay`. Move to `v2-mirror` when you want the text rendered into the frame, use `v1-overlay-max` to translate menus/buttons/choices, use `v3-audio-overlay` if the game has spoken dialogue and you prefer audio transcription, or use `v4-yomitan` to hover over words and look them up in imported dictionaries.

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

### Experimental AI Text Edit Mode

`ai-text-edit` mode sends the dialogue crop and mask to an external HTTP server.

- **Recommended external model:** AnyText2 for high-quality visual text editing.
- **Alternative:** FLUX-Text / ComfyUI workflow.
- **Experimental nature:** AI visual text generation is experimental and can misspell or distort text.
- **Spelling guarantee:** For exact, correct translations, keep `deterministic_text_after_ai: true` (default). This re-renders the exact translated English text on top of the AI edited background.
- **Default fallback:** The default remains `inpaint-text` (or `mask-text`), and Yaku will gracefully fall back to it without crashing if the external HTTP backend fails or is unreachable.

#### Example Config

```yaml
v2_mirror:
  render_mode: ai-text-edit
  ai_text_edit:
    enabled: true
    backend: external_http
    endpoint: "http://127.0.0.1:7861/edit"
    deterministic_text_after_ai: true
    fallback: inpaint-text
```

---

## Audio Overlay Mode (v3-audio-overlay)

Audio Overlay Mode captures Japanese game/system audio or microphone voice feeds, transcribes it with a Kotoba Whisper ASR model, translates the transcript using Yaku's normal DeepL or llama.cpp backends, and displays the translation using the existing V1 floating overlay window.

### Setup and Dependencies

Audio Overlay is optional and depends on heavy packages. The first time you select it from the GUI, Yaku will show a setup assistant asking to install the **Audio Pack**.

The Audio Pack installs:
- `sounddevice` for audio capture
- `numpy` for data processing
- `faster-whisper` for ASR execution
- `silero-vad` for Voice Activity Detection
- `torch` & `torchaudio` for ML backends
- `huggingface-hub` for model downloads

By default, Yaku downloads the **Kotoba Whisper** model (`kotoba-tech/kotoba-whisper-v2.0` - approx. 75MB) and caches it locally under `models/asr`.

### Audio Devices

The user can choose microphone (`mic`), system/game audio (`loopback`), or let Yaku auto-select the best device (`auto`). A default device is chosen automatically on first run, but choosing a WASAPI loopback/system-audio device manually is highly recommended for translating direct Visual Novel game audio.

### Commands for Development and Checking

Install the optional group in your virtual environment:
```powershell
uv sync --extra audio
```

Run audio overlay directly:
```powershell
uv run yaku --mode v3-audio-overlay --translator llama-cpp --target-lang en --run
```

Check your audio configuration, model cache, and available system audio devices:
```powershell
uv run yaku --check-audio
```

Or install the Audio Pack from the CLI:
```powershell
uv run yaku --install-audio-pack
```

Or pre-download the Kotoba Whisper model files:
```powershell
uv run yaku --download-asr-model
```

---

## V1 Overlay Max

"V1 Overlay Max" is designed for full-window UI translations. It scans the entire selected VN window, detects all visible Japanese text regions, translates them using your active translation backend, and renders small translated overlay labels next to each detected region.

### Features
- **Scans Entire Window:** Useful for settings menus, option screens, choice menus, inventories, status screens, and other complex UIs where standard dialogue box OCR is not enough.
- **Requires PaddleOCR:** Bounding boxes are needed to locate regions, so PaddleOCR is required.
- **Timing and Interval:** Because full-window OCR takes more time than scanning a small dialogue rectangle, the recommended scan interval is 1-2 seconds (`scan_interval_ms: 1500`).
- **Translation Caching:** Integrates with Yaku's SQLite translation cache to prevent repeated translations and translation spam of static UI text.

### Commands for Development and Checking
Run v1-overlay-max directly using llama.cpp or DeepL:
```bash
uv run yaku --mode v1-overlay-max --translator llama-cpp --target-lang en --run
uv run yaku --mode v1-overlay-max --translator deepl --target-lang EN-US --run
```

---

## Yomitan Native Dictionary Mode (v4-yomitan)

"Yomitan Native Dictionary" mode implements offline Japanese dictionary lookups directly inside Yaku, styled like Yomitan/Rikaichan. When active, Yaku tracks your mouse cursor position over the selected visual novel region, parses Japanese text deinflections recursively, looks them up in imported Yomitan dictionary ZIP files, and displays a native translucent definition popup next to your cursor.

No external browser extensions or clipboard bridges are required.

### Features
- **Mouse Cursor Tracking:** Hovering over Japanese characters automatically performs lookups. Hover coordinates are mapped using character bounding box approximations relative to the OCR line.
- **Translucent Popup Overlay:** Styled with CSS to show terms, readings, parts of speech, tags, dictionary titles, pitch accents, and frequency ranks. Click-through flags ensure the popup never blocks mouse clicks or window focus for the Visual Novel.
- **Recursive Japanese Deinflector:** BFS-based deinflection resolves verbs, adjectives, potentials, causatives, passives, and polite endings back to base/dictionary forms.
- **SQLite Indexing & Cascading Deletes:** Batch imports Yomitan ZIP archives into an optimized SQLite database. Cascade deletes cleanly wipe associated terms and metadata when a dictionary is deleted.

### Commands for Development and Checking

Run Yomitan mode directly:
```bash
uv run yaku --mode v4-yomitan --run
```

Draw the Yomitan scan region:
```bash
uv run yaku --select-yomitan-region
```

Import Yomitan dictionary ZIP files (reads all ZIP files from your configured dictionary folder, default: `dictionaries/`):
```bash
uv run yaku --import-yomitan-dictionaries
```

Override the dictionary import folder on import or rebuild:
```bash
uv run yaku --import-yomitan-dictionaries --dictionary-dir custom_dictionaries/
```

Rebuild the index (deletes the SQLite file, recreates schemas, and re-imports all dictionary ZIP archives):
```bash
uv run yaku --rebuild-yomitan-index
```

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
--mode                      v1-overlay | v2-mirror | v3-audio-overlay | v1-overlay-max | v4-yomitan
--translator                deepl | llama-cpp
--target-lang               ISO language code (e.g. en, de)
--render-mode               mask-text | inpaint-text | ai-text-edit   (v2 only)
--dictionary-dir PATH       override Yomitan dictionary import directory
--debug                     verbose logging

# actions (mutually exclusive)
--run                       start the application
--setup                     run the interactive setup wizard
--health-check              run environment/config checks and exit
--pick-window               pick the target VN window
--select-ocr-region         draw the OCR capture region
--select-replacement-region draw the v2 text replacement region
--check-audio               check audio dependencies, model availability, and devices
--install-audio-pack         install Audio Pack dependencies
--download-asr-model        pre-download Kotoba Whisper model files
--select-yomitan-region     draw the Yomitan scan region
--import-yomitan-dictionaries import Yomitan dictionary ZIP files
--rebuild-yomitan-index     rebuild Yomitan SQLite index and re-import ZIPs
```

### Hotkeys

- **v1-overlay:** F6 OCR region, F7 lock, F8 force OCR, Shift+F8 retranslate, F9 pause, F10 debug, F11 settings
- **v2-mirror:** F8 force OCR, F9 pause, F10 debug, F11 fullscreen, Esc exit

---

## V2 visual replacement mode

Yaku V2 visual text replacement mode allows playing Visual Novels with the original Japanese dialogue visually replaced by translated text (English/French/etc.) rendered in-place within the dialogue box.

### Features
- **Deterministic Text rendering (Default):** Instead of using a text-to-image generative model which can introduce spelling errors and hallucinations, Yaku uses a hybrid approach:
  1. Japanese text is automatically removed from the dialogue region.
  2. The exact English translation is rendered deterministically using Pillow and FreeType.
- **Render Modes:**
  - `inpaint-text` (Default): Uses OpenCV's fast, localized inpainting algorithms (`Telea` or `Navier-Stokes`) to clean the Japanese text box area, then draws exact translations. If inpainting fails, it degrades gracefully to `mask-text`.
  - `mask-text`: Draws a semi-transparent background box over the original text region to cover it before rendering the translation. Fast, lightweight, and requires no optional packages.
  - `ai-text-edit` (Experimental): An interface for external AnyText2/FLUX-Text style backends to perform style-aligned local edits. Kept disabled by default.
- **Style Sampling:** When `sample_style_from_source` is enabled, Yaku adaptively inspects the color palette and stroke outlines of the original Japanese dialogue and attempts to match them for the English/French rendering.
- **Fast Display Loop:** Dialogue frames are cached based on the crop's hash, meaning visual rendering does not cause interface stuttering or lag.

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

## Benchmarking OCR and translation speed

Yaku includes CLI tools to benchmark translation performance and latency across different backends (DeepL, llama.cpp, etc.).

### 1. Run Benchmarks

Use `yaku-bench-translate` to run repeatable translation tests on a dataset of lines:

**DeepL:**
```powershell
$env:DEEPL_API_KEY="..."
uv run yaku-bench-translate --input benchmarks/vn_lines_ja.txt --translator deepl --target-lang EN-US --repeat 3 --out out/benchmarks/deepl.jsonl
```

**Remote Qwen 27B:**
```powershell
$env:YAKU_REMOTE_LLM_KEY="..."
uv run yaku-bench-translate --input benchmarks/vn_lines_ja.txt --translator llama-cpp --base-url https://llm.iosys.fr/v1 --api-key-env YAKU_REMOTE_LLM_KEY --model qwen-local --target-lang en --repeat 3 --out out/benchmarks/qwen27b_remote.jsonl
```

**Local Qwen 9B:**
```powershell
uv run yaku-bench-translate --input benchmarks/vn_lines_ja.txt --translator llama-cpp --base-url http://127.0.0.1:8089/v1 --model qwen9b --target-lang en --repeat 3 --out out/benchmarks/qwen9b_local.jsonl
```

### 2. View Statistical Summary

Use `yaku-bench-summary` to analyze the logged latencies and token/character rates:

```powershell
uv run yaku-bench-summary out/benchmarks/deepl.jsonl
uv run yaku-bench-summary out/benchmarks/qwen27b_remote.jsonl
```

### 3. Normal App Latency Logs

During standard V1/V2 execution, latency events are automatically written to `out/metrics/yaku_latency.jsonl` when metrics logging is enabled.

To run the app with debug logs:
```powershell
uv run yaku --mode v1-overlay --translator llama-cpp --target-lang en --run --debug
```
Then inspect `out/metrics/yaku_latency.jsonl` for a detailed breakdown of capture, hash, OCR, translation, rendering, and token rate timings.

---

## Development

```bash
uv run pytest -q          # run the test suite
uv run yaku --health-check
```

Config lives in `configs/default.yaml`; per-game overrides live in
`profiles/<name>.yaml`. Cache and edited frames are written under `out/`.
