import sys

from chatbot import Chatbot
from chatbot.demo import DemoKlient
from vagthund import Vagthund

UDEN = "--uden" in sys.argv
KUNDE = "K003"


def ny_bot():
    vagt = Vagthund() if UDEN else Vagthund(lag1=True, lag2=True, lag3=True)
    return Chatbot(KUNDE, vagthund=vagt, klient=DemoKlient())


bot = ny_bot()
print(f"Du chatter som {bot.kunde['navn']} ({KUNDE}). Vagthund: {'SLÅET FRA' if UDEN else 'slået til'}.")
print("Skriv /ny for at starte forfra og /afslut for at lukke.\n")

while True:
    try:
        besked = input("Dig: ").strip()
    except (EOFError, KeyboardInterrupt):
        break
    if not besked:
        continue
    if besked == "/afslut":
        break
    if besked == "/ny":
        bot = ny_bot()
        print("Ny samtale.\n")
        continue

    svar = bot.send(besked)
    for kald in svar.vaerktoejskald:
        status = "udført" if kald["udfoert"] else "IKKE udført"
        print(f"   [værktøj] {kald['vaerktoej']} -> {kald['farve']}, {status}")
    for v in svar.vurderinger:
        if v["farve"] != "grøn":
            print(f"   [vagthund lag {v['lag']}] {v['farve']}: {v['begrundelse']}")
    print(f"Fjordkaffe: {svar.tekst}\n")
    