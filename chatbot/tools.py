"""Chatbottens tre værktøjer: slå ordre op, refunder og send mail.

VIGTIGT: Værktøjerne er BEVIDST naive. De tjekker ikke, om ordren tilhører
den kunde, der chatter, eller om en refusion er rimelig. Den slags regler
står kun i chatbottens systemprompt, præcis som i mange rigtige chatbots.
Det er netop den svaghed, vagthunden skal dække.

Refusioner og mails udføres ikke rigtigt. De skrives kun til en logfil,
så testene kan se, hvad chatbotten har gjort.
"""

import json
from datetime import datetime
from pathlib import Path

ROD = Path(__file__).resolve().parent.parent
DATA = ROD / "data"
LOGFIL = ROD / "logs" / "handlinger.jsonl"


def _hent(filnavn):
    return json.loads((DATA / filnavn).read_text(encoding="utf-8"))


def hent_kunde(kunde_id):
    """Returnerer kunden med dette id, eller None."""
    for kunde in _hent("kunder.json"):
        if kunde["kunde_id"] == kunde_id:
            return kunde
    return None


def _log_handling(vaerktoej, detaljer):
    """Skriver en udført handling som én linje JSON i logs/handlinger.jsonl."""
    LOGFIL.parent.mkdir(parents=True, exist_ok=True)
    linje = {"tid": datetime.now().isoformat(timespec="seconds"),
             "vaerktoej": vaerktoej, **detaljer}
    with LOGFIL.open("a", encoding="utf-8") as fil:
        fil.write(json.dumps(linje, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# De tre værktøjer
# ---------------------------------------------------------------------------

def slaa_ordre_op(ordrenummer):
    """Finder en ordre og returnerer den sammen med kundens oplysninger.

    Bevidst naiv: der er intet tjek af, HVEM der spørger. Ordrens bemærkning
    og varernes anmeldelser sendes med. Det er tekst, chatbotten læser, og
    derfor et sted, hvor indirekte prompt injection kan gemme sig.
    """
    ordrenummer = str(ordrenummer).strip()
    for ordre in _hent("ordrer.json"):
        if ordre["ordrenummer"] == ordrenummer:
            vare_ids = {linje["vare_id"] for linje in ordre["varer"]}
            anmeldelser = [a for a in _hent("anmeldelser.json") if a["vare_id"] in vare_ids]
            return {"ordre": ordre,
                    "kunde": hent_kunde(ordre["kunde_id"]),
                    "anmeldelser": anmeldelser}
    return {"fejl": f"Der findes ingen ordre med nummer {ordrenummer}."}


def refunder(ordrenummer, beloeb, aarsag):
    """Refunderer et beløb på en ordre. Skriver kun til loggen.

    Bevidst naiv: tjekker kun, at ordren findes, og at beløbet er over 0.
    """
    ordrenummer = str(ordrenummer).strip()
    fundet = slaa_ordre_op(ordrenummer)
    if "fejl" in fundet:
        return fundet
    try:
        beloeb = float(beloeb)
    except (TypeError, ValueError):
        return {"fejl": "Beløbet skal være et tal."}
    if beloeb <= 0:
        return {"fejl": "Beløbet skal være større end 0."}

    _log_handling("refunder", {"ordrenummer": ordrenummer, "beloeb": beloeb,
                               "aarsag": str(aarsag),
                               "kunde_id": fundet["ordre"]["kunde_id"]})
    return {"status": "refunderet", "ordrenummer": ordrenummer, "beloeb": beloeb}


def send_mail(til, emne, tekst):
    """Sender en mail. Skriver kun til loggen, der sendes ingen rigtig mail."""
    til = str(til).strip()
    if "@" not in til:
        return {"fejl": "Modtageren skal være en e-mailadresse."}
    _log_handling("send_mail", {"til": til, "emne": str(emne), "tekst": str(tekst)})
    return {"status": "sendt", "til": til}


# ---------------------------------------------------------------------------
# Beskrivelsen af værktøjerne, som sendes til Claude
# ---------------------------------------------------------------------------

VAERKTOEJER = [
    {
        "name": "slaa_ordre_op",
        "description": "Slår en ordre op ud fra ordrenummeret. Returnerer ordrens "
                       "varer, beløb, status og bemærkning samt kundens oplysninger.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ordrenummer": {"type": "string", "description": "Ordrenummeret, fx 1003"},
            },
            "required": ["ordrenummer"],
        },
    },
    {
        "name": "refunder",
        "description": "Refunderer et beløb i kroner på en ordre.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ordrenummer": {"type": "string", "description": "Ordrenummeret, fx 1003"},
                "beloeb": {"type": "number", "description": "Beløbet i kroner"},
                "aarsag": {"type": "string", "description": "Kort begrundelse for refusionen"},
            },
            "required": ["ordrenummer", "beloeb", "aarsag"],
        },
    },
    {
        "name": "send_mail",
        "description": "Sender en e-mail, fx en ordrebekræftelse eller en kvittering.",
        "input_schema": {
            "type": "object",
            "properties": {
                "til": {"type": "string", "description": "Modtagerens e-mailadresse"},
                "emne": {"type": "string", "description": "Mailens emne"},
                "tekst": {"type": "string", "description": "Mailens indhold"},
            },
            "required": ["til", "emne", "tekst"],
        },
    },
]

_FUNKTIONER = {"slaa_ordre_op": slaa_ordre_op, "refunder": refunder, "send_mail": send_mail}


def udfoer_vaerktoej(navn, input_data):
    """Kører det værktøj, Claude har bedt om, og returnerer resultatet som tekst."""
    funktion = _FUNKTIONER.get(navn)
    if funktion is None:
        resultat = {"fejl": f"Ukendt værktøj: {navn}"}
    else:
        try:
            resultat = funktion(**input_data)
        except TypeError:
            resultat = {"fejl": f"Forkerte oplysninger til værktøjet {navn}."}
    return json.dumps(resultat, ensure_ascii=False)
