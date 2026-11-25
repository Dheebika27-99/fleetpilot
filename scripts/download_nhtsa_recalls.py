"""
Download real vehicle recall notices from the US NHTSA public API (free, no key).

NHTSA is the US road-safety agency. A "recall" is an official notice that a vehicle has
a safety defect, with a summary, the consequence and the fix (remedy).

We download recalls for the US versions of the vehicles in our fleet.
Output: data/docs/nhtsa_recalls.json  (git-ignored, re-download any time)

Run:  python scripts/download_nhtsa_recalls.py
"""

import json
import ssl
import time
from pathlib import Path

import httpx

try:
    # Use the operating system's trusted certificates (same as the browser and curl).
    # Python's own bundle can fail to verify some sites, e.g. api.nhtsa.gov.
    # We never turn verification off.
    import truststore
    VERIFY = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
except ImportError:
    VERIFY = True

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "docs" / "nhtsa_recalls.json"
API = "https://api.nhtsa.gov/recalls/recallsByVehicle"

# US equivalents of our fleet (NHTSA only covers vehicles sold in the US)
VEHICLES = [
    ("ISUZU", "NPR"), ("ISUZU", "NPR-HD"), ("ISUZU", "NQR"),         # ~ Isuzu Elf
    ("HINO", "195"), ("HINO", "268"),                                # ~ Hino Dutro
    ("MITSUBISHI FUSO", "FE"), ("MITSUBISHI FUSO", "ECANTER"),       # ~ Fuso / eCanter
    ("TOYOTA", "PRIUS"), ("TOYOTA", "BZ4X"), ("TOYOTA", "TACOMA"),
    ("NISSAN", "NV200"), ("NISSAN", "NV CARGO"),                     # ~ Nissan Caravan
    ("FORD", "TRANSIT"),                                             # common delivery van
]
YEARS = range(2018, 2025)


def pick(d, *keys):
    """NHTSA field names vary a little in case; take the first one that exists."""
    for k in keys:
        if d.get(k):
            return str(d[k]).strip()
    return ""


def main():
    recalls = {}
    with httpx.Client(timeout=30, verify=VERIFY, headers={"User-Agent": "fleetpilot-portfolio"}) as client:
        for make, model in VEHICLES:
            found = 0
            for year in YEARS:
                try:
                    r = client.get(API, params={"make": make, "model": model, "modelYear": year})
                    r.raise_for_status()
                except httpx.HTTPError as exc:
                    print(f"  skip {make} {model} {year}: {type(exc).__name__}: {str(exc)[:120]}")
                    continue
                for item in r.json().get("results", []) or []:
                    campaign = pick(item, "NHTSACampaignNumber", "nhtsaCampaignNumber")
                    if not campaign:
                        continue
                    rec = recalls.setdefault(campaign, {
                        "campaign": campaign,
                        "manufacturer": pick(item, "Manufacturer", "manufacturer"),
                        "component": pick(item, "Component", "component"),
                        "summary": pick(item, "Summary", "summary"),
                        "consequence": pick(item, "Consequence", "consequence"),
                        "remedy": pick(item, "Remedy", "remedy"),
                        "report_date": pick(item, "ReportReceivedDate", "reportReceivedDate"),
                        "vehicles": [],
                    })
                    label = f"{year} {make.title()} {model}"
                    if label not in rec["vehicles"]:
                        rec["vehicles"].append(label)
                        found += 1
                time.sleep(0.2)          # be polite to a free public API
            print(f"{make:<16} {model:<10} {found:>4} recall-vehicle matches")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(list(recalls.values()), indent=2))
    print(f"\nSaved {len(recalls)} unique recalls to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
