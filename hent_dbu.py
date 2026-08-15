# -*- coding: utf-8 -*-
"""
Henter ALLE Viborg FF-akademiets kampe (U13-U19) fra dbu.dk og skriver
dbu-data.json: turneringskampe (førsteholdenes Liga 1/Ligaen), U16 Cup,
trænings- og pokalkampe - med match_type på hver kamp
('liga'/'u16cup'/'venlig'/'pokal').

Mekanik:
  1) DBU's udvidede kampsøgning (kun KOMMENDE kampe) bruges til at OPDAGE
     puljer, hvor Viborg FF's akademihold spiller - også når nye puljer
     opstår ved sæson-/halvsæsonskifte eller nye pokalrunder.
  2) Alle kampe (inkl. resultater for spillede) parses fra puljernes
     kampprogram-sider. puljer.json husker kendte puljer, så resultater
     også samles op, efter at puljens sidste kamp er forsvundet fra
     søgningens fremtidsvindue.

Kun standardbiblioteket - ingen pip-afhængigheder.
"""
import json
import re
import sys
import time
import html as htmllib
import datetime
import urllib.request
import urllib.parse

KLUBNAVN = "Viborg FF"
UNIONER = [1, 2, 3, 4]          # DBU (landsdækkende), Sjælland, Jylland, Fyn
AARGANGE = {"U13", "U14", "U15", "U17", "U19"}
PULJE_STATE_FIL = "puljer.json"
UDDATA_FIL = "dbu-data.json"
BEHOLD_PULJE_DAGE = 21          # puljer beholdes til 3 uger efter sidste VFF-kamp
SOEGEVINDUE_DAGE = 300          # kampsøgningens fremtidsvindue (maks. 364)

UA = {"User-Agent": "Mozilla/5.0 (kampprogram-synk; kontakt: Viborg FF akademi)"}
DA_WEEKDAYS = ["man.", "tirs.", "ons.", "tors.", "fre.", "lør.", "søn."]


def hent(url, forsoeg=2, timeout=30):
    """GET med valgfrit gentaget forsøg - DBU er periodisk overbelastet."""
    for i in range(forsoeg):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return htmllib.unescape(r.read().decode("utf-8", errors="replace"))
        except Exception:
            if i + 1 == forsoeg:
                raise
            time.sleep(5)


def normaliser_holdnavn(navn):
    """Fjern DBU's holdsuffikser: 'Viborg FF (1)', 'Viborg FF (L2/512)', 'AC Horsens U14'."""
    navn = navn.strip()
    navn = re.sub(r"\s*\((?:\d+|L\d+/\d+)\)$", "", navn)
    navn = re.sub(r"\s+U\d{2}$", "", navn)
    return navn.strip()


VIBORG_ALIASER = {KLUBNAVN, "FK Viborg"}  # DBU Jylland-puljer skriver "FK Viborg"


def er_viborg(navn):
    return normaliser_holdnavn(navn) in VIBORG_ALIASER


def klassificer_raekke(raekke):
    """Række-navn -> (hold-på-siden, match_type), eller None hvis rækken ikke
    hører til akademisiden. Kun FØRSTEHOLDENES ligarækker (Liga 1/Ligaen)
    medtages; Liga 2+ og C-hold er andethold. Trænings- og pokalrækker
    medtages for alle årgange (pokal er typisk rækkeholdene - bevidst valg)."""
    r = raekke.strip()
    if re.match(r"^U16 Cup Drenge", r):
        return ("U17", "u16cup")  # U16 Cup vises under U17 på siden
    m = re.match(r"^(U\d{2})\s+Drenge\b", r)
    if not m or m.group(1) not in AARGANGE:
        return None
    aargang = m.group(1)
    if "Træningskamp" in r:
        return (aargang, "venlig")
    if "Pokal" in r:
        return (aargang, "pokal")
    if re.match(r"^U1[579] Drenge Ligaen\b", r) or re.match(r"^U1[34] Drenge Liga 1\b", r):
        return (aargang, "liga")
    return None


def parse_celler(raekke_html):
    """<td>-celler som (ren tekst)-liste."""
    celler = re.findall(r"<td[^>]*>([\s\S]*?)</td>", raekke_html)
    return [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip() for c in celler]


def parse_dato(tekst):
    """'lør. 15-08 2026' eller '15-08 2026' -> date."""
    m = re.search(r"(\d{2})-(\d{2})\s+(\d{4})", tekst)
    if not m:
        return None
    return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))


def soeg_puljer(idag):
    """Kampsøgningen: find (pulje-id -> {type, aargang}) for kommende VFF trænings-/pokalkampe."""
    fundne = {}
    til = idag + datetime.timedelta(days=SOEGEVINDUE_DAGE)
    for union in UNIONER:
        params = {
            "mode": "searchresult", "UnionId": str(union), "GenderId": "",
            "City": "", "Stadium": "", "Club": KLUBNAVN,
            "DateFrom": idag.strftime("%d-%m-%Y"), "DateTo": til.strftime("%d-%m-%Y"),
            "ZipFrom": "", "ZipTo": "", "DivisionAgeGroupIdList": "",
            "IncludeNormalMatches": "true", "IncludeTrainingMatches": "true",
            "IncludeCupMatches": "false",
        }
        url = "https://www.dbu.dk/resultater/kampsoegAdvanceret?" + urllib.parse.urlencode(params)
        try:
            # Opdagelse må gerne fejle billigt: kørslen er daglig, og puljerne
            # i puljer.json er alligevel rygraden - derfor kun ét kort forsøg.
            side = hent(url, forsoeg=1, timeout=12)
        except Exception as e:
            print(f"  ADVARSEL: søgning union {union} fejlede: {e}", file=sys.stderr)
            continue
        finally:
            time.sleep(2)
        for del_ in side.split("MatchProgramMatchClick")[1:]:
            m = re.match(r"\('/resultater/kamp/(\d+)_(\d+)/kampinfo'\)", del_)
            if not m:
                continue
            pulje = m.group(2)
            celler = parse_celler(del_[:4000])
            raekke = next((c for c in celler if re.match(r"^U\d{2}\b", c) and ("Drenge" in c or "Cup" in c)), None)
            if not raekke:
                continue
            klass = klassificer_raekke(raekke)
            if not klass:
                continue
            if not any(er_viborg(c) for c in celler):
                continue
            fundne[pulje] = {"type": klass[1], "aargang": klass[0], "raekke": raekke}
    return fundne


def parse_pulje(pulje_id, info):
    """Alle VFF-kampe i puljens kampprogram (kolonner: -, kampnr, dato, tid, hjemme, ude, spillested, resultat)."""
    side = hent(f"https://www.dbu.dk/resultater/pulje/{pulje_id}/kampprogram")
    kampe = []
    for del_ in side.split("MatchProgramMatchClick")[1:]:
        m = re.match(r"\('/resultater/kamp/(\d+)_(\d+)/kampinfo'\)", del_)
        if not m:
            continue
        celler = parse_celler(del_[:6000])
        # celle 0 er tom/ikon; find kampnr-cellen og læs positionsbaseret derfra
        try:
            nr_i = next(i for i, c in enumerate(celler) if c == m.group(1))
        except StopIteration:
            continue
        dato = parse_dato(celler[nr_i + 1]) if len(celler) > nr_i + 1 else None
        tid_m = re.search(r"\b(\d{2}:\d{2})\b", celler[nr_i + 2]) if len(celler) > nr_i + 2 else None
        hjemme = celler[nr_i + 3] if len(celler) > nr_i + 3 else ""
        ude = celler[nr_i + 4] if len(celler) > nr_i + 4 else ""
        sted = celler[nr_i + 5] if len(celler) > nr_i + 5 else ""
        res = celler[nr_i + 6] if len(celler) > nr_i + 6 else ""
        if dato is None or not (er_viborg(hjemme) or er_viborg(ude)):
            continue
        res_m = re.match(r"^(\d+)\s*-\s*(\d+)$", res)
        kampe.append({
            "team": info["aargang"],
            "kampnr": m.group(1),
            "pulje": pulje_id,
            "match_type": info["type"],
            "date_iso": dato.isoformat(),
            "weekday": DA_WEEKDAYS[dato.weekday()],
            "time": tid_m.group(1) if tid_m else "",
            "home_team": normaliser_holdnavn(hjemme),
            "away_team": normaliser_holdnavn(ude),
            "venue": sted,
            "score_home": int(res_m.group(1)) if res_m else None,
            "score_away": int(res_m.group(2)) if res_m else None,
        })
    return kampe


def main():
    idag = datetime.date.today()
    try:
        with open(PULJE_STATE_FIL, encoding="utf-8") as f:
            state = json.load(f)
    except FileNotFoundError:
        state = {}

    print(f"Søger kommende trænings-/pokalkampe for {KLUBNAVN} ...")
    fundne = soeg_puljer(idag)
    for pulje, info in fundne.items():
        gammel = state.get(pulje, {})
        state[pulje] = {**gammel, **info}
    print(f"  puljer fra søgning: {sorted(fundne)} | kendte i alt: {sorted(state)}")

    alle_kampe = []
    fejlede = 0
    for pulje, info in sorted(state.items()):
        try:
            kampe = parse_pulje(pulje, info)
        except Exception as e:
            print(f"  ADVARSEL: pulje {pulje} kunne ikke hentes: {e}", file=sys.stderr)
            fejlede += 1
            continue
        if kampe:
            info["seneste_kamp"] = max(k["date_iso"] for k in kampe)
        elif "seneste_kamp" not in info:
            # Tom pulje uden historik: giv den en frist, så den ikke hænger evigt
            info["seneste_kamp"] = idag.isoformat()
        print(f"  pulje {pulje} ({info.get('raekke', info['type'])}): {len(kampe)} VFF-kampe")
        alle_kampe.extend(kampe)
        time.sleep(1)

    if fejlede == len(state) and state:
        print("FEJL: ingen puljer kunne hentes - beholder eksisterende data.", file=sys.stderr)
        sys.exit(1)

    # Glem puljer, hvis sidste VFF-kamp ligger mere end BEHOLD_PULJE_DAGE tilbage
    graense = (idag - datetime.timedelta(days=BEHOLD_PULJE_DAGE)).isoformat()
    for pulje in [p for p, i in state.items() if i.get("seneste_kamp", "9999") < graense]:
        print(f"  pulje {pulje} udgået (sidste kamp {state[pulje]['seneste_kamp']}) - fjernes")
        del state[pulje]

    # Dublet-værn på kampnr og gruppering pr. årgang
    teams = {}
    set_ = set()
    for k in sorted(alle_kampe, key=lambda k: (k["date_iso"], k["time"])):
        if k["kampnr"] in set_:
            continue
        set_.add(k["kampnr"])
        teams.setdefault(k["team"], []).append(k)

    ud = {"updated": datetime.datetime.now(datetime.timezone.utc).isoformat(), "teams": teams}
    with open(UDDATA_FIL, "w", encoding="utf-8") as f:
        json.dump(ud, f, ensure_ascii=False, indent=1)
    with open(PULJE_STATE_FIL, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1, sort_keys=True)
    print(f"Skrev {UDDATA_FIL}: " + ", ".join(f"{t}: {len(ks)}" for t, ks in sorted(teams.items())) or "tom")


if __name__ == "__main__":
    main()
