# VFF-kampdata

Automatisk daglig hentning af **alle** Viborg FF-akademiets kampe (U13–U19)
fra dbu.dk: turneringskampe (førsteholdenes Liga 1/Ligaen), U16 Cup samt
trænings- og pokalkampe. Akademiets kampprogram-side henter
[`dbu-data.json`](dbu-data.json) direkte fra dette repo.

- `hent_dbu.py` — hentescriptet (kun Python-standardbibliotek)
- `puljer.json` — kendte DBU-puljer; nye opdages automatisk via DBU's kampsøgning (fx forårspuljer og pokalrunder)
- `dbu-data.json` — dagens kampdata (kampnr, dato, tid, hold, spillested, resultat, match_type)
- `senest-koert.txt` — seneste kørsel; fungerer også som dagligt livstegn, så GitHub ikke pauser tidsplanen
- `.github/workflows/hent.yml` — kører dagligt kl. ca. 06:30

Indholdet er DBU's offentlige kampprogram-data.
