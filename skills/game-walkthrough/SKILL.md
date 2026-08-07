---
name: game-walkthrough
description: >-
  Tell the player exactly what to do and where to go next in a video game,
  from three inputs: a screenshot, the game name, and (optionally) the
  quest/mission name. Use when the user pastes a game screenshot and asks
  "where do I go", "what do I do next", "how do I progress <quest>", "I'm
  stuck", or names a mission they're on. Builds a persistent per-game
  knowledge base from online guides and quest videos — never answers game
  specifics from model memory.
allowed-tools: Bash, Read, Write, WebSearch, WebFetch
argument-hint: "<game name> [quest/mission name]"
---

# Game walkthrough — retrieve, don't recall

Answer one question: **"what is my next move in the quest I named?"** —
decisively, from retrieved evidence, scoped to that quest only.

## Hard rules (each one exists because violating it produced a wrong answer)

1. **Never answer game specifics from parametric memory.** LLMs are not
   trained on reliable game-specific datasets. Quest names, locations, item
   spots recalled from memory are hallucination-shaped. Every game fact in
   the answer must come from a retrieved source or the KB.
2. **Three inputs only: game, quest (optional), screenshot.** The quest the
   user names is the ONLY scope. Do not answer about the main story, treasure
   chests, completion %, or anything else visible on screen unless the user
   asked. (Failure mode: the screenshot shows collection counters and a
   main-story banner → you answer those because they're what you can see.
   That is answering the wrong question confidently.)
3. **Disambiguate hard before retrieving.** Editions and numerals matter:
   `Ys X: Proud Nordics` ≠ `Ys X: Nordics` (whole zones exist only in one);
   `... Investigation II` ≠ `... Investigation`. Also reject real-world
   noise — a search for "Öland investigation" returns Swedish archaeology
   and murder trials. State which exact game+quest you locked onto.
4. **Don't assume quest state.** "How do I progress X" may mean the quest
   isn't started yet and the user is walking to its trigger. Read the
   screenshot for what's actually happening (tracked-objective banner, map
   markers, player position) before prescribing steps.
5. **Decisive, single next move first.** Lead with "do this, go here", then
   the ordered beats. Confidence honesty is a floor, not a hedge: if sources
   genuinely can't resolve the step, say so and ask ONE sharp question.

## Pipeline

### 0. KB check (free)
Look for `${CLAUDE_SKILL_DIR}/kb/<game-slug>.md`. If the quest is already
recorded there, answer from it (still read the user's screenshot for their
position) and skip to step 4.

### 1. Read the screenshot
Extract: region/area name, the tracked-objective banner text, minimap/map
markers and player position, any counters. The banner tells you what the
GAME thinks the current objective is — which may differ from the quest the
user named (parallel quest lines); note the difference, answer the named one.

### 2. Text retrieval (cheap, often stale for new editions)
Search for `<exact game> <exact quest> walkthrough` (wiki/guide sites:
neoseeker, gamefaqs, ludo.guide, fandom, raiderking, steam guides). Targeted
page-lookups beat full fetches. Cross-check at least two sources. **Recent
enhanced-edition content is often missing or mislabeled in text guides** —
guide authors lag; note the guide's own disclaimers.

### 3. Video retrieval (the decisive source for new/undocumented quests)
Find the quest's dedicated video (search `<game> <exact quest name>` on
YouTube — full-quest no-commentary walkthroughs are common and are usually
titled with the exact quest string, which also confirms disambiguation).

**Do NOT trust captions/transcripts of no-commentary videos** — they are
in-game battle voice-lines ("fire and ice!", "let's make tracks!") and any
step sequence reconstructed from them is fabrication. **Read the frames
instead** — the HUD's objective banner, area-title cards, and menus on
screen are ground truth:

```bash
pip install -r ${CLAUDE_SKILL_DIR}/requirements.txt   # once
VS="${CLAUDE_SKILL_DIR}/scripts/videoscan.py"

python "$VS" probe  "<youtube-url>"              # confirm it's the right video
python "$VS" frames "<youtube-url>" --scenes --budget 9
```

`--scenes` finds the cuts first and samples just after each one, so the frame
budget lands on area transitions, cutscene starts and menu opens instead of on
nine identical shots of a corridor. It stream-seeks (no download) and saves
`_frames/f_<centiseconds>.jpg` plus a `frames.json` timestamp map.

Read every frame. Map the objective-banner text and area titles across
timestamps → that IS the quest's step sequence. Go back finer around a
transition you care about (`--times 15,40,65`), and when the banner is small,
crop and upscale it: `--crop hud --zoom 3`. Dialogue frames carry story beats;
menu frames carry unlocks/rewards.

Fuller method, other sampling modes, and the audio/caption ladder:
the **`video-understanding`** skill (it owns `videoscan.py`; this copy is
kept byte-identical). If the `claude-video-vision` plugin is installed, its
`video_watch` / `video_detail` MCP tools do the same job with inline frames —
use them and keep the rules above.

### 4. Answer
- **Lock line:** which exact game + quest you resolved (edition-precise).
- **Next move:** one imperative line for the user's current position.
- **The beats:** ordered steps with the evidence timestamp/source for each.
- **Scope guard:** nothing outside the named quest unless asked.
- Cite sources (guide URLs, video + timestamps). Flag anything the game
  gates behind later story/abilities so the user doesn't chase locked
  content — but only where it touches the named quest.

### 5. Persist to the KB (always, after user confirms or evidence is solid)
Append/update `${CLAUDE_SKILL_DIR}/kb/<game-slug>.md`:

```markdown
## <Exact Quest Name>
- verified: <date> | sources: <urls + video id w/ timestamps>
- start: <where/how the quest triggers>
- steps: <ordered beats>
- gates: <story/ability gates touching this quest>
- pitfalls: <disambiguation traps, wrong-source noise hit during research>
```

Plus a `# <Game>` header block with edition facts (what distinguishes this
edition, zone names, guide-site landscape). Commit the KB file to this repo
(`git add kb/ && git commit`) so knowledge persists and compounds across
sessions and machines. The KB is the product — each answered quest makes
the next one cheaper.

## Tooling notes
- `yt-dlp` + `imageio-ffmpeg` (bundled ffmpeg binary, no system install) —
  see `requirements.txt`. Frame extraction streams via HTTP range requests;
  ~9 frames across a 75-min video costs seconds, not a 700 MB download.
- `python scripts/videoscan.py analyze <url> --start 300 --duration 120` when
  you need to know where a long video's chapters actually break. Analyzing a
  whole URL streams the whole file — bound it.
- If a browser pane is available you can seek the video visually instead;
  the script path works headless.
- Clean up `_frames/` in the scratch dir when done.
