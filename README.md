# VFF-kampdata

Automatisk daglig hentning af **alle** Viborg FF-akademiets kampe (U13–U19)
fra dbu.dk: turneringskampe (førsteholdenes Liga 1/Ligaen), U16 Cup samt
trænings- og pokalkampe. Akademiets kampprogram-side henter
[`dbu-data.json`](dbu-data.json) direkte fra dette repo.

- `hent_dbu.py` — hentescriptet (kun Python-standardbibliotek)
- `puljer.json` — kendte DBU-puljer; nye opdages automatisk via DBU's kampsøgning (fx forårspuljer og pokalrunder)
- `dbu-data.json` — dagens kampdata (kampnr, dato, tid, hold, spillested, resultat, straffespark, match_type)
- `senest-koert.txt` — seneste kørsel; fungerer også som dagligt livstegn, så GitHub ikke pauser tidsplanen
- `.github/workflows/hent.yml` — kører dagligt (sat til 06:30, men GitHub starter den typisk
  mellem 10:30 og 12) og desuden lørdag og søndag kl. ca. 15, 18 og 21, så weekendens
  resultater står der samme aften

Indholdet er DBU's offentlige kampprogram-data.

## Straffespark

Ender en kamp i straffesparkskonkurrence (U15-ligaen sender uafgjorte kampe
dertil), står slutresultatet i `score_home`/`score_away` som ellers, og
straffesparkene i tre felter:

```json
"score_home": 2,
"score_away": 2,
"penalty_winner": "home",
"penalty_winner_goals": 7,
"penalty_loser_goals": 6
```

`penalty_winner` er `"home"` eller `"away"`; målene er vinderens og taberens i
konkurrencen. Uden straffespark er de tre felter `null`. Er DBU's tal
urimelige (set: «43 - -1»), står vinderen uden tal.

Selve kampprogrammet er `index.html` og serveres altid på
**https://mikkel2409-dot.github.io/vff-kampdata/** via GitHub Pages.

## Manuelle kampe (fælles for alle)

`manuelle-kampe.json` er klubbens fælles liste over kampe, som DBU ikke kender
(fx akademiets aftalte testkampe). Alt heri vises automatisk for ALLE besøgende
på siden. Redigér filen direkte på GitHub (blyants-ikonet) — én kamp ser sådan ud:

```json
{
  "id": "u15-vejle-2026-09-20",
  "team": "U15",
  "match_type": "venlig",
  "date_iso": "2026-09-20",
  "time": "11:00",
  "home_team": "Viborg FF",
  "away_team": "Vejle B",
  "venue": "Viborg FF´s anlæg",
  "address": "Rughavevej 39 b, 8800 Viborg",
  "score_home": null,
  "score_away": null
}
```

`team`: U13/U14/U15/U17/U19 · `match_type`: `venlig`, `stævne` eller `pokal` ·
`id`: unikt og stabilt (ændres det, opfattes kampen som ny) · resultat udfyldes
i `score_home`/`score_away`, når kampen er spillet. Flyttes en kamp, rettes
dato/tid blot — siden flytter den selv hos alle. Slettes en kamp fra listen,
markeres den med et "Tjek DBU"-flag på siden i stedet for at forsvinde.
