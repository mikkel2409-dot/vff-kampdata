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
# U13, U14, U15, U16, U17, U19 i DBU-søgningens aldersgruppe-id'er. Uden dette
# filter dækker søgningen ALLE aldersgrupper og timer ud på DBU's server.
ALDERSGRUPPE_IDS = ["20", "19", "18", "17", "16", "30"]
AARGANGE = {"U13", "U14", "U15", "U17", "U19"}
PULJE_STATE_FIL = "puljer.json"
STEDER_FIL = "steder.json"      # cache: stadium-id -> adresse (til "Vis rute")
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
    """Fjern DBU's holdsuffikser: 'Viborg FF (1)', 'Viborg FF (L2/512)',
    'FK Viborg (Liga)', 'Viborg FF (L2C/622)', 'AC Horsens U14'."""
    navn = navn.strip()
    navn = re.sub(r"\s*\((?:\d+|Liga|L[0-9A-Z]+(?:/\d+)?)\)$", "", navn)
    navn = re.sub(r"\s+U\d{2}$", "", navn)
    return navn.strip()


def hold_markoer(navn):
    """DBU's raekkemarkoer, som pokalpuljer saetter efter holdnavnet:
    'FK Viborg (Liga)' -> 'LIGA', 'FK Viborg (L1/601)' -> 'L1',
    'Viborg FF (L2C/622)' -> 'L2C'. None hvis holdet ikke baerer en markoer."""
    m = re.search(r"\((Liga|L[0-9A-Z]+?)(?:/\d+)?\)$", navn.strip())
    return m.group(1).upper() if m else None


# Akademiets foerstehold spiller i Ligaen (U15/U17/U19) eller Liga 1 (U13/U14).
# Klubbens andethold (Liga 2, 2C, 3, 4, C-hold) stiller ogsaa op i pokalen,
# men hoerer ikke til paa akademiets kampprogram.
FOERSTEHOLD_MARKOERER = {"LIGA", "L1"}

VIBORG_ALIASER = {KLUBNAVN, "FK Viborg"}  # DBU skriver begge dele: U13/U14 og
                                          # pokal-foersteholdene hedder "FK Viborg"


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


# Straffesparkskonkurrencen. DBU sætter et mærke med en tooltip INDE i vinderens
# mål-felt i resultat-cellen (U15-ligaen sender uafgjorte kampe til straffespark):
#   <div class="home-score"><div class="penalty-result-badge _home"> <img .../>
#     <div class="tool-tip"> Straffesparkskonkurrence <br /> 7 - 6 </div> </div> 2 </div>
#   <div> - </div> <div class="away-score"> 2 </div>
# Som ren tekst står der «Straffesparkskonkurrence 7 - 6 2 - 2», og indtil 23/9-26
# blev resultatet derfor slet ikke læst (U15 mod AaB 12/9 manglede sit 2-2).
STRAFFE_TEKST = re.compile(r"straffespark\w*\s*(-?\d+)\s*-\s*(-?\d+)", re.IGNORECASE)
STRAFFE_SIDE = re.compile(r"penalty-result-badge\s+_(home|away)\b")


def parse_resultat(celle_html):
    """Resultat-cellen -> (hjemme, ude, straffe). Alt er None uden et resultat.

    `straffe` er None uden straffesparkskonkurrence, ellers
    {"winner": "home"/"away", "winner_goals": 7, "loser_goals": 6}. Vinderen er
    mærkets side. Tallene gemmes som vinderens og taberens - det største er
    vinderens - så rækkefølgen i tooltip'en er ligegyldig. Urimelige tal (DBU
    har vist «43 - -1») giver vinderen uden tal.
    """
    tekst = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", celle_html)).strip()
    straffe = None
    side_m = STRAFFE_SIDE.search(celle_html)
    if side_m:
        straffe = {"winner": side_m.group(1), "winner_goals": None, "loser_goals": None}
        tal_m = STRAFFE_TEKST.search(tekst)
        if tal_m:
            a, b = int(tal_m.group(1)), int(tal_m.group(2))
            if min(a, b) >= 0 and max(a, b) <= 30 and a != b:
                straffe["winner_goals"], straffe["loser_goals"] = max(a, b), min(a, b)
    # Tooltip'en ud - den står foran vinderens mål, hvad enten det er hjemme eller ude
    rest = re.sub(r"\s+", " ", STRAFFE_TEKST.sub(" ", tekst)).strip()
    res_m = re.match(r"^(\d+)\s*-\s*(\d+)$", rest)
    if not res_m:
        return None, None, None
    return int(res_m.group(1)), int(res_m.group(2)), straffe


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
            "ZipFrom": "", "ZipTo": "", "DivisionAgeGroupIdList": ALDERSGRUPPE_IDS,
            "IncludeNormalMatches": "true", "IncludeTrainingMatches": "true",
            "IncludeCupMatches": "false",
        }
        url = "https://www.dbu.dk/resultater/kampsoegAdvanceret?" + urllib.parse.urlencode(params, doseq=True)
        try:
            # Opdagelse må gerne fejle billigt: kørslen er daglig, og puljerne
            # i puljer.json er alligevel rygraden - derfor kun ét kort forsøg.
            side = hent(url, forsoeg=1, timeout=20)
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


def hent_stadium_adresse(stadium_id):
    """Adresse fra DBU's spillested-side ('Adresse | Ansvej 110 | 8600 Silkeborg')."""
    side = hent(f"https://www.dbu.dk/resultater/stadium/{stadium_id}", forsoeg=1, timeout=15)
    tokens = [t.strip() for t in re.split(r"<[^>]+>", side) if t.strip()]
    for i, t in enumerate(tokens):
        if t == "Adresse" and i + 2 < len(tokens):
            gade, postby = tokens[i + 1], tokens[i + 2]
            if re.match(r"^\d{4}\s", postby):
                return f"{gade}, {postby}"
            return gade
    return ""


def parse_pulje(pulje_id, info):
    """Alle VFF-kampe i puljens kampprogram (kolonner: -, kampnr, dato, tid, hjemme, ude, spillested, resultat)."""
    side = hent(f"https://www.dbu.dk/resultater/pulje/{pulje_id}/kampprogram")
    kampe = []
    for del_ in side.split("MatchProgramMatchClick")[1:]:
        m = re.match(r"\('/resultater/kamp/(\d+)_(\d+)/kampinfo'\)", del_)
        if not m:
            continue
        stadium_m = re.search(r"/resultater/stadium/(\d+)", del_[:6000])
        id_for_navn = {n.strip(): h for h, n in
                       re.findall(r'href="/resultater/hold/(\d+)_\d+"[^>]*>([^<]+)<', del_[:6000])}
        celler = parse_celler(del_[:6000])
        # Samme celler som HTML - resultat-cellens straffespark ses kun dér
        raa_celler = re.findall(r"<td[^>]*>([\s\S]*?)</td>", del_[:6000])
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
        res_html = raa_celler[nr_i + 6] if len(raa_celler) > nr_i + 6 else ""
        vi_hjemme, vi_ude = er_viborg(hjemme), er_viborg(ude)
        if dato is None or not (vi_hjemme or vi_ude):
            continue

        # I pokalpuljer stiller klubben BAADE akademiets foerstehold og et andethold.
        # Foerste gang udpeges akademiets hold paa DBU's raekkemarkoer, og holdets
        # id gemmes i puljer.json - derefter er id'et alene afgoerende, saa et
        # aendret holdnavn ikke kan snyde filteret.
        if info["type"] == "pokal":
            vores_navn = hjemme if vi_hjemme else ude
            vores_id = id_for_navn.get(vores_navn)
            kendt_id = info.get("holdid")
            if kendt_id:
                if vores_id != kendt_id:
                    print(f"    pulje {pulje_id}: kamp {m.group(1)} udeladt - "
                          f"'{vores_navn}' (id {vores_id}) er ikke akademiets hold "
                          f"(forventet id {kendt_id})")
                    continue
            elif hold_markoer(vores_navn) in FOERSTEHOLD_MARKOERER and vores_id:
                info["holdid"] = vores_id
                print(f"    pulje {pulje_id}: akademiets hold udpeget som "
                      f"'{vores_navn}' (id {vores_id})")
            else:
                print(f"    pulje {pulje_id}: kamp {m.group(1)} udeladt - '{vores_navn}' "
                      f"er ikke akademiets hold (markoer: {hold_markoer(vores_navn) or 'ingen'})")
                continue

        score_home, score_away, straffe = parse_resultat(res_html)
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
            "stadium": stadium_m.group(1) if stadium_m else None,
            "score_home": score_home,
            "score_away": score_away,
            # Straffesparkskonkurrencen: vinderens side og målene som vinder/taber
            "penalty_winner": straffe["winner"] if straffe else None,
            "penalty_winner_goals": straffe["winner_goals"] if straffe else None,
            "penalty_loser_goals": straffe["loser_goals"] if straffe else None,
        })
    return kampe


def main():
    idag = datetime.date.today()
    try:
        with open(PULJE_STATE_FIL, encoding="utf-8") as f:
            state = json.load(f)
    except FileNotFoundError:
        state = {}
    try:
        with open(STEDER_FIL, encoding="utf-8") as f:
            steder = json.load(f)
    except FileNotFoundError:
        steder = {}
    # Gårsdagens kampe bruges som reserve, hvis en enkelt pulje fejler i dag -
    # ellers ville dens kampe mangle i feedet og blive fejl-flaget på siden.
    try:
        with open(UDDATA_FIL, encoding="utf-8") as f:
            forrige_kampe = [k for ks in json.load(f).get("teams", {}).values() for k in ks]
    except Exception:
        forrige_kampe = []

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
            genbrug = [k for k in forrige_kampe if k.get("pulje") == pulje]
            print(f"  ADVARSEL: pulje {pulje} kunne ikke hentes ({e})"
                  + (f" - genbruger gårsdagens {len(genbrug)} kampe" if genbrug else ""), file=sys.stderr)
            alle_kampe.extend(genbrug)
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

    # Slå adresser op for nye spillesteder (cachen gør det til en engangsudgift)
    manglende_steder = {k["stadium"] for k in alle_kampe if k.get("stadium")} - set(steder)
    for sid in sorted(manglende_steder):
        try:
            steder[sid] = hent_stadium_adresse(sid)
            time.sleep(0.5)
        except Exception as e:
            print(f"  ADVARSEL: adresse for spillested {sid} kunne ikke hentes: {e}", file=sys.stderr)
    if manglende_steder:
        print(f"  nye spillested-adresser hentet: {len(manglende_steder & set(steder))}")

    # Dublet-værn på kampnr og gruppering pr. årgang
    teams = {}
    set_ = set()
    for k in sorted(alle_kampe, key=lambda k: (k["date_iso"], k["time"])):
        if k["kampnr"] in set_:
            continue
        set_.add(k["kampnr"])
        k["address"] = steder.get(k.pop("stadium", None) or "", "") or k.get("address", "")
        teams.setdefault(k["team"], []).append(k)

    ud = {"updated": datetime.datetime.now(datetime.timezone.utc).isoformat(), "teams": teams}
    with open(UDDATA_FIL, "w", encoding="utf-8") as f:
        json.dump(ud, f, ensure_ascii=False, indent=1)
    with open(PULJE_STATE_FIL, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1, sort_keys=True)
    with open(STEDER_FIL, "w", encoding="utf-8") as f:
        json.dump(steder, f, ensure_ascii=False, indent=1, sort_keys=True)
    print(f"Skrev {UDDATA_FIL}: " + ", ".join(f"{t}: {len(ks)}" for t, ks in sorted(teams.items())) or "tom")


if __name__ == "__main__":
    main()
