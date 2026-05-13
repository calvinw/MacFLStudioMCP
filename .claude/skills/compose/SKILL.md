---
name: compose
description: Guide through the mandatory FL Studio piano roll composition workflow (read → plan → write → confirm)
---

# FL Studio Piano Roll Compose Workflow

You are guiding a composition session in FL Studio. Follow this **mandatory workflow** from CLAUDE.md:

## The Workflow (Non-Negotiable Order)

### 1️⃣ READ — Full sweep before any edits

**Always read first**, even if you think you know the state. This is mandatory at the start of every edit session.

```
fl_piano_roll_read_patterns_autolocate()
```

**Options:**
- Call with no arguments to read all patterns
- Pass `navigate_after_pattern=<index>` if you know which pattern will be edited first
- Optionally pass `navigate_after_channel=<index>` — FL will land on the edit target immediately after the sweep, so the UI shows the right pattern while you plan

**Returns:** current note state for every pattern

**Why**: Skipping the read means composing from stale/imagined state. After the read, FL lands on your target pattern (if specified), ready for editing.

### 2️⃣ PLAN — Derive notes from the read data

Analyze the data you just read. Never invent from memory or prior sessions.

- What notes exist in each pattern?
- What needs to change?
- Where should new notes go?
- What timing and velocity?

**Keep this in your reasoning** — show the user what you found and what you're planning to do.

### 3️⃣ WRITE — Use `piano_roll_write_patterns` (PLURAL)

**Critical**: Always use the PLURAL version. Never call the singular version in a loop.

```
fl_piano_roll_write_patterns(writes=[
  {channel: 0, pattern: 1, current_note_count: 16, notes: [...]},
  {channel: 1, pattern: 2, current_note_count: 0,  notes: [...]},
])
```

**Options:**
- Pass all writes as a single list
- `clear_first=True` (default) — clears pattern before writing
- `restore_start=False` (default) — **leave this as default on writes** so FL stays on the pattern that was just edited, even if the user was viewing a different pattern before.
- `current_note_count` — **always pass this from the read sweep**. It tells the write tool whether the piano roll viewport needs a `force_retarget` call:
  - `> 0` → `patterns.select` is sufficient, no flicker
  - `0` or omitted → `force_retarget` is called to move the piano roll to the correct (empty) channel

**Why**: Singular calls fire separate Cmd+Opt+Y keystrokes per write. They race and corrupt the file bus. Plural is atomic.

**Why `current_note_count` matters**: FL's `patterns.select` (jumpToPattern) only retargets the piano roll viewport when the target pattern has notes. For empty patterns, the piano roll stays on whatever channel was last open. There is no FL API to check note count without opening the piano roll — the read sweep is the only source of truth.

### 4️⃣ CONFIRM — Read again if uncertain

Call `fl_piano_roll_read_patterns_autolocate()` again if anything looks wrong or you want to verify the write succeeded.

## Tools Available

### Piano Roll
- `fl_piano_roll_read_patterns_autolocate` — read all patterns (or specific ones)
- `fl_piano_roll_write_patterns` — write notes to channels (plural!)


## Example Session

```
User: "Add a C major chord progression to the Chords pattern"

1. READ:
   fl_piano_roll_read_patterns_autolocate()
   → Found 4 channels, "Chords" pattern at index 1

2. PLAN:
   "I'll add C-E-G to channel 0 (bass) at bar 1,
    then add a melody over it in channel 1"

3. WRITE:
   fl_piano_roll_write_patterns(writes=[
     {channel: 0, pattern: 1, current_note_count: 16, notes: [
       {midi: 36, time_bars: 0, duration_bars: 4, velocity: 0.8},
     ]},
     {channel: 1, pattern: 2, current_note_count: 0, notes: [
       {midi: 60, time_bars: 0, duration_bars: 1, velocity: 0.8},
       {midi: 64, time_bars: 1, duration_bars: 1, velocity: 0.8},
       {midi: 67, time_bars: 2, duration_bars: 1, velocity: 0.8},
     ]},
   ])

4. CONFIRM:
   ✓ Write returned ok=True, wrote 4 notes
   Done!
```

---

## Critical Details

### `restore_start` behavior
- **Reads: always pass `restore_start=True`** — after sweeping patterns to collect notes, FL must return to whatever pattern the user was viewing before. Never leave the user on a different pattern just because a read swept through it.
- **Writes: leave `restore_start=False` (default)** — after editing a pattern, FL should stay on the pattern that was just edited, even if the user was on a different one when they made the request. The edit target is where the user's attention should go.
- After a successful write, do not re-read patterns unless you want to verify the result or make additional changes.

### No parallel piano roll writes
Piano-roll writes share a single file bus (`fLMCP_request.json`) and one `Cmd+Opt+Y` hotkey. **Calling multiple `piano_roll_write_pattern` (singular) in a loop will race and corrupt the bus.** Always use `piano_roll_write_patterns` (plural) with all writes in a single list.

### Full sweep vs. targeted reads
- **Before any edit session** — always do a full sweep: `fl_piano_roll_read_patterns_autolocate()` with no args.
- **After edits** — only re-read the patterns you changed, or re-read all if something looks wrong.
- **No need to re-read** if the write returned `ok=True` with the expected `note_count`.

---

**Remember**: Read → Plan → Write (plural) → Confirm. This workflow is mandatory, not optional.
