#!/usr/bin/env python3
"""Turn a short idea into a 30-60 second cinematic video-generation prompt.

Built for construction-site security promos: a dramatized incident, the
monitoring/response, the arrest, then a branded call to action.

Uses the Gemini API (stdlib only, no dependencies).

Setup:
    export GEMINI_API_KEY="your-key"          # https://aistudio.google.com/apikey
    export GEMINI_MODEL="gemini-2.5-pro"      # optional override

Usage:
    python crime_scene_prompt.py                      # interactive
    python crime_scene_prompt.py "night copper theft" # idea on the command line
    python crime_scene_prompt.py --dry-run            # print the meta-prompt, no API call
"""
import argparse
import json
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

# A fresh mood is drawn every run unless the user picks one.
MOODS = [
    ("Cold Fincher precision", "desaturated teal-grey, clinical symmetry, slow deliberate push-ins, silence between sounds"),
    ("Rain-soaked neo-noir", "wet asphalt reflections, sodium-orange vs cyan, hard backlight through rain, low brooding score"),
    ("Michael Mann night city", "anamorphic flares, deep blue shadows, floodlight halos, throbbing synth bass, handheld tension"),
    ("Bleak Nordic procedural", "overcast flat light, muted greens and greys, long static wides, sparse ambient sound"),
    ("Pre-dawn blue-hour thriller", "cold blue ambient with warm work-light pockets, mist, rising low strings"),
    ("High-contrast tactical realism", "strobing red/blue emergency light, bodycam-style handheld, tight breathing and radio chatter"),
    ("Golden-hour tension", "long amber shadows, dust in the air, slow telephoto compression, uneasy quiet"),
    ("Storm-front dread", "heavy clouds, wind, flickering floodlights, thunder-low rumble, claustrophobic framing"),
]

INCIDENTS = [
    "after-hours copper/cable theft",
    "equipment or fuel theft from a gated yard",
    "trespass and vandalism by a group",
    "attempted excavator/skid-steer theft",
    "perimeter fence breach at night",
    "daytime tool theft by an impostor in a hi-vis vest",
]

SYSTEM_INSTRUCTIONS = """You are an award-winning film director and prompt engineer for AI video generators (Veo, Sora, Runway, Kling).
Convert the user's brief into ONE production-ready video-generation prompt for a {duration}-second cinematic, dramatized construction-site security incident that ends with a branded call to action.

HARD RULES
- Entirely fictional dramatization: invented actors, no real people, no real police/agency insignia or badge numbers, no real brands other than the client's.
- Include a small on-screen lower-third "DRAMATIZATION" in the opening seconds and the closing frame.
- Show monitoring and response competently and lawfully: detection, verified alert, dispatch, lawful arrest with no gratuitous violence, no gore, no weapons brandished by the good guys.
- Feel real: practical lighting, believable site details (hoarding, cranes, scaffolding, site cabins, PPE, heavy plant), plausible CCTV/thermal/drone and control-room UI.
- No text artifacts: specify that all on-screen text other than the listed overlays must be avoided or blurred.
- Output ONLY the final prompt, no preamble, no markdown fences.

STRUCTURE THE OUTPUT EXACTLY AS
TITLE: <short punchy title>
FORMAT: <aspect ratio, {duration}s, frame rate, resolution>
STYLE & MOOD: <named mood, color grade, lens/film-stock language, lighting, reference tone without naming real films' IP>
SETTING: <location, weather, time, site details>
CHARACTERS: <each with age range, clothing, build, behavior - no real people>
SHOT LIST: <numbered shots with timecodes that sum to {duration}s; for each: camera angle, lens, movement, action, lighting, sound>
  Required beats in order: (1) quiet establishing shot, (2) the intrusion seen through the client's monitoring cameras, (3) control-room detection and verified alert, (4) response arrival and confrontation, (5) lawful arrest, (6) calm aftermath, (7) branded end card.
AUDIO: <score, ambience, SFX, radio chatter, any voice-over line (max 2 short lines)>
ON-SCREEN TEXT: <exact overlays: DRAMATIZATION tag, camera timestamp/ID overlays, and the end card with the client's company name, phone, website, email and tagline VERBATIM as supplied>
CONTINUITY & NEGATIVE PROMPT: <consistency notes; what to avoid: gore, gun fights, real logos, garbled text, extra limbs, morphing faces, shaky unreadable footage>
"""


def load_brand():
    """Brand details come from brand.json (if present) and are confirmed interactively."""
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


def choose(label, options, allow_random=True):
    print(f"\n{label}")
    for i, opt in enumerate(options, 1):
        text = opt if isinstance(opt, str) else opt[0]
        print(f"  {i}. {text}")
    hint = "number, or Enter for a surprise" if allow_random else "number"
    while True:
        raw = input(f"Choose ({hint}): ").strip()
        if not raw and allow_random:
            return random.choice(options)
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        print("  Invalid choice.")


def gather(idea_arg):
    print("\n=== Cinematic Site-Security Prompt Builder ===\n")
    brand = load_brand()
    idea = idea_arg or ask("1. Your idea / what should happen", required=True)
    incident = choose("2. Incident type:", INCIDENTS)
    mood = choose("3. Mood (a new one is picked every run if you press Enter):", MOODS)
    duration = ask("4. Length in seconds (30-60)", "45")
    while not (duration.isdigit() and 30 <= int(duration) <= 60):
        duration = ask("   Must be 30-60", "45")
    location = ask("5. Site type / location feel", "mid-rise apartment construction site, tower crane, city outskirts")
    time_of_day = ask("6. Time of day / weather", "2:47 AM, light drizzle")
    suspects = ask("7. Number and type of intruders", "two men in dark clothing")
    response = ask("8. Response style (guards, patrol vehicle, drone, police)", "mobile patrol unit plus police")
    print("\nBrand details for the end card (saved to brand.json for next time):")
    brand["company"] = ask("9. Company name", brand["company"], required=True)
    brand["phone"] = ask("   Phone", brand["phone"])
    brand["website"] = ask("   Website", brand["website"])
    brand["email"] = ask("   Email", brand["email"])
    brand["tagline"] = ask("   Sales line / tagline", brand["tagline"])
    try:
        CONFIG_FILE.write_text(json.dumps(brand, indent=2))
    except OSError:
        pass
    return {
        "idea": idea, "incident": incident, "mood": mood, "duration": int(duration),
        "location": location, "time": time_of_day, "suspects": suspects,
        "response": response, "brand": brand,
    }


def build_meta_prompt(d):
    mood_name, mood_look = d["mood"]
    b = d["brand"]
    brief = f"""BRIEF
Idea: {d['idea']}
Incident type: {d['incident']}
Mood: {mood_name} - {mood_look}
Duration: {d['duration']} seconds
Location: {d['location']}
Time/weather: {d['time']}
Intruders: {d['suspects']}
Response: {d['response']}
Client end card (use verbatim):
  Company: {b['company']}
  Phone: {b['phone']}
  Website: {b['website']}
  Email: {b['email']}
  Tagline: {b['tagline']}
"""
    return SYSTEM_INSTRUCTIONS.format(duration=d["duration"]), brief


def call_gemini(system, brief, model, key):
    url = API_URL.format(model=model)
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": brief}]}],
        "generationConfig": {"temperature": 1.0, "maxOutputTokens": 4096},
    }
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        sys.exit(f"Gemini API error {exc.code}: {exc.read().decode(errors='replace')[:500]}")
    except urllib.error.URLError as exc:
        sys.exit(f"Network error: {exc.reason}")
    try:
        return "".join(p["text"] for p in data["candidates"][0]["content"]["parts"]).strip()
    except (KeyError, IndexError):
        sys.exit(f"Unexpected response (possibly blocked): {json.dumps(data)[:500]}")


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

    print(f"\nMood this run: {d['mood'][0]}\nGenerating with {args.model}...\n")
    result = call_gemini(system, brief, args.model, key)
    print(result)

    OUT_DIR.mkdir(exist_ok=True)
    path = OUT_DIR / f"prompt_{datetime.now():%Y%m%d_%H%M%S}.txt"
    path.write_text(result + "\n")
    print(f"\nSaved to {path}")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        sys.exit("\nCancelled.")
