# ambient-room

Ambient music for the room, controlled from a phone. A synthesis engine
runs on the practice recorder's control unit (the Pi 3) and plays through
the room's speakers. Start with `PLAN.md`.

- **Shared hardware.** This project uses the hardware of
  `~/play/piano-recorder`: the Pi 3, the mixer's USB playback, the
  speakers.
  - Hardware facts live in that project's `docs/components.md`. Record new
    ones there, in the slot's entry, with the date. Don't copy them here.
  - **Don't break the recorder.** Any change to the Pi's audio setup
    re-runs the recorder's tests (T6 and T9 at least) and goes in its swap
    log.
- **Modular.** The engine, the output, the conductor and the page are
  separate parts.
  - The config picks the engine and the output device.
  - Never hard-code a device, card id or address in code.
- **No site details in git.** This install's details go in
  `local/README.md` (untracked), never in tracked files: addresses,
  network names, MAC addresses, user names, keys.
  - Tracked files use placeholders (`@USER@`, `@APP@` in the unit) or
    plain words ("the Pi", "the home Wi-Fi", `practice.local`).
  - The shared network facts live in piano-recorder's `local/README.md`.
- **For people who know nothing about synths.** The page uses plain words
  and no synth jargon. Every setting must sound acceptable, and changes
  glide.
- **Desktop testing:** `tools/desktop` runs the service here with
  `config/desktop.toml` (sound through the desktop's speakers, page on
  port 8001). The venv must come from Debian's Python, with system
  packages, so it sees `python3-csound`:
  `/usr/bin/python3 -m venv --system-site-packages .venv`. The `python3`
  on this desktop's PATH is Miniconda's, which does not see it.
- Docs here are plain: short sentences, measured numbers with units, no
  marketing.
