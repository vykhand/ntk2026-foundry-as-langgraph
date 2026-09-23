"""Generate the synthetic stand-in program (``fixtures/program.json``).

Deterministic — no randomness — so the fixture is reproducible and reviewable.
Runs at *build time only*; the agent always reads the JSON file.

Design goals (scenario spec §Data plan, §Act-by-act):

* Three conference days, 21–23 Sept 2026, Grand Hotel Bernardin room names.
* Tuesday is engineered for the rehearsal persona (AI + Azure, nothing before
  nine, coffee gap): AI talks in *Emerald* run on 60-minute slots that are
  offset from the 45-minute grid in every other room, so a naive agenda
  produces real, non-obvious clashes for ``clash_checker`` to catch.
* Exactly one planted joke-target talk carries ``synthetic: true``.
* The author's two talks are present so the agent can cross-promote them.
* Every other speaker is fictional (see ``SPEAKERS``).

Regenerate with ``uv run gen-program``. When the real ntk.si export lands, a
separate normaliser replaces this file's output; only ``synthetic: true`` on the
joke talk must survive the swap.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "fixtures" / "program.json"
SCHEMA = ROOT / "fixtures" / "program.schema.json"
TZ = ZoneInfo("Europe/Ljubljana")

CONFERENCE = "NT konferenca 2026"
VENUE = "Grand Hotel Bernardin, Portorož"
DAYS = ("2026-09-21", "2026-09-22", "2026-09-23")

# Placeholder for the ntk.si speaker string of the author (git identity). Replace on data swap.
AUTHOR = "Andy V."


@dataclass(frozen=True)
class Spec:
    title: str
    tags: tuple[str, ...]
    abstract: str
    level: int = 200
    demo_pct: int = 30
    lang: str = "sl"


def s(title, tags, abstract, level=200, demo_pct=30, lang="sl") -> Spec:  # noqa: D103 - terse builder
    return Spec(title, tuple(tags), abstract, level, demo_pct, lang)


# ── Hand-authored pools (Slovene titles; content is generic but plausible) ──

POOLS: dict[str, list[Spec]] = {
    "AI": [
        s(
            "Agenti v praksi: od prototipa do produkcije",
            ("agenti", "llm", "produkcija"),
            "Kaj se zgodi z agentom, ko zapusti prenosnik: identiteta, sledenje, stroški.",
            300,
            50,
        ),
        s(
            "RAG brez halucinacij: vzorci, ki delujejo",
            ("rag", "llm", "iskanje", "vektorji"),
            "Pregled vzorcev za iskanje z generiranjem, ki preživijo stik z realnimi podatki.",
            300,
            40,
        ),
        s(
            "Semantic Kernel ali LangGraph: kdaj kateri",
            ("langgraph", "semantic-kernel", "agenti", "ogrodja"),
            "Primerjava dveh ogrodij za agente na istem primeru, z merjenjem.",
            300,
            60,
        ),
        s(
            "Ocenjevanje agentov: metrike, ki jim lahko verjamete",
            ("evali", "agenti", "kakovost", "metrike"),
            "Kako zgraditi ocenjevanje, ki ga ne moreš preglasovati z lepo demonstracijo.",
            300,
            40,
        ),
        s(
            "Model Context Protocol v podjetju",
            ("mcp", "orodja", "agenti", "integracije"),
            "MCP strežniki, avtentikacija in upravljanje orodij v večjih organizacijah.",
            300,
            50,
        ),
        s(
            "Copilot Studio za neprogramerje",
            ("copilot", "low-code", "copilot-studio"),
            "Zgradimo uporabnega agenta brez vrstice kode in pogledamo, kje so meje.",
            100,
            70,
        ),
        s(
            "Varnost LLM aplikacij: prompt injection in obramba",
            ("varnost", "llm", "prompt-injection"),
            "Napadi na jezikovne modele v praksi in kaj proti njim dejansko pomaga.",
            300,
            40,
        ),
        s(
            "Lokalni modeli na prenosniku: Foundry Local in Ollama",
            ("lokalni-modeli", "foundry-local", "ollama", "slm"),
            "Kdaj je majhen model dovolj in kako ga poganjati brez oblaka.",
            200,
            60,
        ),
        s(
            "Fino uglaševanje malih modelov za slovenščino",
            ("fine-tuning", "slovenščina", "slm"),
            "Postopek, podatki in stroški finega uglaševanja za domači jezik.",
            300,
            30,
        ),
        s(
            "Opazljivost agentov: sledi, metrike, stroški",
            ("opazljivost", "tracing", "app-insights", "agenti"),
            "OpenTelemetry za agente: od klica orodja do računa ob koncu meseca.",
            300,
            50,
        ),
        s(
            "Večagentni sistemi: orkestracija brez kaosa",
            ("agenti", "orkestracija", "vecagentni"),
            "Vzorci delegiranja med agenti in kje se vse skupaj rado sesuje.",
            300,
            40,
        ),
        s(
            "Odgovorna umetna inteligenca v javnem sektorju",
            ("odgovorna-ai", "etika", "javni-sektor"),
            "Kaj od AI zahteva zakonodaja in kako to prevedemo v tehnične kontrole.",
            100,
            0,
        ),
        s(
            "Strukturirani izhodi in klicanje orodij v praksi",
            ("tool-calling", "json", "llm", "strukturirani-izhodi"),
            "Zanesljivi JSON izhodi in klici funkcij pri različnih modelih.",
            200,
            60,
        ),
        s(
            "Govorni agenti v realnem času",
            ("glas", "realtime", "agenti", "voice"),
            "Nizka zakasnitev, prekinjanje in orodja v govornih agentih.",
            300,
            60,
        ),
    ],
    "Azure": [
        s(
            "Azure Container Apps: od nič do produkcije",
            ("container-apps", "kontejnerji", "aca"),
            "Praktična pot do zanesljive aplikacije v Container Apps s skaliranjem na nič.",
            200,
            60,
        ),
        s(
            "AKS v letu 2026: kaj je novega",
            ("aks", "kubernetes"),
            "Novosti v upravljanem Kubernetesu in kdaj ga sploh potrebujete.",
            300,
            30,
        ),
        s(
            "Azure Functions Flex Consumption v praksi",
            ("functions", "serverless"),
            "Novi model plačila po porabi in kaj pomeni za arhitekturo.",
            200,
            50,
        ),
        s(
            "Landing zones za mala podjetja",
            ("landing-zone", "upravljanje", "governance"),
            "Zmanjšana različica priporočil, ki jo lahko izvede ena oseba.",
            200,
            20,
        ),
        s(
            "Bicep ali Terraform? Odgovor je odvisen",
            ("bicep", "terraform", "iac"),
            "Isti projekt, dva jezika za infrastrukturo, iskrena primerjava.",
            200,
            50,
        ),
        s(
            "Azure Developer CLI: en ukaz do oblaka",
            ("azd", "devops", "cli"),
            "azd up, azd deploy in razširitve – hitri cikel od kode do okolja.",
            200,
            70,
        ),
        s(
            "Optimizacija stroškov v Azure brez joka",
            ("finops", "stroški", "cost"),
            "Kje se skriva denar in kako ga najti, preden ga najde finance.",
            100,
            20,
        ),
        s(
            "Managed Identity: konec gesel v kodi",
            ("identity", "entra", "varnost", "managed-identity"),
            "Vsak vir dobi svojo identiteto – vzorci in pasti.",
            200,
            50,
        ),
        s(
            "Azure API Management kot AI prehod",
            ("apim", "ai-gateway", "llm"),
            "Omejevanje, beleženje in usmerjanje klicev na jezikovne modele.",
            300,
            40,
        ),
        s(
            "Durable Functions in dolgotrajni procesi",
            ("durable", "orkestracija", "functions"),
            "Orkestracija, ki preživi ponovni zagon – vzorci in odpravljanje težav.",
            300,
            50,
        ),
        s(
            "Azure Monitor in KQL za razvijalce",
            ("monitor", "kql", "opazljivost"),
            "Poizvedbe, ki jih boste dejansko uporabljali ob incidentu ob dveh zjutraj.",
            200,
            60,
        ),
        s(
            "Hibridni scenariji z Azure Arc",
            ("arc", "hibrid", "infrastruktura"),
            "Upravljanje strežnikov in gruč zunaj Azure z istimi orodji.",
            200,
            40,
        ),
    ],
    "Varnost": [
        s(
            "Zero Trust v praksi: kje začeti",
            ("zero-trust", "varnost", "entra"),
            "Načrt v treh korakih za organizacijo, ki nima varnostne ekipe.",
            200,
            20,
        ),
        s(
            "Entra ID Conditional Access: napredni vzorci",
            ("entra", "conditional-access", "identiteta"),
            "Politike, ki jih uporabniki ne sovražijo in napadalci ne obidejo.",
            300,
            40,
        ),
        s(
            "Defender XDR: lov na grožnje",
            ("defender", "xdr", "threat-hunting"),
            "Napredni lov z KQL in avtomatizacija odzivov.",
            300,
            50,
        ),
        s(
            "Varnost DevOps cevovodov",
            ("devops", "supply-chain", "varnost"),
            "Skrivnosti, odvisnosti in podpisovanje – kje cevovodi puščajo.",
            300,
            40,
        ),
        s(
            "Ribarjenje v dobi generativne AI",
            ("phishing", "socialni-inzeniring", "ai"),
            "Kako AI spreminja napade na ljudi in kaj to pomeni za obrambo.",
            100,
            10,
        ),
        s(
            "Sentinel: avtomatizacija odzivov",
            ("sentinel", "soar", "avtomatizacija"),
            "Playbooki, ki zaprejo incident, preden ga človek sploh vidi.",
            300,
            50,
        ),
        s(
            "Purview in zaščita podatkov",
            ("purview", "dlp", "podatki"),
            "Označevanje, preprečevanje uhajanja in skladnost v Microsoft 365.",
            200,
            30,
        ),
        s(
            "Varnostne kopije, ki jih izsiljevalska programska oprema ne doseže",
            ("backup", "ransomware", "odpornost"),
            "Nespremenljive kopije in preizkušen načrt obnove.",
            200,
            30,
        ),
        s(
            "Penetracijsko testiranje AI aplikacij",
            ("pentest", "ai", "red-team"),
            "Metodologija in orodja za varnostno preverjanje aplikacij z LLM.",
            300,
            50,
        ),
        s(
            "NIS2: kaj mora vedeti razvijalec",
            ("nis2", "skladnost", "regulativa"),
            "Zahteve direktive, prevedene v konkretne razvojne prakse.",
            100,
            0,
        ),
    ],
    "Podatki": [
        s(
            "Microsoft Fabric: ena platforma za vse podatke",
            ("fabric", "analitika", "lakehouse"),
            "Pregled platforme in kdaj se izplača preseliti obstoječe rešitve.",
            100,
            40,
        ),
        s(
            "Lakehouse vzorci v Fabricu",
            ("fabric", "lakehouse", "delta"),
            "Medaljonska arhitektura, inkrementalno nalaganje in upravljanje shem.",
            300,
            50,
        ),
        s(
            "Power BI: modeliranje za hitrost",
            ("power-bi", "dax", "modeliranje"),
            "Zakaj je poročilo počasno in kako ga popraviti brez novega strežnika.",
            200,
            60,
        ),
        s(
            "SQL Server 2025 in vektorsko iskanje",
            ("sql-server", "vektorji", "ai"),
            "Vektorski tip, iskanje po podobnosti in integracija z modeli.",
            300,
            60,
        ),
        s(
            "Analitika v realnem času z Eventstreams",
            ("real-time", "eventstreams", "fabric"),
            "Tokovi dogodkov od naprave do nadzorne plošče v minutah.",
            200,
            60,
        ),
        s(
            "Upravljanje podatkov brez birokracije",
            ("governance", "kakovost", "katalog"),
            "Lastništvo, katalog in kakovost podatkov v majhni ekipi.",
            100,
            10,
        ),
        s(
            "Cosmos DB za AI aplikacije",
            ("cosmos-db", "vektorji", "nosql"),
            "Vektorsko iskanje, pomnilnik agentov in vzorci porazdelitve.",
            300,
            50,
        ),
        s(
            "Migracija podatkov v oblak: lekcije s terena",
            ("migracija", "sql", "oblak"),
            "Kaj je šlo narobe pri desetih migracijah in kako smo se naučili.",
            200,
            10,
        ),
        s(
            "dbt in Fabric: sodobni podatkovni inženiring",
            ("dbt", "fabric", "inzeniring"),
            "Transformacije kot koda, testi podatkov in CI za podatkovne cevovode.",
            300,
            50,
        ),
        s(
            "PostgreSQL na Azure: pgvector in prijatelji",
            ("postgresql", "pgvector", "azure"),
            "Prilagodljiv strežnik, razširitve in vektorsko iskanje v Postgresu.",
            300,
            50,
        ),
    ],
    "Razvoj": [
        s(
            ".NET 10: kaj prinaša novega",
            ("dotnet", "csharp"),
            "Pregled novosti v izvajalnem okolju, jeziku in knjižnicah.",
            200,
            40,
        ),
        s(
            "Aspire: lokalni razvoj porazdeljenih aplikacij",
            ("aspire", "dotnet", "mikrostoritve"),
            "Orkestracija storitev na razvijalskem stroju in pot do oblaka.",
            300,
            70,
        ),
        s(
            "GitHub Copilot: agentni način v praksi",
            ("copilot", "github", "agenti", "produktivnost"),
            "Delegiranje nalog agentu, pregled sprememb in kje mu ne zaupamo.",
            200,
            70,
        ),
        s(
            "Testiranje, ki ga ne sovražite",
            ("testiranje", "kakovost", "tdd"),
            "Testi, ki ujamejo napake in ne lomijo ob vsakem refaktoriranju.",
            200,
            50,
        ),
        s(
            "Blazor v letu 2026",
            ("blazor", "web", "dotnet"),
            "Načini upodabljanja, interaktivnost in kdaj izbrati kaj.",
            200,
            60,
        ),
        s(
            "Minimalni API in navpične rezine",
            ("minimal-api", "arhitektura", "dotnet"),
            "Manj slojev, več jasnosti – organizacija kode po funkcionalnostih.",
            300,
            50,
        ),
        s(
            "Python za .NET razvijalce",
            ("python", "dotnet", "ai"),
            "Prevajalnik navad: okolja, pakiranje, tipi in kjer Python zmaga.",
            100,
            50,
        ),
        s(
            "Čista arhitektura, ki ni pretirana",
            ("arhitektura", "ddd", "clean"),
            "Koliko strukture je dovolj za projekt, ki ga vzdržujeta dva človeka.",
            300,
            20,
        ),
        s(
            "TypeScript za zaledje: Bun, Deno, Node",
            ("typescript", "node", "bun", "deno"),
            "Primerjava izvajalnih okolij in kaj pomenijo za produkcijo.",
            200,
            50,
        ),
        s(
            "Zastavice funkcionalnosti in postopne izdaje",
            ("feature-flags", "devops", "izdaje"),
            "Ločevanje izdaje od objave in varno preizkušanje na produkciji.",
            200,
            40,
        ),
    ],
    "Microsoft 365": [
        s(
            "Copilot v Teams: kaj deluje in kaj ne",
            ("copilot", "teams", "m365"),
            "Iskren pregled po enem letu uporabe v srednje velikem podjetju.",
            100,
            40,
        ),
        s(
            "SharePoint agenti",
            ("sharepoint", "agenti", "copilot"),
            "Agenti nad dokumenti: nastavitev, dovoljenja in omejitve.",
            200,
            60,
        ),
        s(
            "Power Automate: od klik-klik do pro-code",
            ("power-automate", "avtomatizacija", "low-code"),
            "Kdaj tok preraste v kodo in kako ga tja preseliti brez bolečin.",
            200,
            60,
        ),
        s(
            "Intune za hibridno delo",
            ("intune", "naprave", "mdm"),
            "Upravljanje naprav, ki jih nikoli ne vidite v pisarni.",
            200,
            30,
        ),
        s(
            "Exchange Online: varnost pošte v 2026",
            ("exchange", "email", "varnost"),
            "DMARC, zaščita pred prevzemom in kaj se je spremenilo letos.",
            200,
            30,
        ),
        s(
            "Graph API za razvijalce",
            ("graph-api", "m365", "razvoj"),
            "Dovoljenja, spremembe v realnem času in pasti pri velikih najemnikih.",
            300,
            60,
        ),
        s(
            "Aplikacije za Teams z Agents SDK",
            ("teams", "agents-sdk", "boti"),
            "Od bota do agenta v Teams z novim ogrodjem.",
            300,
            60,
        ),
        s(
            "Licenciranje Microsoft 365 brez skrivnosti",
            ("licenciranje", "m365"),
            "Kaj vključuje kateri paket in kako ne plačati dvakrat.",
            100,
            0,
        ),
    ],
    "Infrastruktura": [
        s(
            "Windows Server 2025: novosti",
            ("windows-server", "infrastruktura"),
            "Hotpatching, varnost in vse, kar je zamudilo prejšnjo različico.",
            200,
            30,
        ),
        s(
            "Azure Local v praksi",
            ("azure-local", "stack-hci", "hibrid"),
            "Lokalna infrastruktura, upravljana iz Azure – izkušnje z uvedbo.",
            300,
            40,
        ),
        s(
            "Omrežja v Azure: hub-spoke ali vWAN",
            ("omrezja", "vwan", "hub-spoke"),
            "Topologije, stroški in kdaj je enostavno dovolj.",
            300,
            20,
        ),
        s(
            "Avtomatizacija s PowerShell 7",
            ("powershell", "avtomatizacija", "skripte"),
            "Moduli, testi in objava skript, ki jih uporablja cela ekipa.",
            200,
            60,
        ),
        s(
            "Virtualizacija po VMware: možnosti",
            ("virtualizacija", "hyper-v", "migracija"),
            "Alternative in načrt migracije, ki ne ustavi podjetja.",
            200,
            20,
        ),
        s(
            "Azure Virtual Desktop v 2026",
            ("avd", "vdi", "namizja"),
            "Nove možnosti, stroški in izkušnja uporabnika.",
            200,
            40,
        ),
        s(
            "Upravljanje posodobitev z Azure Update Manager",
            ("update-manager", "posodobitve", "arc"),
            "Ena konzola za posodabljanje strežnikov kjerkoli.",
            200,
            50,
        ),
        s(
            "DNS, certifikati in reči, ki padejo ob petkih",
            ("dns", "certifikati", "pki"),
            "Zgodbe s terena in kontrolni seznam, da se ne ponovijo.",
            100,
            30,
        ),
    ],
    "Poslovno": [
        s(
            "Kako prodati AI projekt upravi",
            ("poslovno", "ai", "uprava"),
            "Argumenti, ki delujejo, in številke, ki jih uprava dejansko razume.",
            100,
            0,
        ),
        s(
            "Merjenje donosnosti AI projektov",
            ("roi", "poslovno", "ai"),
            "Merila, ki ločijo uspešen projekt od dragega eksperimenta.",
            100,
            0,
        ),
        s(
            "Agilnost v regulirani panogi",
            ("agilno", "regulativa", "poslovno"),
            "Kako ohraniti hitrost, ko vsak korak potrebuje podpis.",
            100,
            0,
        ),
    ],
}

# Fixed, hand-placed sessions.
KEYNOTE = s(
    "Otvoritveni keynote: Platforma, agenti in mi",
    ("keynote", "otvoritev", "ai", "platforma"),
    "Uvodni pregled tem konference in smeri, v katero gre platforma.",
    100,
    10,
)

TALK2 = s(
    "Pripelji svojega agenta: LangGraph v produkciji na Foundry Agent Service",
    ("langgraph", "foundry", "agenti", "hosted-agents", "azure", "produkcija", "ai"),
    "Ne prepisuj agenta za produkcijo: prinesi svoj LangGraph, platforma prinese "
    "identiteto, izolacijo, opazljivost in nadzorovano izboljševanje.",
    300,
    50,
)

# Placeholder title for the author's Talk 1 (durable execution + memory); swap for the ntk.si string.
TALK1 = s(
    "Trajno izvajanje in spomin agentov",
    ("agenti", "spomin", "durable", "trajno-izvajanje", "ai"),
    "Druga polovica zgodbe o agentih: stanje izvajanja, pomnilnik in ponovni zagoni.",
    300,
    50,
)

JOKE = s(
    "Digitalna transformacija digitalne transformacije 2.0",
    ("digitalna-transformacija", "sinergija", "paradigma", "poslovno"),
    "Holistična sinergija disruptivnih paradigm v postdigitalni dobi transformacije.",
    100,
    0,
)
JOKE_SPEAKER = "dr. Sinergija Paradigma"

SPEAKERS = [
    "Ana Kovačič",
    "Luka Zupančič",
    "Nina Horvat",
    "Matej Kralj",
    "Petra Golob",
    "Jan Kovač",
    "Maja Turk",
    "Rok Potočnik",
    "Sara Mlakar",
    "Tadej Vidmar",
    "Eva Bizjak",
    "Blaž Kastelic",
    "Katja Oblak",
    "Nejc Hribar",
    "Tina Kobal",
    "Gregor Pirc",
    "Urška Novak",
    "Miha Božič",
    "Špela Jerman",
    "Aleš Kos",
    "Klara Pavlič",
    "Jure Lesjak",
    "Mateja Rozman",
    "Domen Zajc",
    "Neža Kolar",
    "Primož Furlan",
    "Tjaša Kavčič",
    "Anže Medved",
    "Lea Štrukelj",
    "Boštjan Rupnik",
    "Vesna Koren",
    "Tilen Marolt",
    "Zala Cerar",
    "Simon Bregar",
    "Polona Žagar",
    "Uroš Vrhovec",
    "Manca Ambrožič",
    "Gašper Sever",
    "Barbara Lampe",
    "Marko Petek",
]

# ── Day plans: room → list of (start, end, track-or-fixed-spec) ─────────────

G45 = [
    ("09:00", "09:45"),
    ("10:00", "10:45"),
    ("11:00", "11:45"),
    ("12:00", "12:45"),
    ("14:00", "14:45"),
    ("15:00", "15:45"),
    ("16:00", "16:45"),
    ("17:00", "17:45"),
]
G60 = [
    ("09:00", "10:00"),
    ("10:15", "11:15"),
    ("11:30", "12:30"),
    ("14:00", "15:00"),
    ("15:15", "16:15"),
    ("16:30", "17:30"),
]
MON = [("14:15", "15:00"), ("15:15", "16:00"), ("16:15", "17:00")]
WED = G45[:6]

Fixed = tuple[Spec, str]  # (spec, speaker)
SlotPlan = tuple[str, str, object]  # (start, end, track name | Fixed)

PLAN: dict[str, dict[str, list]] = {
    "2026-09-21": {
        "Emerald": [("13:00", "14:00", (KEYNOTE, "Katarina Zupan"))] + [(a, b, "Razvoj") for a, b in MON],
        "Europa": [(a, b, "Infrastruktura") for a, b in MON],
        "Adria": [(a, b, "Microsoft 365") for a, b in MON],
        "Nautica": [
            (MON[0][0], MON[0][1], "Varnost"),
            (MON[1][0], MON[1][1], "Varnost"),
            (MON[2][0], MON[2][1], "Podatki"),
        ],
    },
    "2026-09-22": {
        "Emerald": [(a, b, "AI") for a, b in G60[:3]]
        + [("14:00", "15:00", (TALK2, AUTHOR))]
        + [(a, b, "AI") for a, b in G60[4:]],
        "Europa": [(a, b, t) for (a, b), t in zip(G45, ["AI", "Azure"] * 4, strict=True)],
        "Adria": [(a, b, "Azure") for a, b in G45],
        "Nautica": [(a, b, "Varnost") for a, b in G45],
        "Mediteranea": [(a, b, "Podatki") for a, b in G45],
        "Istra": [(a, b, "Razvoj") for a, b in G45[:4]] + [(a, b, "Microsoft 365") for a, b in G45[4:]],
        "Tartini": [
            ("10:00", "10:45", "Poslovno"),
            ("11:00", "11:45", (JOKE, JOKE_SPEAKER)),
            ("12:00", "12:45", "Poslovno"),
            ("14:00", "14:45", "Poslovno"),
        ],
    },
    "2026-09-23": {
        "Emerald": [
            ("09:00", "09:45", "AI"),
            ("10:00", "10:45", "AI"),
            ("11:00", "12:00", (TALK1, AUTHOR)),
            ("12:00", "12:45", "AI"),
            ("14:00", "14:45", "AI"),
            ("15:00", "15:45", "AI"),
        ],
        "Europa": [(a, b, "Infrastruktura") for a, b in WED[:5]],
        "Adria": [(a, b, "Razvoj") for a, b in WED[:3]] + [(WED[3][0], WED[3][1], "Microsoft 365")],
        "Nautica": [(WED[0][0], WED[0][1], "Podatki")],
    },
}


def _iso(day: str, hhmm: str) -> str:
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime.combine(datetime.fromisoformat(day).date(), time(h, m), tzinfo=TZ).isoformat()


def build() -> dict:
    pools = {track: list(specs) for track, specs in POOLS.items()}
    talks: list[dict] = []
    speaker_cursor = 0
    dropped: list[str] = []

    for day, rooms in PLAN.items():
        for room, slots in rooms.items():
            for start, end, what in slots:
                if isinstance(what, tuple):
                    spec, speaker = what
                    track = "Keynote" if spec is KEYNOTE else ("Poslovno" if spec is JOKE else "AI")
                else:
                    track = what
                    if not pools[track]:
                        dropped.append(f"{day} {room} {start} ({track}: pool exhausted)")
                        continue
                    spec = pools[track].pop(0)
                    speaker = SPEAKERS[speaker_cursor % len(SPEAKERS)]
                    speaker_cursor += 1
                talks.append(
                    {
                        "id": "",  # assigned after chronological sort
                        "title": spec.title,
                        "speaker": speaker,
                        "room": room,
                        "start": _iso(day, start),
                        "end": _iso(day, end),
                        "track": track,
                        "level": spec.level,
                        "demo_pct": spec.demo_pct,
                        "lang": spec.lang,
                        "synthetic": spec is JOKE,
                        "tags": list(spec.tags),
                        "abstract": spec.abstract,
                    }
                )

    leftovers = {t: [x.title for x in p] for t, p in pools.items() if p}
    talks.sort(key=lambda t: (t["start"], t["room"]))
    for n, talk in enumerate(talks, start=1):
        talk["id"] = f"t-{n:03d}"

    meta = {
        "source": "synthetic",
        "generated_at": "2026-09-05",
        "conference": CONFERENCE,
        "venue": VENUE,
        "timezone": "Europe/Ljubljana",
        "days": list(DAYS),
        "note": (
            "Synthetic stand-in generated by scripts/gen_program.py. Speakers are fictional except "
            f"the author placeholder '{AUTHOR}'. Exactly one talk carries synthetic=true (the planted "
            "joke target). Replace with the ntk.si export when it lands; keep the joke talk."
        ),
    }
    if dropped or leftovers:
        print("gen_program: note —", {"dropped_slots": dropped, "unplaced": leftovers}, file=sys.stderr)
    return {"meta": meta, "talks": talks}


def validate(program: dict) -> None:
    try:
        import jsonschema
    except ImportError:  # pragma: no cover - dev dependency
        print("gen_program: jsonschema not installed, skipping validation", file=sys.stderr)
        return
    jsonschema.validate(program, json.loads(SCHEMA.read_text(encoding="utf-8")))


def main() -> None:
    program = build()
    validate(program)
    OUT.write_text(json.dumps(program, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    by_day: dict[str, int] = {}
    for talk in program["talks"]:
        by_day[talk["start"][:10]] = by_day.get(talk["start"][:10], 0) + 1
    joke = [t["id"] for t in program["talks"] if t["synthetic"]]
    print(f"wrote {OUT.relative_to(ROOT)}: {len(program['talks'])} talks {by_day}; synthetic={joke}")


if __name__ == "__main__":
    main()
