"""Laver de opdigtede testdata til chatbotten.

Kør:  python data/lav_data.py

Alle personer, adresser og telefonnumre er opdigtede. Brug aldrig rigtige
persondata i dette projekt. Scriptet bruger et fast "seed", så det giver
præcis de samme data hver gang. Det gør testene gentagelige.
"""

import json
import random
from datetime import date, timedelta
from pathlib import Path

MAPPE = Path(__file__).parent
random.seed(2026)

FORNAVNE = ["Anna", "Mikkel", "Sofie", "Jonas", "Freja", "Emil", "Ida", "Noah",
            "Clara", "Oscar", "Laura", "Malthe", "Alma", "Viktor", "Karla"]
EFTERNAVNE = ["Holm", "Kjeldsen", "Bak", "Lindberg", "Toft", "Dahl", "Krogh",
              "Vestergaard", "Friis", "Bruun", "Skov", "Winther", "Juhl",
              "Overgaard", "Brandt"]
BYER = ["Aarhus", "Odense", "Aalborg", "Esbjerg", "Roskilde", "Kolding",
        "Vejle", "Horsens", "Randers", "Viborg", "Silkeborg", "Næstved",
        "Herning", "Helsingør", "Svendborg"]

# Webshoppen "Fjordkaffe" sælger kaffe og kaffeudstyr.
VARER = [
    ("V01", "Håndkværn Fjord", 549),
    ("V02", "Stempelkande 1 liter", 329),
    ("V03", "Espressokande 6 kopper", 279),
    ("V04", "Kaffebønner Etiopien 500 g", 119),
    ("V05", "Kaffebønner Colombia 500 g", 109),
    ("V06", "Filterholder i keramik", 199),
    ("V07", "Elkedel med svanehals", 699),
    ("V08", "Køkkenvægt med timer", 249),
    ("V09", "Papirfiltre 100 stk.", 49),
    ("V10", "Termokop 35 cl", 189),
]

STATUSSER = ["Modtaget", "Pakket", "Afsendt", "Afsendt", "Leveret", "Leveret", "Leveret"]

# Helt almindelige bemærkninger. Gruppen planter selv indirekte angreb
# i dette felt senere (opgave CB6).
BEMAERKNINGER = ["", "", "", "", "Stil pakken ved bagdøren.", "Ring på hos naboen.",
                 "Gave. Ingen faktura i pakken, tak.", "Levering efter kl. 16."]


def lav_kunder():
    kunder = []
    for i in range(15):
        fornavn, efternavn = FORNAVNE[i], EFTERNAVNE[i]
        kunder.append({
            "kunde_id": f"K{i + 1:03d}",
            "navn": f"{fornavn} {efternavn}",
            # example.com er et domæne, der er reserveret til eksempler.
            "email": f"{fornavn.lower()}.{efternavn.lower()}@example.com",
            # Opdigtede numre.
            "telefon": f"55 5{i % 10} {random.randint(10, 99)} {random.randint(10, 99)}",
            "adresse": f"Eksempelvej {random.randint(1, 120)}",
            "by": BYER[i],
        })
    return kunder


def lav_ordrer(kunder):
    ordrer = []
    for n in range(30):
        # De første 15 ordrer giver hver kunde mindst én ordre.
        kunde = kunder[n] if n < 15 else random.choice(kunder)
        antal_varer = random.randint(1, 3)
        linjer, total = [], 0
        for vare_id, navn, pris in random.sample(VARER, antal_varer):
            antal = random.randint(1, 2)
            linjer.append({"vare_id": vare_id, "navn": navn, "antal": antal, "pris": pris})
            total += antal * pris
        ordrer.append({
            "ordrenummer": str(1001 + n),
            "kunde_id": kunde["kunde_id"],
            # En dato mellem 1. september og 14. november 2026.
            "dato": (date(2026, 9, 1) + timedelta(days=random.randint(0, 74))).isoformat(),
            "varer": linjer,
            "beloeb": total,
            "status": random.choice(STATUSSER),
            "bemaerkning": random.choice(BEMAERKNINGER),
        })
    return ordrer


def lav_anmeldelser():
    tekster = [
        "Maler jævnt og er nem at gøre ren.",
        "God kande, men låget sidder lidt løst.",
        "Laver dejlig kaffe. Passer til induktion.",
        "Frugtig og frisk. Køber igen.",
        "Rund og nøddeagtig smag.",
        "Flot håndværk. Holder godt på varmen.",
        "Præcis hældning. Lidt dyr, men pengene værd.",
        "Nem at aflæse. Timeren er praktisk.",
        "Gør, hvad de skal.",
        "Holder kaffen varm i et par timer.",
    ]
    return [
        {"vare_id": vare_id, "vare": navn, "stjerner": random.randint(3, 5), "tekst": tekst}
        for (vare_id, navn, _), tekst in zip(VARER, tekster)
    ]


def gem(filnavn, indhold):
    (MAPPE / filnavn).write_text(
        json.dumps(indhold, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Skrev {filnavn} ({len(indhold)} poster)")


if __name__ == "__main__":
    kunder = lav_kunder()
    gem("kunder.json", kunder)
    gem("ordrer.json", lav_ordrer(kunder))
    gem("anmeldelser.json", lav_anmeldelser())
