"""Chat med Fjordkaffes kundeservice-chatbot i terminalen.

Start fra projektets rodmappe:

    python -m chatbot.app                 chat som kunde K003
    python -m chatbot.app --kunde K007    chat som en anden kunde
    python -m chatbot.app --besked "Hvor er min ordre 1003?"   én besked og afslut

Kommandoer i chatten:
    /ny          start en ny samtale
    /kunde K005  skift kunde (starter en ny samtale)
    /detaljer    vis eller skjul værktøjskald og vagthundens vurderinger
    /afslut      luk chatten
"""

import argparse
import os
import sys

from vagthund import Vagthund

from .agent import Chatbot


def vis(svar, detaljer):
    if detaljer:
        for kald in svar.vaerktoejskald:
            status = "udført" if kald["udfoert"] else "IKKE udført"
            print(f"   [værktøj] {kald['vaerktoej']}({kald['input']}) -> {kald['farve']}, {status}")
        if svar.stoppet_af_lag:
            print(f"   [vagthund] stoppet af lag {svar.stoppet_af_lag}")
    print(f"Fjordkaffe: {svar.tekst}\n")


def main():
    parser = argparse.ArgumentParser(description="Fjordkaffes kundeservice-chatbot (testmål)")
    parser.add_argument("--kunde", default="K003", help="kunde-id, fx K003")
    parser.add_argument("--besked", help="send én besked og afslut")
    parser.add_argument("--lag1", action="store_true", help="slå vagthundens lag 1 til")
    parser.add_argument("--lag2", action="store_true", help="slå vagthundens lag 2 til")
    parser.add_argument("--lag3", action="store_true", help="slå vagthundens lag 3 til")
    args = parser.parse_args()

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    if not os.getenv("ANTHROPIC_API_KEY"):
        sys.exit("Mangler ANTHROPIC_API_KEY. Kopiér .env.example til .env, og indsæt din nøgle.")

    def ny_bot(kunde_id):
        vagthund = Vagthund(lag1=args.lag1, lag2=args.lag2, lag3=args.lag3)
        return Chatbot(kunde_id, vagthund=vagthund)

    try:
        bot = ny_bot(args.kunde)
    except ValueError as fejl:
        sys.exit(str(fejl))

    if args.besked:
        try:
            vis(bot.send(args.besked), detaljer=True)
        except Exception as fejl:  # fx netværksfejl eller forkert API-nøgle
            sys.exit(f"Fejl: {fejl}")
        return

    detaljer = True
    print(f"Du chatter som {bot.kunde['navn']} ({bot.kunde['kunde_id']}). Skriv /afslut for at lukke.\n")
    while True:
        try:
            besked = input("Dig: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not besked:
            continue
        if besked == "/afslut":
            break
        if besked == "/ny":
            bot = ny_bot(bot.kunde["kunde_id"])
            print("Ny samtale.\n")
            continue
        if besked == "/detaljer":
            detaljer = not detaljer
            print(f"Detaljer er {'slået til' if detaljer else 'slået fra'}.\n")
            continue
        if besked.startswith("/kunde"):
            dele = besked.split()
            try:
                bot = ny_bot(dele[1] if len(dele) > 1 else "")
                print(f"Du chatter nu som {bot.kunde['navn']} ({bot.kunde['kunde_id']}).\n")
            except ValueError as fejl:
                print(f"{fejl}\n")
            continue
        try:
            vis(bot.send(besked), detaljer)
        except Exception as fejl:  # fx netværksfejl eller forkert API-nøgle
            print(f"Fejl: {fejl}\n")


if __name__ == "__main__":
    main()
