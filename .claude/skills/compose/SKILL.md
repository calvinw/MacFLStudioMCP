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
  {channel: 0, pattern: 1, notes: [...]},
  {channel: 1, pattern: 1, notes: [...]},
])
```

**Options:**
- Pass all writes as a single list
- `clear_first=True` (default) — clears pattern before writing
- `restore_start=False` (default) — FL stays on the last edited pattern. Do not pass `restore_start=True` unless you have a specific reason to jump back to the original pattern.

**Why**: Singular calls fire separate Cmd+Opt+Y keystrokes per write. They race and corrupt the file bus. Plural is atomic.

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
     {channel: 0, pattern: 1, notes: [
       {midi: 36, time_bars: 0, duration_bars: 4, velocity: 0.8},
     ]},
     {channel: 1, pattern: 1, notes: [
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
- `restore_start=False` (default) — FL stays wherever the last write/read left it. No visible jumping back.
- `restore_start=True` — explicitly pass this only if you need FL to return to the original pattern after the operation.
- After a successful write, do not re-read patterns unless you want to verify the result or make additional changes.

### No parallel piano roll writes
Piano-roll writes share a single file bus (`fLMCP_request.json`) and one `Cmd+Opt+Y` hotkey. **Calling multiple `piano_roll_write_pattern` (singular) in a loop will race and corrupt the bus.** Always use `piano_roll_write_patterns` (plural) with all writes in a single list.

### Full sweep vs. targeted reads
- **Before any edit session** — always do a full sweep: `fl_piano_roll_read_patterns_autolocate()` with no args.
- **After edits** — only re-read the patterns you changed, or re-read all if something looks wrong.
- **No need to re-read** if the write returned `ok=True` with the expected `note_count`.

---

**Remember**: Read → Plan → Write (plural) → Confirm. This workflow is mandatory, not optional.
