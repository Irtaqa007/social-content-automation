#!/usr/bin/env python3
"""Pre-production package generator for 30-60s cinematic construction-site security promos.

Follows a real filmmaking workflow instead of one big prompt:
  logline -> look/style lock -> character & location bibles -> timed shot list
  -> per-shot still-frame prompts (image model) -> per-shot video prompts
  (image-to-video, <=8s each) -> sound plan -> edit & post checklist.

Uses the Gemini API (stdlib only).

Setup:
    export GEMINI_API_KEY="your-key"          # https://aistudio.google.com/apikey
    export GEMINI_MODEL="gemini-2.5-pro"      # optional override

Usage:
    python crime_scene_prompt.py                      # interactive
    python crime_scene_prompt.py "night copper theft" # idea on the command line
    python crime_scene_prompt.py --dry-run            # show instructions, no API call
"""
import argparse
import json
import math
import os
import random
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

DEFAULT_MODEL = "gemini-2.5-pro"
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
OUT_DIR = Path("generated_prompts")
CONFIG_FILE = Path("brand.json")
MAX_SHOT_SECONDS = 8  # current video models generate clips of about this length

MOODS = [
    ("Cold Fincher precision", "desaturated teal-grey, clinical symmetry, slow deliberate push-ins, silence between sounds"),
    ("Rain-soaked neo-noir", "wet asphalt reflections, sodium-orange vs cyan, hard backlight through rain, low brooding score"),
    ("Michael Mann night city", "anamorphic flares, deep blue shadows, floodlight halos, throbbing synth bass, handheld tension"),
    ("Bleak Nordic procedural", "overcast flat light, muted greens and greys, long static wides, sparse ambient sound"),
    ("Pre-dawn blue-hour thriller", "cold blue ambient with warm work-light pockets, mist, rising low strings"),
    ("High-contrast tactical realism", "strobing red/blue emergency light, bodycam-style handheld, tight breathing and radio chatter"),
    ("Golden-hour tension", "long amber shadows, dust in the air, slow telephoto compression, uneasy quiet"),
    ("Storm-front dread", "heavy clouds, wind, flickering floodlights, low thunder rumble, claustrophobic framing"),
]

INCIDENTS = [
    "after-hours copper/cable theft",
    "equipment or fuel theft from a gated yard",
    "trespass and vandalism by a group",
    "attempted excavator/skid-steer theft",
    "perimeter fence breach at night",
    "daytime tool theft by an impostor in a hi-vis vest",
]

SYSTEM_INSTRUCTIONS = """You are a veteran film director, cinematographer and AI-video prompt engineer producing a {duration}-second dramatized short for a construction-site security company.

Produce a complete PRE-PRODUCTION PACKAGE as JSON only (no markdown fences, no commentary).

FILMMAKING RULES
- Three-act economy: setup (quiet, ominous), escalation (intrusion, detection, response), resolution (lawful arrest, calm), then a branded end card.
- Required beats in order: establishing, intrusion on client monitoring cameras, control-room detection and verified alert, response arrival, confrontation, lawful arrest, calm aftermath. The end card is built in post, NOT generated.
- Vary shot size and angle (wide, medium, close-up, insert, OTS, high CCTV POV, drone). Obey the 180-degree rule and keep screen direction consistent. Motivate every camera move. Cut on action.
- Every shot is {max_shot} seconds or less. Shot durations must sum to exactly {duration}. Timecodes must be contiguous.
- Fictional dramatization only: invented actors, no real people, no real police/agency insignia, badge numbers or brands other than the client. Competent, lawful response; no gore, no gunfire, no weapons drawn.
- AI-video limits: generated frames must contain NO readable text, logos or signage (describe signs as blank/blurred). Titles, the DRAMATIZATION tag, camera timestamps and the end card are added in post.
- CONTINUITY: write ONE style_lock paragraph (look, lens language, grade, lighting, grain, aspect ratio) and fixed character/location descriptions. Every still_prompt and video_prompt MUST begin by pasting the style_lock and MUST restate, word for word, the full description of every character or location element in that shot. Never use pronouns or "same as before".
- still_prompt: a single frame for an image model (composition, lens, light, subject, wardrobe, location). video_prompt: for image-to-video from that still (one camera move, subject action beat by beat, ambient motion, audio cues). Keep each under 120 words.

JSON SCHEMA (all keys required)
{{
 "title": str, "logline": str,
 "format": {{"aspect_ratio": str, "fps": int, "resolution": str, "lens_package": str}},
 "style_lock": str,
 "characters": [{{"id": str, "role": str, "description": str, "wardrobe": str}}],
 "location": {{"description": str, "fixed_elements": [str]}},
 "shots": [{{"n": int, "start": float, "end": float, "duration": float, "beat": str,
            "shot_size": str, "angle": str, "lens": str, "movement": str,
            "characters": [str], "action": str, "lighting": str,
            "still_prompt": str, "video_prompt": str, "sound": str, "transition": str}}],
 "audio": {{"score": str, "ambience": str, "sfx": [str], "radio_chatter": [str], "voiceover": [str]}},
 "negative_prompt": str,
 "post_notes": [str]
}}
"""


def load_brand():
    defaults = {"company": "", "phone": "", "website": "", "email": "", "tagline": ""}
    if CONFIG_FILE.exists():
        try:
            defaults.update(json.loads(CONFIG_FILE.read_text()))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Warning: could not read {CONFIG_FILE}: {exc}", file=sys.stderr)
    return defaults


def ask(label, default="", required=False):
    suffix = f" [{default}]" if default else ""
    while True:
        value = input(f"{label}{suffix}: ").strip() or default
        if value or not required:
            return value
        print("  This one is required.")


def choose(label, options):
    print(f"\n{label}")
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {opt if isinstance(opt, str) else opt[0]}")
    while True:
        raw = input("Choose (number, or Enter for a surprise): ").strip()
        if not raw:
            return random.choice(options)
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        print("  Invalid choice.")


def gather(idea_arg):
    print("\n=== Cinematic Site-Security Pre-Production Builder ===\n")
    brand = load_brand()
    idea = idea_arg or ask("1. Your idea / what should happen", required=True)
    incident = choose("2. Incident type:", INCIDENTS)
    mood = choose("3. Mood (new one each run if you press Enter):", MOODS)
    duration = ask("4. Length in seconds (30-60)", "45")
    while not (duration.isdigit() and 30 <= int(duration) <= 60):
        duration = ask("   Must be 30-60", "45")
    location = ask("5. Site type / location feel", "mid-rise apartment construction site, tower crane, city outskirts")
    time_of_day = ask("6. Time of day / weather", "2:47 AM, light drizzle")
    suspects = ask("7. Number and type of intruders", "two men in dark clothing")
    response = ask("8. Response style (guards, patrol vehicle, drone, police)", "mobile patrol unit plus police")
    aspect = ask("9. Aspect ratio (9:16 social, 16:9 web)", "16:9")
    print("\nBrand details for the end card (saved to brand.json for next time):")
    brand["company"] = ask("10. Company name", brand["company"], required=True)
    brand["phone"] = ask("    Phone", brand["phone"])
    brand["website"] = ask("    Website", brand["website"])
    brand["email"] = ask("    Email", brand["email"])
    brand["tagline"] = ask("    Sales line / tagline", brand["tagline"])
    try:
        CONFIG_FILE.write_text(json.dumps(brand, indent=2))
    except OSError:
        pass
    return {"idea": idea, "incident": incident, "mood": mood, "duration": int(duration),
            "location": location, "time": time_of_day, "suspects": suspects,
            "response": response, "aspect": aspect, "brand": brand}


def build_meta_prompt(d):
    mood_name, mood_look = d["mood"]
    system = SYSTEM_INSTRUCTIONS.format(duration=d["duration"], max_shot=MAX_SHOT_SECONDS)
    min_shots = math.ceil(d["duration"] / MAX_SHOT_SECONDS)
    brief = f"""BRIEF
Idea: {d['idea']}
Incident type: {d['incident']}
Mood: {mood_name} - {mood_look}
Duration: {d['duration']} seconds (use at least {min_shots} shots, ideally {min_shots + 2}-{min_shots + 4})
Aspect ratio: {d['aspect']}
Location: {d['location']}
Time/weather: {d['time']}
Intruders: {d['suspects']}
Response: {d['response']}
"""
    return system, brief


def call_gemini(system, brief, model, key):
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": brief}]}],
        "generationConfig": {"temperature": 0.9, "maxOutputTokens": 16384,
                             "responseMimeType": "application/json"},
    }
    req = urllib.request.Request(
        API_URL.format(model=model), data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        sys.exit(f"Gemini API error {exc.code}: {exc.read().decode(errors='replace')[:500]}")
    except urllib.error.URLError as exc:
        sys.exit(f"Network error: {exc.reason}")
    try:
        text = "".join(p["text"] for p in data["candidates"][0]["content"]["parts"]).strip()
    except (KeyError, IndexError):
        sys.exit(f"Unexpected response (possibly blocked): {json.dumps(data)[:500]}")
    text = text.removeprefix("```json").removesuffix("```").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        sys.exit(f"Model returned invalid JSON ({exc}). Run again.\n{text[:400]}")


def validate(pkg, duration):
    """Return a list of problems with the package so the user can fix or rerun."""
    issues = []
    for key in ("title", "style_lock", "characters", "location", "shots", "audio"):
        if key not in pkg:
            issues.append(f"missing '{key}'")
    shots = pkg.get("shots", [])
    total = sum(float(s.get("duration", 0)) for s in shots)
    if abs(total - duration) > 0.6:
        issues.append(f"shot durations sum to {total:.1f}s, expected {duration}s")
    for s in shots:
        if float(s.get("duration", 0)) > MAX_SHOT_SECONDS:
            issues.append(f"shot {s.get('n')} is longer than {MAX_SHOT_SECONDS}s")
        for k in ("still_prompt", "video_prompt"):
            if pkg.get("style_lock", "")[:40] not in s.get(k, ""):
                issues.append(f"shot {s.get('n')} {k} does not start with the style lock")
    return issues


def tc(sec):
    sec = float(sec)
    return f"{int(sec // 60):02d}:{sec % 60:04.1f}"


def write_package(pkg, d, folder):
    folder.mkdir(parents=True, exist_ok=True)
    b = d["brand"]
    shots = pkg["shots"]
    (folder / "package.json").write_text(json.dumps(pkg, indent=2))

    lines = [f"# {pkg['title']}", "", f"**Logline:** {pkg['logline']}", "",
             f"**Format:** {pkg['format']}", "", "## Style lock (pasted into every prompt)", pkg["style_lock"], "",
             "## Characters (fixed descriptions)"]
    lines += [f"- **{c['id']}** ({c['role']}): {c['description']} Wardrobe: {c['wardrobe']}" for c in pkg["characters"]]
    lines += ["", "## Location", pkg["location"]["description"], ""]
    lines += [f"- {e}" for e in pkg["location"]["fixed_elements"]]
    lines += ["", "## Negative prompt", pkg["negative_prompt"]]
    (folder / "1_bible.md").write_text("\n".join(lines) + "\n")

    sl = ["# Shot list", "", "| # | TC | Dur | Beat | Size / angle | Lens | Move | Action |", "|---|---|---|---|---|---|---|---|"]
    for s in shots:
        sl.append(f"| {s['n']} | {tc(s['start'])}-{tc(s['end'])} | {s['duration']}s | {s['beat']} | "
                  f"{s['shot_size']} / {s['angle']} | {s['lens']} | {s['movement']} | {s['action']} |")
    (folder / "2_shot_list.md").write_text("\n".join(sl) + "\n")

    (folder / "3_still_prompts.txt").write_text("\n\n".join(
        f"=== SHOT {s['n']} ({s['beat']}) ===\n{s['still_prompt']}" for s in shots) + "\n")
    (folder / "4_video_prompts.txt").write_text("\n\n".join(
        f"=== SHOT {s['n']} ({s['duration']}s) - animate still {s['n']} ===\n{s['video_prompt']}\nSOUND: {s['sound']}"
        for s in shots) + "\n")

    a = pkg["audio"]
    sound = ["# Sound plan", f"- Score: {a['score']}", f"- Ambience: {a['ambience']}",
             "- SFX: " + "; ".join(a["sfx"]), "- Radio chatter: " + "; ".join(a["radio_chatter"]),
             "- Voice-over: " + " / ".join(a["voiceover"]), "", "## Per-shot sound"]
    sound += [f"- Shot {s['n']}: {s['sound']}" for s in shots]
    (folder / "5_sound_plan.md").write_text("\n".join(sound) + "\n")

    post = ["# Edit & post checklist", "",
            "1. Generate one still per shot from 3_still_prompts.txt. Pick the best take; keep faces/wardrobe consistent (reuse a reference image of each character).",
            "2. Animate each approved still with its video prompt (image-to-video). Generate 2-3 takes per shot.",
            "3. Assemble in DaVinci Resolve / Premiere in the order of 2_shot_list.md; trim to the timecodes; cut on action.",
            "4. Colour: apply one grade across all shots; add subtle film grain for matching.",
            "5. Sound: build from 5_sound_plan.md (licensed score, foley, radio chatter, room tone). Mix dialogue/VO over score; master to -14 LUFS.",
            "6. Add in post (never generate in AI video): 'DRAMATIZATION' tag at start and end, camera timestamp/ID overlays on CCTV shots.",
            "7. Build the end card as real text:",
            f"   - {b['company']}", f"   - {b['phone']}", f"   - {b['website']}", f"   - {b['email']}", f"   - \"{b['tagline']}\"",
            "8. QC: check for garbled text, morphing faces, continuity breaks, logos. Confirm no real police insignia.",
            "9. Export: H.264, platform-specific crops (16:9 web, 9:16 social, 1:1 feed), burned-in captions.", ""]
    post += [f"- {n}" for n in pkg.get("post_notes", [])]
    (folder / "6_edit_and_post.md").write_text("\n".join(post) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("idea", nargs="?", help="short idea (skips the first question)")
    ap.add_argument("--model", default=os.environ.get("GEMINI_MODEL", DEFAULT_MODEL))
    ap.add_argument("--dry-run", action="store_true", help="print the instructions instead of calling the API")
    args = ap.parse_args()

    key = os.environ.get("GEMINI_API_KEY")
    if not key and not args.dry_run:
        sys.exit("Set GEMINI_API_KEY first (https://aistudio.google.com/apikey), or use --dry-run.")

    d = gather(args.idea)
    system, brief = build_meta_prompt(d)
    if args.dry_run:
        print("\n----- SYSTEM -----\n" + system + "\n----- BRIEF -----\n" + brief)
        return

    print(f"\nMood this run: {d['mood'][0]}\nGenerating package with {args.model}...\n")
    pkg = call_gemini(system, brief, args.model, key)
    issues = validate(pkg, d["duration"])
    if issues:
        print("Quality check found problems (rerun, or fix package.json by hand):")
        for i in issues:
            print(f"  - {i}")
    folder = OUT_DIR / f"{datetime.now():%Y%m%d_%H%M%S}_{pkg.get('title', 'untitled')[:30].replace(' ', '_').replace('/', '-')}"
    write_package(pkg, d, folder)
    print(f"Title: {pkg['title']}\nLogline: {pkg['logline']}\nShots: {len(pkg['shots'])}\n\nSaved to {folder}/")
    print("Next: follow 6_edit_and_post.md (stills -> image-to-video -> edit -> sound -> end card).")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        sys.exit("\nCancelled.")
