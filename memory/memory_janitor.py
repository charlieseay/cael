import json
import os
import sys
import time
import fcntl
from datetime import datetime, timezone

memory_dir = sys.argv[1] if len(sys.argv) > 1 else "."
turns_path = os.path.join(memory_dir, "conversation-turns.json")
episodes_path = os.path.join(memory_dir, "conversation-episodes.json")
persona_path = os.path.join(memory_dir, "persona-profile.json")
status_path = os.path.join(memory_dir, "memory-health.json")
lock_path = os.path.join(memory_dir, "memory-janitor.lock")

MAX_RAW_TURNS = 240
COMPRESS_CHUNK_SIZE = 120
SLEEP_SECONDS = 300
MAX_DIR_BYTES = 500 * 1024 * 1024  # 500 MB hard ceiling

try:
    lock_fp = open(lock_path, "w", encoding="utf-8")
    fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
except Exception:
    # Another janitor instance is already active for this memory directory.
    sys.exit(0)

def load_json(path, fallback):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return fallback

def save_json(path, value):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(value, f, indent=2, sort_keys=True)
    os.replace(tmp, path)

def dir_size_bytes(path):
    total = 0
    for entry in os.scandir(path):
        try:
            total += entry.stat().st_size
        except Exception:
            pass
    return total

def trim_episodes_for_size():
    """Drop oldest episodes until directory is under the 500 MB ceiling."""
    while dir_size_bytes(memory_dir) > MAX_DIR_BYTES:
        episodes = load_json(episodes_path, [])
        if not isinstance(episodes, list) or not episodes:
            break
        episodes.pop(0)
        save_json(episodes_path, episodes)

def mark_status(last_compact=None):
    payload = load_json(status_path, {})
    payload["mode"] = "subprocess"
    payload["lastRunAt"] = datetime.now(timezone.utc).isoformat()
    if last_compact is not None:
        payload["lastCompactAt"] = last_compact
    save_json(status_path, payload)

def compact_once():
    turns = load_json(turns_path, [])
    if not isinstance(turns, list):
        turns = []
    if len(turns) <= MAX_RAW_TURNS:
        mark_status()
        return

    chunk = turns[:COMPRESS_CHUNK_SIZE]
    remaining = turns[COMPRESS_CHUNK_SIZE:]

    # Trivial queries not worth archiving — filter them out of the episode summary
    _TRIVIAL = {"what time is it", "what's the time", "time", "hello", "hi", "hey cael"}
    user_turns = [t.get("content", "").strip() for t in chunk if t.get("role") == "user"]
    substantive = [u for u in user_turns if u.lower() not in _TRIVIAL and len(u) > 10]
    # Pick up to 5 unique substantive user turns for the episode summary
    seen = set()
    highlights = []
    for u in substantive:
        key = u[:60].lower()
        if key not in seen:
            seen.add(key)
            highlights.append(u[:120])
        if len(highlights) >= 5:
            break

    highlights_str = " | ".join(highlights) if highlights else "(only trivial queries)"
    episode = {
        "id": f"ep-{int(time.time()*1000)}",
        "summary": f"Archive of {len(user_turns)} user turns ({len(substantive)} substantive). Topics: {highlights_str}.",
        "turnCount": len(chunk),
        "start": chunk[0].get("timestamp") if chunk else datetime.now(timezone.utc).isoformat(),
        "end": chunk[-1].get("timestamp") if chunk else datetime.now(timezone.utc).isoformat(),
    }
    episodes = load_json(episodes_path, [])
    if not isinstance(episodes, list):
        episodes = []
    episodes.append(episode)
    episodes = episodes[-200:]
    save_json(episodes_path, episodes)
    save_json(turns_path, remaining)

    # Update persona: track substantive turn rate, not raw turn count
    persona = load_json(persona_path, {
        "traits": {},
        "preferences": {},
        "summary": "No stable persona yet.",
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    })
    traits = persona.get("traits", {}) if isinstance(persona.get("traits"), dict) else {}
    traits["total_episodes"] = len(episodes)
    traits["recent_substantive_turns"] = len(substantive)
    persona["traits"] = traits
    prefs = persona.get("preferences") or {}
    pref_count = len([k for k in prefs if k != "last_stated_preference"])
    persona["summary"] = (
        f"{len(episodes)} archived episodes, {pref_count} documented preferences. "
        f"Recent topics: {highlights_str[:200]}."
    )
    persona["updatedAt"] = datetime.now(timezone.utc).isoformat()
    save_json(persona_path, persona)
    mark_status(last_compact=datetime.now(timezone.utc).isoformat())
    trim_episodes_for_size()

while True:
    try:
        compact_once()
    except Exception:
        pass
    time.sleep(SLEEP_SECONDS)