# Veloce guide

Everything you need to install Veloce, use it day to day, and fix the rare thing that goes wrong.

**Contents**
[1. Install the app](#1-install-the-app) ·
[2. Add the browser extension](#2-add-the-browser-extension) ·
[3. Download a file](#3-download-a-file) ·
[4. Download a video or music](#4-download-a-video-or-music) ·
[5. The Veloce app](#5-the-veloce-app) ·
[6. Settings](#6-settings) ·
[7. Command line](#7-command-line) ·
[8. Run from source](#8-run-from-source) ·
[9. Troubleshooting](#9-troubleshooting) ·
[10. Uninstall](#10-uninstall)

---

## 1. Install the app

The app is the engine that does the fast downloading. It runs quietly in your system tray.

### Download

Get the file for your computer from the [fast download mirror](https://huggingface.co/datasets/Firoj112/veloce-downloads/tree/main/latest) (or the [GitHub release](https://github.com/Firojpaudel/veloce/releases/latest) — same files, often much slower):

| Your computer | File |
| :--- | :--- |
| Windows 10 or 11 | `veloce-setup-windows-x64.exe` (installer) — or `veloce-windows-x64-portable.zip` if you can't install apps |
| Mac with Apple chip (M1 or newer) | `veloce-macos-arm64` |
| Mac with Intel chip | `veloce-macos-x86_64` |
| Linux (64-bit) | `veloce-linux-x86_64` |

> [!TIP]
> Not sure which Mac you have? Apple menu → **About This Mac**. "Chip: Apple M…" means Apple Silicon; "Processor: Intel" means Intel.

### Open it

**Windows** — run the installer. It installs just for you (no admin password), adds Veloce to the Start menu, and offers **Start Veloce when I sign in**; leave it ticked. The portable zip runs from any folder: unzip it and open `Veloce.exe`.

**macOS** — the easiest way is one Terminal line. Files downloaded with `curl` aren't quarantined, so there's no security prompt:

```bash
curl -fL -o /usr/local/bin/veloce https://huggingface.co/datasets/Firoj112/veloce-downloads/resolve/main/latest/veloce-macos-arm64 && chmod +x /usr/local/bin/veloce && veloce
```

On an Intel Mac use `veloce-macos-x86_64`. If you're asked for a password, put `sudo` before `curl` and `chmod`.

**Linux** — in the folder where you downloaded it:

```bash
chmod +x veloce-linux-x86_64 && ./veloce-linux-x86_64
```

> [!WARNING]
> **The first launch may show a security prompt** because Veloce isn't code-signed yet. It's about the missing signature, not about anything the app does. You see it once, for the installer only.
>
> - **Windows, in the browser** ("isn't commonly downloaded" / "may be dangerous"): open the downloads list, then **⋯ → Keep** (Edge: **⋯ → Keep → Show more → Keep anyway**).
> - **Windows, when you run it** ("Windows protected your PC"): **More info → Run anyway**.
> - **macOS** ("can't be opened" / "Apple could not verify"): **System Settings → Privacy & Security**, scroll down, **Open Anyway**. The Terminal install above avoids this entirely.

### Finish

The Veloce window opens in your browser at `http://127.0.0.1:9229`, and a Veloce icon appears in your system tray (top bar on macOS, bottom-right on Windows). Turn on **Start at login** when the window offers it — from then on Veloce starts quietly every time you sign in, and you never have to open it again.

> [!NOTE]
> Opening Veloce a second time doesn't start a second copy — it just brings up the window. To close Veloce completely, use the tray icon → **Quit Veloce**.

---

## 2. Add the browser extension

The extension adds the **Download** button to videos and hands browser downloads to the app. It works in Chrome, Edge, Brave, Opera, Vivaldi and other Chromium browsers.

1. Download [`veloce-extension.zip`](https://huggingface.co/datasets/Firoj112/veloce-downloads/resolve/main/latest/veloce-extension.zip) and unzip it somewhere permanent (for example `Documents/veloce-extension`). Don't delete the folder afterwards — the browser loads it from there.
2. Open `chrome://extensions` (Edge: `edge://extensions`).
3. Switch on **Developer mode** (top-right).
4. Click **Load unpacked** and choose the unzipped folder.
5. Click the puzzle-piece icon in the toolbar and **pin** Veloce.

Check it worked: click the Veloce icon. The badge next to the name should say **Ready**. If it says **Off**, the app isn't running — open it (step 1).

> [!TIP]
> <kbd>Alt</kbd> <kbd>Shift</kbd> <kbd>V</kbd> opens the Veloce popup from anywhere in the browser.

---

## 3. Download a file

There are four ways; use whichever is handiest.

**Just download as usual.** Click any download link in your browser. When the app is running, Veloce catches it automatically (with the browser's own file name and your site login) and downloads it faster. Tiny files under 1 MB are left to the browser, where they finish fastest.

**Paste a link.** Copy a link, open the Veloce popup (or the app and press <kbd>N</kbd>), and paste. Veloce checks the link first and shows the real file name, size, and whether it can use several connections. Rename the file if you like, then press **Download**.

**Right-click.** Right-click any link → **Download link with Veloce**.

**Paste anywhere in the app.** With the Veloce window focused, just press <kbd>Ctrl</kbd> <kbd>V</kbd> (<kbd>⌘</kbd> <kbd>V</kbd> on Mac) — the new-download sheet opens with your link.

Files are saved to `Downloads/veloce` in your home folder. Veloce never overwrites a file: a second copy becomes `name (1).ext`.

---

## 4. Download a video or music

<p align="center">
  <img src="media/grab-a-video.gif" alt="Hovering a YouTube video, pressing Download, switching to Audio only and saving an MP3" width="760">
</p>

1. **Point at the video** you're watching. A small **Download** button appears in its top-right corner.
2. **Click it.** Veloce finds every available quality — this takes a few seconds.
3. Choose:
   - **Video** — pick a resolution. The highlighted one (up to 1080p) is a good default.
   - **Audio only** — **MP3** plays everywhere; **M4A** suits Apple devices; **Opus** is the smallest for its quality; **FLAC** keeps the source audio in a lossless container.
4. Press **Download**. Progress shows in the Veloce popup and app.

**Works on** YouTube (including Shorts), TikTok, Instagram Reels and posts, X / Twitter, Facebook, Vimeo, Reddit, Twitch clips, SoundCloud, Bandcamp and 1,800+ other sites, plus ordinary video players on any page.

**Playlists.** Open a video that's part of a playlist (a YouTube link with `&list=` in it, a playlist page, a SoundCloud set). In the picker, turn on **Whole playlist** — or open the **Playlist** tab to tick exactly the videos you want. They're saved together in a folder named after the playlist and download three at a time.

**From the popup.** On a video page, the popup shows a **Download this video** card at the top — the same choices, without touching the page.

**Login-only videos** (members-only, private links you can see, age-restricted) work because the extension passes your browser's login for that site to the app on your own computer. Turn this off in settings if you prefer.

> [!IMPORTANT]
> Video downloads need the app running. If the popup says **Off**, open Veloce first.

> [!CAUTION]
> Only download what you have the right to keep. Veloce doesn't break DRM, so Spotify, Netflix and similar protected streams won't work — by design.

---

## 5. The Veloce app

<p align="center">
  <img src="media/desktop-app.gif" alt="Starting a download in the Veloce app, its connection lanes filling, then pausing it from the command palette" width="760">
</p>

- **Sidebar:** all downloads, what's in progress, completed, anything that needs attention, and file types (videos, audio, documents, archives, programs).
- **Each row** shows the file, where it came from, and its status. While downloading, the bar is split into **lanes** — one per connection — so you can see Veloce working.
- **Hover a row** for its actions: pause, resume, show in folder, copy link, remove. *Remove* only takes it off the list; your file stays on disk.
- **Search** with <kbd>/</kbd>, or use the **command palette** (<kbd>Ctrl</kbd> <kbd>K</kbd>, <kbd>⌘</kbd> <kbd>K</kbd> on Mac) for everything: new download, pause all, resume all, retry failed, switch theme, jump anywhere.

**Keyboard shortcuts**

| Key | Does |
| :--- | :--- |
| <kbd>N</kbd> | New download |
| <kbd>Ctrl</kbd>/<kbd>⌘</kbd> <kbd>V</kbd> | Download the link on your clipboard |
| <kbd>Ctrl</kbd>/<kbd>⌘</kbd> <kbd>K</kbd> | Command palette |
| <kbd>/</kbd> | Filter the list |
| <kbd>↑</kbd> <kbd>↓</kbd> or <kbd>J</kbd> <kbd>K</kbd> | Move between downloads |
| <kbd>Space</kbd> | Pause or resume the selected download |
| <kbd>Enter</kbd> | Show the selected file in its folder |
| <kbd>Delete</kbd> | Remove the selected item from the list |
| <kbd>Esc</kbd> | Close a sheet or the palette |

**Tray icon:** open Veloce, open the downloads folder, toggle *Start at login*, quit. Its tooltip shows how many downloads are running and how fast.

---

## 6. Settings

**In the extension** (popup → gear icon)

| Setting | What it does |
| :--- | :--- |
| Theme | System (default), Light or Dark |
| Catch browser downloads | Hand normal downloads to Veloce while the app is running |
| Skip files smaller than | Leave small files to the browser (default 1 MB) |
| Never catch downloads from | Sites to always leave to the browser, one per line |
| Connections per file | The most Veloce may use (it usually needs fewer) |
| Use my site logins | Pass this browser's cookies to the app for login-only files and videos |
| Notify when downloads finish | Desktop notification, with **Show in folder** |

**In the app** (sidebar → Settings): theme, start at login, download folder, connections, and the yt-dlp / ffmpeg status with a **Check for update** button.

**Advanced** — environment variables, set before starting the app:

| Variable | Effect |
| :--- | :--- |
| `VELOCE_DOWNLOAD_DIR` | Save downloads somewhere other than `~/Downloads/veloce` |
| `VELOCE_HOME` | Where history, logs and updates live (default `~/.veloce`) |
| `VELOCE_NO_AUTO_UPDATE=1` | Don't update yt-dlp automatically |
| `VELOCE_EXTENSION_IDS` | Accept requests only from these extension IDs (comma-separated) |

---

## 7. Command line

The same file you downloaded is also a command-line tool. Examples use the Linux name — use your own file's name.

```bash
./veloce-linux-x86_64                         # start the app (same as double-clicking)
./veloce-linux-x86_64 download https://example.com/big.iso -o ~/Downloads/ -c 16
./veloce-linux-x86_64 autostart enable        # start at login (disable / status also work)
./veloce-linux-x86_64 daemon                  # engine only, in this terminal (servers, debugging)
./veloce-linux-x86_64 --help
```

`download` shows a live progress bar; <kbd>Ctrl</kbd> <kbd>C</kbd> pauses and keeps the partial file.

---

## 8. Run from source

For development, or on platforms without a prebuilt file.

```bash
git clone https://github.com/Firojpaudel/veloce.git
cd veloce
python3 -m pip install -r requirements.txt    # yt-dlp, and pystray + Pillow for the tray icon
python3 main.py                               # the app
```

- Python **3.10+**. The engine itself uses only the standard library; the requirements add video support and the tray icon.
- Install **ffmpeg** for HD video (it merges separate video and audio) and MP3 conversion: `winget install ffmpeg`, `brew install ffmpeg`, or `sudo apt install ffmpeg`.
- Load the `extension/` folder as an unpacked extension (section 2).
- Tests: `python3 -m unittest discover -s tests` (no network needed).

---

## 9. Troubleshooting

| What you see | What to do |
| :--- | :--- |
| Popup says **Off** | The app isn't running. Open it, or turn on *Start at login*. |
| No **Download** button on a video | Reload the page once after installing or updating the extension. The button appears when you point at the video itself. |
| "Couldn't get this video" | The site may need you to be signed in — sign in in this browser and try again. Very new site changes are usually fixed by the daily yt-dlp update; in the app: Settings → **Check for update**. |
| Video says "Setting up video support" | First run only: Veloce is downloading ffmpeg (joins picture and sound) and Deno (needed for YouTube), about 70 MB in total. It happens once, in the background, right after you first open the app. |
| Only audio downloads work | ffmpeg couldn't be set up — usually no internet at first launch. Restart Veloce while online, or install ffmpeg yourself (section 8). |
| "Single connection" on a file | That server doesn't allow split downloads. Veloce still downloads it, at normal speed. |
| A download says **Failed** | The reason is shown under its name. Press **Try again**. While the app stays open, it continues from where it stopped; after a restart it starts over. |
| Port 9229 already in use | Another copy of Veloce is running (check the tray), or another program uses that port. |
| Where's the log? | `~/.veloce/engine.log` when started at login. |

Still stuck? [Open an issue](https://github.com/Firojpaudel/veloce/issues) with what you clicked, what you expected, and the last lines of the log.

---

## 10. Uninstall

1. Tray icon → turn off **Start at login**, then **Quit Veloce** (or run `veloce autostart disable`).
2. Delete the app file you downloaded.
3. Remove the extension at `chrome://extensions`.
4. Optional: delete `~/.veloce` (history, logs, yt-dlp updates). Your downloaded files in `~/Downloads/veloce` are yours — keep or delete them.

---

<sub>[← Back to the README](../README.md)</sub>
