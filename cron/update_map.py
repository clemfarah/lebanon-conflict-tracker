#!/usr/bin/env python3
"""
Lebanon Conflict Tracker — Daily Map Updater
Sources: Al Jazeera, Reuters, BBC Middle East RSS feeds
Searches for new Israeli military events in Lebanon, updates the map HTML,
redeploys, and sends a notification summary.
"""

import json, re, subprocess, sys, os, datetime
import urllib.request, urllib.parse, html as htmllib
import xml.etree.ElementTree as ET

# ─── CONFIG ───
MAP_FILE        = "/home/user/workspace/lebanon-attacks-map/index.html"
LOG_FILE        = "/home/user/workspace/cron_tracking/lebanon-tracker/update_log.json"
SEARCH_DIR      = "/home/user/workspace/cron_tracking/lebanon-tracker"
MAP_URL         = "https://www.perplexity.ai/computer/a/lebanon-conflict-tracker-2026-YksfibPwQ9e87qNCoNqBxw"

TODAY_UTC       = datetime.datetime.now(datetime.timezone.utc)
TODAY           = TODAY_UTC.strftime("%Y-%m-%d")
TODAY_DISPLAY   = TODAY_UTC.strftime("%B %-d, %Y")

RSS_FEEDS = [
    ("Al Jazeera",  "https://www.aljazeera.com/xml/rss/all.xml"),
    ("Reuters",     "https://feeds.reuters.com/reuters/topNews"),
    ("BBC",         "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml"),
    ("Guardian",    "https://www.theguardian.com/world/middleeast/rss"),
]

KEYWORDS = ["lebanon","israel","hezbollah","beirut","idf","airstrike",
            "strike","bomb","casualt","killed","displaced","litani",
            "southern lebanon","beqaa","bekaa","tyre","sidon","nabatieh"]

# ─── HELPERS ───
def load_log():
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE) as f:
            return json.load(f)
    return {"last_updated": None, "updates": []}

def save_log(log):
    with open(LOG_FILE, "w") as f:
        json.dump(log, f, indent=2)

def read_map():
    with open(MAP_FILE) as f:
        return f.read()

def write_map(content):
    with open(MAP_FILE, "w") as f:
        f.write(content)

def get_current_max_id(html):
    # matches both `id: 5,` and `id:5,` formats
    ids = re.findall(r'\bid:\s*(\d+)[,}]', html)
    return max([int(x) for x in ids], default=44)

def get_existing_dates(html):
    # matches both `date: "2026-03-02"` and `date:"2026-03-02"` formats
    dates = re.findall(r'date:\s*"(\d{4}-\d{2}-\d{2})"', html)
    return set(dates)

# ─── RSS FETCH ───
def fetch_rss(name, url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 LB-Tracker/1.0"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            content = resp.read()
        root = ET.fromstring(content)
        channel = root.find("channel") or root
        items = channel.findall("item")
        results = []
        for item in items:
            title = htmllib.unescape(item.findtext("title", ""))
            desc  = htmllib.unescape(item.findtext("description", ""))
            link  = item.findtext("link", "")
            pub   = item.findtext("pubDate", "")
            combined = (title + " " + desc).lower()
            if any(kw in combined for kw in KEYWORDS):
                results.append({
                    "source": name,
                    "title": title.strip(),
                    "desc": re.sub(r'<[^>]+>', '', desc).strip()[:300],
                    "link": link,
                    "pub": pub,
                    "text": f"{title} {re.sub(r'<[^>]+>','',desc)}"
                })
        print(f"  [{name}] {len(results)} relevant items found")
        return results
    except Exception as e:
        print(f"  [{name}] RSS error: {e}")
        return []

def fetch_all_news():
    print("Fetching RSS feeds...")
    all_items = []
    for name, url in RSS_FEEDS:
        all_items.extend(fetch_rss(name, url))
    return all_items

def combined_text(items):
    return " ".join(i["text"] for i in items)

# ─── NUMBER EXTRACTION ───
def extract_numbers(text):
    # Prefer larger numbers (cumulative totals)
    killed_matches = re.findall(r'(\d[\d,]+)\s*(?:people\s+)?(?:killed|dead|deaths)', text, re.IGNORECASE)
    wounded_matches = re.findall(r'(\d[\d,]+)\s*(?:people\s+)?(?:wounded|injur)', text, re.IGNORECASE)
    displaced_matches = re.findall(r'([\d,.]+(?:\s*(?:million|thousand))?)\s*(?:people\s+)?displaced', text, re.IGNORECASE)

    def best_num(matches):
        if not matches:
            return None
        nums = []
        for m in matches:
            try:
                nums.append(int(m.replace(",","").replace(".","").split()[0]))
            except:
                pass
        return str(max(nums)) if nums else None

    return {
        "killed":    best_num(killed_matches),
        "wounded":   best_num(wounded_matches),
        "displaced": displaced_matches[0] if displaced_matches else None,
    }

# ─── ZONE DETECTION ───
ZONE_DEFS = [
    ("beirut",     ["beirut", "dahiyeh", "southern suburb", "bashoura", "corniche"],
     "strike",     "Beirut",               33.887, 35.511, "Beirut Strikes"),
    ("south",      ["southern lebanon","south lebanon","sidon","tyre","sur ","nabatieh","bint jbeil","marjayoun","khiam"],
     "strike",     "Southern Lebanon",     33.27,  35.30,  "South Lebanon Strikes"),
    ("beqaa",      ["beqaa","bekaa","zahle","baalbek","hermel","nabi chit","yohmor"],
     "strike",     "Beqaa Valley",         33.72,  35.88,  "Beqaa Valley Strikes"),
    ("ground",     ["ground operation","ground troop","incursion","infantry","armored","tank","merkava","seize","territory"],
     "ground",     "Southern Lebanon",     33.15,  35.50,  "Ground Operations"),
    ("phosphorus", ["white phosphorus","phosphor"],
     "phosphorus", "Lebanon",              33.55,  35.60,  "White Phosphorus Use Reported"),
    ("hvt",        ["commander killed","senior commander","irgc killed","quds force","hezbollah official","hezbollah leader","hezbollah commander"],
     "target",     "Lebanon",              33.87,  35.52,  "High-Value Target Eliminated"),
    ("un",         ["unifil","un peacekeeper","un peacekeeping","un base"],
     "un",         "Southern Lebanon (UNIFIL)", 33.12, 35.44, "UNIFIL Incident"),
    ("bridge",     ["bridge","infrastructure","port","airport"],
     "strike",     "Lebanon Infrastructure", 33.90, 35.48, "Infrastructure Strike"),
]

def detect_strike_zones(text):
    t = text.lower()
    zones = []
    for key, triggers, type_, loc, lat, lng, label in ZONE_DEFS:
        if any(tr in t for tr in triggers):
            zones.append({
                "key": key, "type": type_, "location": loc,
                "lat": lat, "lng": lng, "label": label
            })
    return zones

# ─── HEADLINE SUMMARY ───
def top_headlines(items, n=4):
    seen = set()
    headlines = []
    for item in items:
        title = item["title"]
        if title and title not in seen:
            seen.add(title)
            headlines.append(f"• {title} ({item['source']})")
            if len(headlines) >= n:
                break
    return "\n".join(headlines)

# ─── EVENT BUILDING ───
def build_events(zones, numbers, items, next_id):
    offsets = [(0,0),(0.012,0.012),(0.024,-0.012),(-0.012,0.018),(0.018,-0.024),(0.03,0.006)]
    events = []
    # Pick most informative description from headlines
    top_desc = ". ".join([i["title"] for i in items[:2]]) if items else ""
    top_desc = top_desc.replace('"', "'").replace('\n', ' ')[:250]

    for i, zone in enumerate(zones):
        dlat, dlng = offsets[i % len(offsets)]
        killed_str = numbers.get("killed")
        casualties_str = f"Cumulative total: {int(killed_str):,}+ killed" if killed_str and killed_str.isdigit() else (
            f"Cumulative: {killed_str}+ killed" if killed_str else None)

        desc = f"{zone['label']} reported on {TODAY_DISPLAY}."
        if top_desc and i == 0:
            desc += f" {top_desc}"

        events.append({
            "id": next_id + i,
            "date": TODAY,
            "type": zone["type"],
            "location": zone["location"],
            "lat": round(zone["lat"] + dlat, 4),
            "lng": round(zone["lng"] + dlng, 4),
            "title": f"{zone['label']} — {TODAY_DISPLAY}",
            "desc": desc.replace('"', "'"),
            "casualties": casualties_str
        })
    return events

def build_timeline_day(events, numbers, items):
    d = datetime.datetime.strptime(TODAY, "%Y-%m-%d")
    killed = numbers.get("killed")
    killed_int = int(killed) if killed and killed.isdigit() else None
    casualty_tag = f"{killed_int:,}+ killed" if killed_int else None

    ev_items = []
    for j, ev in enumerate(events):
        text_detail = items[j]["title"].replace('"', "'") if j < len(items) else ev["title"]
        ev_items.append({
            "type": ev["type"],
            "text": f"<strong>{ev['title']}</strong> — {text_detail}"
        })

    return {
        "date": f"{d.strftime('%B')} {d.day}, {d.year}",
        "key": TODAY,
        "casualtyTag": casualty_tag,
        "events": ev_items
    }

# ─── MAP INJECTION ───
def inject_into_map(html, new_events, timeline_day, numbers):
    if not new_events:
        return html, False

    # 1. Event JS entries — inject before closing ]; of EVENTS array
    entries = []
    for e in new_events:
        cas = f'"{e["casualties"]}"' if e.get("casualties") else "null"
        entries.append(f"""  {{ id:{e['id']}, date:"{e['date']}", type:"{e['type']}",
    loc:"{e['location']}", lat:{e['lat']}, lng:{e['lng']},
    title:"{e['title']}",
    desc:"{e['desc']}",
    cas:{cas}, src:"Al Jazeera / RSS" }},""")

    events_block = "\n".join(entries)
    # Inject inside EVENTS array — before the closing ];
    # The marker is the ];\ that immediately precedes the TIMELINE DATA comment.
    # We must include the ]; in the replacement so events land INSIDE the array.
    marker = "];\n\n// ═══════════════════════════════════════════════════════════\n// TIMELINE DATA"
    if marker not in html:
        # Fallback: any ]; followed by a comment block
        marker2 = "];\n\n// ═══════"
        if marker2 not in html:
            print("ERROR: injection marker missing from map HTML")
            return html, False
        html = html.replace(marker2, events_block + "\n" + marker2, 1)
    else:
        # Replace: keep the ]; AFTER the new events, not before
        replacement = events_block + "\n\n];\n\n// ═══════════════════════════════════════════════════════════\n// TIMELINE DATA"
        html = html.replace(marker, replacement, 1)

    # 2. Timeline day entry
    if timeline_day:
        evs_js = "\n      ".join([
            f'{{ type: "{ev["type"]}", text: "{ev["text"]}" }},'
            for ev in timeline_day["events"]
        ])
        cas_tag = f'"{timeline_day["casualtyTag"]}"' if timeline_day.get("casualtyTag") else "null"
        tday_js = f"""  {{
    date: "{timeline_day['date']}", key: "{timeline_day['key']}",
    casualtyTag: {cas_tag},
    events: [
      {evs_js}
    ]
  }},"""
        # Must inject INSIDE the TIMELINE array — before the ];\ that precedes MAP INIT
        tmarker = "];\n\n// ═══════════════════════════════════════════════════════════\n// MAP INIT"
        if tmarker in html:
            replacement_t = tday_js + "\n\n];\n\n// ═══════════════════════════════════════════════════════════\n// MAP INIT"
            html = html.replace(tmarker, replacement_t, 1)
        else:
            # Fallback: bare MAP INIT comment
            tmarker2 = "// MAP INIT"
            if tmarker2 in html:
                html = html.replace(tmarker2, tday_js + "\n\n// MAP INIT", 1)

    # 3. Date filter pill
    d = datetime.datetime.strptime(TODAY, "%Y-%m-%d")
    if f'data-filter="{TODAY}"' not in html:
        new_pill = f'      <button class="df-btn" data-filter="{TODAY}">Mar {d.day}</button>\n'
        # Try multiple anchor patterns
        for old_anchor in [
            '    </div>\n    <div class="map-legend">',
            '    </div>\n  </div>\n</div>\n\n<script>',
            '</div>\n    <div class="map-legend">',
        ]:
            if old_anchor in html:
                html = html.replace(old_anchor, new_pill + old_anchor, 1)
                break

    # 4. Update header stats
    if numbers.get("killed") and numbers["killed"].isdigit():
        k = int(numbers["killed"])
        html = re.sub(
            r'(<div class="stat-value">)\d[\d,]+\+?(<\/div>\s*<div class="stat-label">Killed)',
            rf'\g<1>{k:,}+\2', html
        )
    if numbers.get("wounded") and numbers["wounded"].isdigit():
        w = int(numbers["wounded"])
        html = re.sub(
            r'(<div class="stat-value">)\d[\d,]+\+?(<\/div>\s*<div class="stat-label">Wounded)',
            rf'\g<1>{w:,}+\2', html
        )

    return html, True

# ─── MAIN ───
def main():
    print(f"\n{'='*60}")
    print(f"Lebanon Conflict Tracker — Daily Update")
    print(f"UTC Date: {TODAY_DISPLAY}")
    print(f"{'='*60}\n")

    log = load_log()
    if log.get("last_updated") == TODAY:
        msg = f"Already updated today ({TODAY}). Skipping duplicate run."
        print(msg)
        return {"status": "skipped", "reason": msg, "notification": False}

    html         = read_map()
    existing     = get_existing_dates(html)
    next_id      = get_current_max_id(html) + 1

    print(f"Existing dates in map: {sorted(existing)}")
    print(f"Next event ID: {next_id}\n")

    if TODAY in existing:
        log["last_updated"] = TODAY
        save_log(log)
        return {"status": "skipped", "reason": f"Date {TODAY} already in map.", "notification": False}

    # Fetch news
    items = fetch_all_news()
    all_text = combined_text(items)

    # Save raw data
    os.makedirs(SEARCH_DIR, exist_ok=True)
    with open(os.path.join(SEARCH_DIR, f"search_{TODAY}.json"), "w") as f:
        json.dump({"date": TODAY, "item_count": len(items), "headlines": [i["title"] for i in items[:10]]}, f, indent=2)

    if not items:
        msg = "No relevant news items found in RSS feeds. Conflict may have paused or feeds unavailable."
        print(msg)
        log["last_updated"] = TODAY
        log["updates"].append({"date": TODAY, "status": "no_content", "message": msg})
        save_log(log)
        return {"status": "no_content", "message": msg, "notification": False}

    numbers = extract_numbers(all_text)
    zones   = detect_strike_zones(all_text)

    print(f"Detected zones  : {[z['key'] for z in zones]}")
    print(f"Numbers extracted: {numbers}")
    print(f"Headlines count  : {len(items)}\n")

    if not zones:
        msg = f"No strike zones detected for {TODAY_DISPLAY}. Conflict may be de-escalating."
        print(msg)
        log["last_updated"] = TODAY
        log["updates"].append({"date": TODAY, "status": "no_strikes", "message": msg})
        save_log(log)
        return {"status": "no_strikes", "message": msg, "notification": True,
                "summary": msg, "headlines": top_headlines(items)}

    new_events    = build_events(zones, numbers, items, next_id)
    timeline_day  = build_timeline_day(new_events, numbers, items)
    updated_html, ok = inject_into_map(html, new_events, timeline_day, numbers)

    if not ok:
        msg = "Map injection failed. Check map HTML structure."
        log["last_updated"] = TODAY
        log["updates"].append({"date": TODAY, "status": "error", "message": msg})
        save_log(log)
        return {"status": "error", "message": msg, "notification": False}

    write_map(updated_html)
    print(f"Map updated: {len(new_events)} new event(s) written to {MAP_FILE}")

    # ─ Build rich notification summary ─
    killed_disp   = f"{int(numbers['killed']):,}+" if numbers.get("killed") and numbers["killed"].isdigit() else numbers.get("killed","unknown")
    wounded_disp  = f"{int(numbers['wounded']):,}+" if numbers.get("wounded") and numbers["wounded"].isdigit() else numbers.get("wounded","unknown")
    displaced_disp = numbers.get("displaced","unknown")

    summary = (
        f"Lebanon Conflict Map Updated — {TODAY_DISPLAY}\n\n"
        f"Strikes detected in: {', '.join(z['label'] for z in zones)}\n\n"
        f"Cumulative casualties:\n"
        f"  Killed: {killed_disp}\n"
        f"  Wounded: {wounded_disp}\n"
        f"  Displaced: {displaced_disp}\n\n"
        f"Top headlines:\n{top_headlines(items)}\n\n"
        f"Map: {MAP_URL}"
    )
    print(f"\nNotification summary:\n{summary}")

    log["last_updated"] = TODAY
    log["updates"].append({
        "date": TODAY, "status": "updated",
        "new_events": len(new_events),
        "zones": [z["key"] for z in zones],
        "numbers": numbers,
    })
    save_log(log)

    return {
        "status": "updated",
        "date": TODAY,
        "new_events": len(new_events),
        "summary": summary,
        "numbers": numbers,
        "notification": True,
        "notification_title": f"Lebanon Map Updated — {len(new_events)} new events ({TODAY_DISPLAY})",
        "notification_body": summary,
    }

if __name__ == "__main__":
    result = main()
    print("\nRESULT_JSON:" + json.dumps(result))
    sys.exit(0)
