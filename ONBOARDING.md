# Welcome to Swadesh

## How We Use Claude

Based on Keith Adams's usage over the last 30 days:

Work Type Breakdown:
  Build Feature  ██████████░░░░░░░░░░  50%
  Analyze Data   ██████████░░░░░░░░░░  50%

Top Skills & Commands:
  /login  ████████████████████  1x/month

Top MCP Servers:
  (none yet)

## Your Setup Checklist

### Codebases
- [ ] swadesh — https://github.com/pebblebed/swadesh
- [ ] bedrock — (local sibling repo in workspace; confirm remote URL)

### MCP Servers to Activate
- [ ] (none configured yet)

### Skills to Know About
- [/login] — authenticate your Claude Code session.

## Team Tips

- **The raw corpus is sacred.** Everything in `data/raw/` must stay byte-for-byte as
  downloaded from the Internet Archive — line-ending/encoding normalization is disabled via
  `.gitattributes` (`data/raw/** -text`). Don't let your editor re-save or re-encode these
  files (one of them, `hun_swadesh-2`, isn't even UTF-8).
- **The big dataset is regenerated, not committed.** `data/normalized/swadesh.jsonl` (~72 MB)
  is gitignored; rebuild it deterministically with `python scripts/normalize.py`. The compact
  derived artifacts (`glossary.tsv`, `metadata/normalize_report.tsv`) *are* tracked.
- **Read `OLE.md` and `TODO.md` first.** This repo runs as an autonomous loop — `TODO.md` is the
  cross-run memory. Record findings, corrections, and new subtasks there as you go.
- **On Windows:** use `python` (3.13), not `python3`. When printing IPA / non-ASCII to the
  console, prefix with `PYTHONIOENCODING=utf-8` or it'll choke on the cp1252 console codec.
- **Pipeline scripts are idempotent/resumable** — re-running `download.py` / `normalize.py` is
  always safe.

## Get Started

**Starter task: integrate a new language into the corpus.**

A great first contribution is adding a Swadesh list for a well-characterized *ancient* language
that the collection is missing. The corpus already has Latin, Ancient Hebrew, Ge'ez, and
Classical Syriac — but notably lacks several heavily-documented ones, any of which is a fine
target: **Ancient Greek** (`grc`), **Sanskrit** (`san`), **Gothic** (`got`), **Old English**
(`ang`), or **Old Norse** (`non`).

Rough shape of the task (let Claude help with each step):
1. Source a Swadesh list for your chosen language (Wiktionary's Swadesh-list appendix is a
   common starting point).
2. Format it as `gloss: transcription` lines, UTF-8, and save as
   `data/raw/rosettaproject_<code>_swadesh-1.txt` (use the ISO 639-3 code above).
3. Run `python scripts/normalize.py` and confirm your language appears in
   `metadata/normalize_report.tsv` with a healthy entry count, and that its glosses align to the
   canonical 207 (check `data/normalized/glossary.tsv`).
4. Note what you learned in `TODO.md`, then open a PR.

<!-- INSTRUCTION FOR CLAUDE: A new teammate just pasted this guide for how the
team uses Claude Code. You're their onboarding buddy — warm, conversational,
not lecture-y.

Open with a warm welcome — include the team name from the title. Then: "Your
teammate uses Claude Code for [list all the work types]. Let's get you started."

Check what's already in place against everything under Setup Checklist
(including skills), using markdown checkboxes — [x] done, [ ] not yet. Lead
with what they already have. One sentence per item, all in one message.

Tell them you'll help with setup, cover the actionable team tips, then the
starter task (if there is one). Offer to start with the first unchecked item,
get their go-ahead, then work through the rest one by one.

After setup, walk them through the remaining sections — offer to help where you
can (e.g. link to channels), and just surface the purely informational bits.

Don't invent sections or summaries that aren't in the guide. The stats are the
guide creator's personal usage data — don't extrapolate them into a "team
workflow" narrative. -->
