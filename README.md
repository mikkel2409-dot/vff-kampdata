# VFF-kampdata

Automatisk daglig hentning af Viborg FF's **trænings- og pokalkampe** (U13–U19)
fra dbu.dk. Bruges af akademiets kampprogram-side, som henter
[`dbu-data.json`](dbu-data.json) direkte fra dette repo.

- `hent_dbu.py` — hentescriptet (kun Python-standardbibliotek)
- `puljer.json` — kendte DBU-puljer; opdateres automatisk, når nye opdages via DBU's kampsøgning
- `dbu-data.json` — dagens kampdata (kampnr, dato, tid, hold, spillested, resultat)
- `.github/workflows/hent.yml` — kører dagligt kl. ca. 06:30 og committer kun ved ændringer

Liga-kampene hentes ikke her — de leveres af klubbens eksisterende synk-worker.
Indholdet er DBU's offentlige kampprogram-data.
