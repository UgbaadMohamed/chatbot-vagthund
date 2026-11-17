"""Selve chatbotten: en AI-agent, der kan svare kunder og bruge værktøjer.

Sådan virker én besked fra kunden:

    1. Vagthunden tjekker beskeden               (lag 1)
    2. Claude læser beskeden og beslutter, om et værktøj skal bruges
    3. Vagthunden tjekker hvert værktøjskald     (lag 3), før det udføres
    4. Claude får resultatet og skriver et svar  (trin 2-4 kan gentages)
    5. Vagthunden tjekker svaret                 (lag 2), før kunden ser det

Med vagthundens skelet er alle tjek grønne, så chatbotten er ubeskyttet.
"""

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime

from vagthund import GROEN, GUL, Vagthund

from . import tools
from .prompt import byg_systemprompt

# Modellen kan skiftes i .env med CHATBOT_MODEL.
MODEL = os.getenv("CHATBOT_MODEL", "claude-haiku-5-5")
MAKS_TRIN = 6  # Højst så mange runder med værktøjer pr. besked.

SVAR_BLOKERET = "Det kan jeg desværre ikke hjælpe med."
SVAR_TIL_MENNESKE = "Jeg har sendt din henvendelse videre til en medarbejder, som vender tilbage til dig."
SVAR_FEJL = "Beklager, jeg kunne ikke færdiggøre din henvendelse. Prøv igen."


@dataclass
class Svar:
    """Alt, hvad der skete ved én besked. Bruges af testscriptet og dashboardet."""
    tekst: str                                          # det, kunden ser
    vaerktoejskald: list = field(default_factory=list)  # alle forsøg på at bruge værktøjer
    vurderinger: list = field(default_factory=list)     # vagthundens vurderinger
    stoppet_af_lag: int | None = None                   # 1, 2 eller None


class Chatbot:
    def __init__(self, kunde_id, vagthund=None, klient=None, model=MODEL):
        self.kunde = tools.hent_kunde(kunde_id)
        if self.kunde is None:
            raise ValueError(f"Ukendt kunde-id: {kunde_id}")
        self.vagthund = vagthund or Vagthund()
        self.model = model
        self.system = byg_systemprompt(self.kunde)
        self.historik = []   # samtalen indtil nu, i det format Claude API bruger
        self.afventer = []   # gule handlinger, der venter på et menneske
        self._klient = klient

    @property
    def klient(self):
        # Klienten oprettes først, når den skal bruges. Den læser ANTHROPIC_API_KEY.
        if self._klient is None:
            import anthropic
            self._klient = anthropic.Anthropic()
        return self._klient

    def send(self, besked):
        """Sender én besked fra kunden og returnerer et Svar."""
        svar = Svar(tekst="")

        # --- Lag 1: tjek kundens besked, før Claude ser den -----------------
        v = self.vagthund.tjek_besked(besked, self.kunde)
        svar.vurderinger.append(asdict(v))
        if v.farve != GROEN:
            svar.tekst = SVAR_TIL_MENNESKE if v.farve == GUL else SVAR_BLOKERET
            svar.stoppet_af_lag = 1
            self._log(besked, svar)
            return svar

        self.historik.append({"role": "user", "content": besked})
        tekst = ""

        for _ in range(MAKS_TRIN):
            respons = self.klient.messages.create(
                model=self.model,
                max_tokens=1024,
                system=self.system,
                tools=tools.VAERKTOEJER,
                messages=self.historik,
            )
            # Claudes svar består af blokke: tekst, værktøjskald og evt. andre typer.
            # Blokkene gemmes uændret i historikken, så de kan sendes med næste gang.
            # Tomme tekstblokke fjernes, fordi API'et afviser dem.
            blokke = [b for b in respons.content
                      if not (b.type == "text" and not b.text.strip())]
            tekst = "".join(b.text for b in blokke if b.type == "text").strip()
            self.historik.append({"role": "assistant",
                                  "content": blokke or "(intet svar)"})

            if respons.stop_reason != "tool_use":
                break

            # --- Lag 3: tjek hvert værktøjskald, før det udføres -------------
            resultater = []
            for blok in blokke:
                if blok.type != "tool_use":
                    continue
                resultat = self._haandter_vaerktoej(besked, blok, svar)
                resultater.append({"type": "tool_result",
                                   "tool_use_id": blok.id,
                                   "content": resultat})
            self.historik.append({"role": "user", "content": resultater})
        else:
            # Løkken løb tør for runder uden et færdigt svar.
            tekst = SVAR_FEJL
            self.historik.append({"role": "assistant", "content": tekst})

        # --- Lag 2: tjek svaret, før kunden ser det -------------------------
        v = self.vagthund.tjek_svar(tekst, self.kunde)
        svar.vurderinger.append(asdict(v))
        if v.farve != GROEN:
            tekst = SVAR_TIL_MENNESKE if v.farve == GUL else SVAR_BLOKERET
            svar.stoppet_af_lag = 2
            # Det stoppede svar fjernes også fra historikken.
            self.historik[-1] = {"role": "assistant", "content": tekst}

        svar.tekst = tekst or SVAR_FEJL
        self._log(besked, svar)
        return svar

    def _haandter_vaerktoej(self, besked, blok, svar):
        """Spørger vagthunden og udfører kun værktøjet, hvis svaret er grønt."""
        navn, input_data = blok.name, blok.input
        v = self.vagthund.tjek_handling(besked, navn, input_data, self.kunde)
        svar.vurderinger.append(asdict(v))
        kald = {"vaerktoej": navn, "input": input_data, "farve": v.farve,
                "begrundelse": v.begrundelse, "udfoert": False}

        if v.farve == GROEN:
            resultat = tools.udfoer_vaerktoej(navn, input_data)
            kald["udfoert"] = True
        elif v.farve == GUL:
            self.afventer.append({"vaerktoej": navn, "input": input_data,
                                  "begrundelse": v.begrundelse})
            resultat = ("AFVENTER GODKENDELSE: Handlingen er ikke udført. "
                        "En medarbejder skal godkende den først. Fortæl kunden det.")
        else:
            resultat = ("BLOKERET: Handlingen er ikke udført og må ikke udføres. "
                        "Fortæl kunden, at du ikke kan hjælpe med det.")

        kald["resultat"] = resultat
        svar.vaerktoejskald.append(kald)
        return resultat

    def _log(self, besked, svar):
        """Gemmer hele turen som én linje i logs/samtaler.jsonl."""
        logfil = tools.LOGFIL.parent / "samtaler.jsonl"
        logfil.parent.mkdir(parents=True, exist_ok=True)
        linje = {"tid": datetime.now().isoformat(timespec="seconds"),
                 "kunde_id": self.kunde["kunde_id"], "besked": besked, **asdict(svar)}
        with logfil.open("a", encoding="utf-8") as fil:
            fil.write(json.dumps(linje, ensure_ascii=False) + "\n")