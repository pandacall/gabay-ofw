# Safe Floor dialability verification (issue #39)

Per-number reachability record for every entry in `app/directory.py`
(`_ENTRIES`). Rule: a number that cannot be verified from an official
source does **not** ship on a card; a number not dialable from the
user's country ships only as a Manila-relay row. Verified 03 Sep 2026.

The single canonical DMW source for MWO numbers is the official
**DMW MWO Directory and Jurisdiction (as of 13 March 2026)** PDF:
<https://dmw.gov.ph/archives/v1/resources/dsms/DMW/MWO-Directory-and-Jurisdiction-as-of-13-March-2026.pdf>
(downloaded and text-extracted during this verification).

## Shipped numbers

| Key | Number | Official source | Dials from | Notes |
|---|---|---|---|---|
| `mwo_riyadh` | +966 50 285 0944 | DMW MWO Directory PDF (13 Mar 2026); riyadhpe.dfa.gov.ph/contact-us (archived 01 Jan 2026) | Saudi networks (Saudi mobile) | Both sources agree |
| `mwo_alkhobar` | +966 56 232 9926 | DMW MWO Directory PDF (13 Mar 2026), row "Alkhobar, KSA" (`mwo_alkhobar@dmw.gov.ph +966562329926`) | Saudi networks | Embassy page lists an Eastern-Region ops line +966 53 449 5729; the DMW directory number is shipped as canonical |
| `ph_embassy_riyadh_atn` | +966 56 989 3301 | riyadhpe.dfa.gov.ph/contact-us (archived 01 Jan 2026): "Assistance to Nationals Section … HOTLINE +966569893301" | Saudi networks | 24/7 ATN hotline |
| `pcg_jeddah_atn` | +966 55 521 9613 | jeddahpcg.dfa.gov.ph/113-help-for-filipinos (archived 25 Aug 2025); also on riyadhpe.dfa.gov.ph | Saudi networks | Covers Makkah/Madinah/western KSA; second line +966 53 424 0362 |
| `mwo_doha` | +974 3318 2459 | DMW MWO Directory PDF (13 Mar 2026); dohape.dfa.gov.ph/contact-us (archived 13 Apr 2025) | Qatari networks | |
| `mwo_doha_atn` | +974 5118 4242 | dohape.dfa.gov.ph/contact-us (archived 13 Apr 2025): "Assistance-to-Nationals (ATN)" | Qatari networks | |
| `ph_embassy_doha_atn` | +974 6644 6303 | dohape.dfa.gov.ph/contact-us (archived 13 Apr 2025): "Hotline for nationals in distress" | Qatari networks | |
| `mwo_kuwait` | +965 9403 9063 | DMW MWO Directory PDF (13 Mar 2026); kuwaitpe.dfa.gov.ph MWO page (archived 20 Apr 2025) | Kuwaiti networks | Alternates +965 6040 3858, +965 6558 5355 |
| `mwo_dubai` | +971 50 652 6626 | DMW MWO Directory PDF (13 Mar 2026); dubaipcg.dfa.gov.ph/contact-us (archived 13 Feb 2025) | UAE networks | Covers Dubai + northern emirates |
| `mwo_abu_dhabi` | +971 56 270 9157 | DMW MWO Directory PDF (13 Mar 2026); abudhabipe.dfa.gov.ph/contact-us (archived 08 Feb 2025, "POLO MAIN HOTLINE") | UAE networks | Arabic line +971 55 616 9779 |
| `ph_consulate_dubai_atn` | +971 56 501 5756 | dubaipcg.dfa.gov.ph/contact-us (archived 13 Feb 2025): "Assistance to Nationals (ATN)" | UAE networks | |
| `dfa_oumwa_atn` | +63 2 8834 4996 | foi.gov.ph DFA response (fetched live 03 Sep 2026, "Trunkline: (02) 8834-4996/4594"); PNA 21 Jun 2023 | Any network, international format (toll applies) | Metro Manila geographic landline. OUMWA renamed OUMA 10 Apr 2024 (dfa.gov.ph release) |
| `dmw_orcc` | +63 2 8722 1144 | dfa.gov.ph release 10 Apr 2024 (archived 16 Oct 2025): "Hotline Numbers: 8722-1144 / 8722-1155 / 1348 (ORCC)"; dmw.gov.ph/archives/poea/contact.html (fetched live 03 Sep 2026) | Any network, international format | DFA itself redirects OFW cases from MWO countries here; alt +63 2 8722 1155 |
| `owwa_1348` | 1348 | dfa.gov.ph release 10 Apr 2024 (ORCC hotline list); owwa.gov.ph branding | **Philippines only** — PH-carrier short code | Ships as Manila-relay only. The widely republished "+63 2 1348" overseas variant is not confirmed on owwa.gov.ph, so it does not ship |

## Deliberately NOT shipped (fail closed)

| Candidate | Why it does not ship |
|---|---|
| MWO Jeddah phone | The official MWO Jeddah site (mwo-jeddah.org/contact-us) publishes emails only. The DMW Directory PDF prints `+96569819720`, which fails Saudi number-length validation (a dropped digit; third parties print +966 56 981 9720, unconfirmed officially). Western KSA is covered by `pcg_jeddah_atn`. |
| PH Embassy Kuwait ATN hotline | Published only as image banners on kuwaitpe.dfa.gov.ph (no extractable text); third-party sources print +965 6500 2612, unconfirmed officially. `mwo_kuwait` (embassy compound) is verified and ships. |
| "DMW hotline 1553" | Not found on any official source (dmw.gov.ph, pna.gov.ph, pia.gov.ph). The only official 1553 is the DOH mental-health crisis line. The verified overseas DMW line is the ORCC (+63 2 8722 1144/1155), which ships instead. |
| 1343 Actionline (anti-trafficking) | Short code is PH-domestic; official overseas access is the TinBo app call, not a dialable number; "+63 2 1343" unconfirmed on an official page. Out of card scope for now. |
| "+63 2 1348" | Published in 2019 launch media but not on owwa.gov.ph; unverified, so 1348 ships only as a Manila-relay short code. |

## Standing facts

- Philippine short codes (1348, 1553, 1343) are provisioned on Philippine
  carriers only and are **not dialable from Saudi, Qatari, Kuwaiti, or
  Emirati networks**. Every Gulf mission accordingly publishes local
  host-country mobile hotlines, which is what the cards lead with.
- Gulf mission mobile hotlines rotate every 1–2 years. Snapshot dates
  above are the verification anchor; a manual test-call pass before any
  public launch is advisable, and the DMW MWO Directory PDF (updated
  roughly monthly) is the refresh source.
