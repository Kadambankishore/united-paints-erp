"""
extractor/pdf_extractor.py
Production-hardened UC/UP invoice PDF extractor.
Integrated from ingest/extractor.py (the original ERP build extractor).
"""
import re
import pdfplumber
from collections import defaultdict
from typing import Optional, List, Dict, Any

# ── Seller GSTINs ─────────────────────────────────────────────────────────
SELLER_GSTIN_UC = "33ABRPA4038N1ZI"
SELLER_GSTIN_UP = "33AWOPS1931N1Z0"
ALL_SELLER_GSTINS = {SELLER_GSTIN_UC, SELLER_GSTIN_UP}

# ── ASRK dealer GSTIN → party_uid ────────────────────────────────────────
ASRK_GSTIN_UID = {
    "33BPVPM9524C1ZM": "CBE-ARASAN-01",
    "33BDQPS2381Q1ZO": "TRY-SRIMAN-01",
    "33CLTPR0053C1Z8": "MDU-RAJ-01",
    "33AAMFK8693B1Z4": "ERD-KISHOR-01",
}

# ── City abbreviation table ───────────────────────────────────────────────
CITY_ABBR = {
    "COIMBATORE":"CBE","MADURAI":"MDU","ERODE":"ERD","TRICHY":"TRY",
    "TIRUCHIRAPPALLI":"TRY","TIRUNELVELI":"TVL","DINDIGUL":"DGL",
    "THENI":"THN","SATTUR":"STR","VIRUDHUNAGAR":"VDN","RAJAPALAYAM":"RJP",
    "PARAMAKUDI":"PAR","ELUMALAI":"ELU","KANYAKUMARI":"KAN","PALANI":"PLN",
    "TIRUPUR":"TUP","TENKASI":"TEN","ARUPPUKKOTTAI":"ARU","THIRUMANGALAM":"THI",
    "BANGALORE":"BLR","BENGALURU":"BLR","POLLACHI":"PLI","THANJAVUR":"THA",
    "KARUR":"KAR","PUDUKOTTAI":"PUK","PUDUKKOTTAI":"PUK","KUMBAKONAM":"KUM",
    "NAGAPATTINAM":"NAG","RAMANATHAPURAM":"RAM","SIVAGANGAI":"SIV",
    "USILAMPATTI":"USL","DEVAKOTTAI":"DEV","KARAIKUDI":"KAK","ARANTHANGI":"ARA",
    "CUMBUM":"CUM","ODDANCHATRAM":"ODC","AUNDIPATTI":"AND","VIRALIMALAI":"VIR",
    "MELUR":"MEL","TIRUCHENDUR":"TIR","KOVILPATTI":"KOV","UDANGUDI":"UDA",
    "SAYALKUDI":"SAY","SIVAKASI":"SIK","SRIVILLIPUTHUR":"SRV","VALLIYOOR":"VAL",
    "KALLAL":"KAL","SINGAMPUNARI":"SIN","ALANGUDI":"ALA","ILAYANGUDI":"ILA",
    "MIMISAL":"MIM","KILAKARAI":"KIL","CHINNAMANUR":"CHI","DHARAPURAM":"DHA",
    "BODINAYAKKANUR":"BOD","GUDALUR":"GUD","PONNAMARAVATHI":"PON",
    "AMBASAMUDRAM":"AMB","THOOTHUKUDI":"THO","TUTICORIN":"TUT",
    "NAGERCOIL":"NAG","CHENNAI":"CHN","T.KALLUPATTI":"TKA",
    "MUTHUKULATHUR":"MUT","MUDUKULATHUR":"MUT","CHELLIAMPATTI":"CHE",
    "KOLARPATTI":"KOL","SHOLAVANDAN":"SHO","PERAIYUR":"PER",
    "PERIYAKULAM":"PRK","THALAVAIPURAM":"THA","KARIYAPATTI":"KAR",
    "SANKARAMPATTI":"SAN","VILATTIKULAM":"VIL","VRIDDHACHALAM":"VRD",
    "ULUNDURPET":"ULU","SANGARAPURAM":"SAN","KODAI ROAD":"KOD",
    "TIRUPATTUR":"TIP","PARAMATHIVELUR":"PAR","MADUKKUR":"MAD",
    "MANDAPAM":"MAN","THIRUMAYAM":"THI","THIRUTHANGAL":"THI",
}

# ── Rep map ───────────────────────────────────────────────────────────────
REP_MAP = {
    "VIJAY":   ("Vijay",                  "Sattur Region",               "VJ-STN"),
    "U.K":     ("U. Kannan",              "Pollachi Region",             "UK-WCN"),
    "L.S":     ("L. Sreenivasan",         "West TN",                     "LS-WTN"),
    "L.S.C":   ("L. Sreenivasan (Covai)", "CBE Region",                  "LSC-CBE"),
    "BABU":    ("Babu",                   "Kerala",                      "BA-KER"),
    "M.BABU":  ("Babu",                   "Kerala",                      "BA-KER"),
    "TDK":     ("T. Dhinakaran",          "Chennai",                     "TDK-CHN"),
    "DEEPAK":  ("Deepak",                 "Bangalore (Karnataka)",        "DP-KRN"),
    "PHONE":   ("Direct Order",           "Direct / Walk-in Orders",     "DI-DIR"),
    "DIRECT":  ("Direct Order",           "Direct / Walk-in Orders",     "DI-DIR"),
    "AAKASH":  ("Aakash (Mktg Head)",     "Internal – Management Orders","AK-MGT"),
    "AKASH":   ("Aakash (Mktg Head)",     "Internal – Management Orders","AK-MGT"),
    "A.A":     ("Aakash (Mktg Head)",     "Internal – Management Orders","AK-MGT"),
    "UT-BGL":  ("Universal Tradings BLR", "Bangalore (Karnataka)",       "UT-BLR"),
    "UT-BLR":  ("Universal Tradings BLR", "Bangalore (Karnataka)",       "UT-BLR"),
}

# ── In-memory party UID state ─────────────────────────────────────────────
_gstin_uid_map: dict = {}
_name_uid_map:  dict = {}
_uid_counter: defaultdict = defaultdict(int)


def _city_code(place: str) -> str:
    p = re.sub(r"-\d[\d\s]*$", "", place.strip().upper()).strip()
    p = re.sub(r"\s*(DIST|TOWN|CITY)$", "", p).strip()
    if p in CITY_ABBR:
        return CITY_ABBR[p]
    first = p.split()[0] if p else "UNK"
    return CITY_ABBR.get(first, first[:3] if first else "UNK")


def _make_party_uid(gstin: str, buyer_name: str, place: str) -> str:
    if gstin and gstin in ASRK_GSTIN_UID:
        uid = ASRK_GSTIN_UID[gstin]
        _gstin_uid_map[gstin] = uid
        return uid
    if gstin and gstin in _gstin_uid_map:
        return _gstin_uid_map[gstin]
    cc  = _city_code(place)
    fn  = re.sub(r"[^A-Z0-9]", "", (buyer_name or "").split()[0].upper() if (buyer_name or "").split() else "UNK")[:6]
    key = f"{cc}-{fn}"
    if key in _name_uid_map:
        return _name_uid_map[key]
    _uid_counter[key] += 1
    uid = f"{key}-{_uid_counter[key]:02d}"
    _name_uid_map[key] = uid
    if gstin:
        _gstin_uid_map[gstin] = uid
    return uid


def _dedup(s: str) -> str:
    s = s.strip().rstrip(",").strip()
    words = s.split()
    n = len(words)
    for half in range(1, n // 2 + 1):
        if words[:half] == words[half: half * 2]:
            return " ".join(words[:half])
    return s


def _parse_rep(ord_raw: str) -> tuple:
    r = (ord_raw or "").strip().upper().replace(" ", "")
    for code, (name, area, ac) in REP_MAP.items():
        if r == code.replace(" ", "").upper():
            return code, name, area, ac
    return "DIRECT", "Direct Order", "Direct / Walk-in Orders", "DI-DIR"


def _parse_products(lines: list) -> list:
    pat = re.compile(
        r"^(\d+)\s+(.+?)\s+(\d+%)\s+(\d{8})\s+(\S+)\s+(\S+)\s+(\S+)\s+([\d,]+(?:\.\d+)?)\s+([\d,]+(?:\.\d+)?)$"
    )
    products = []
    for line in lines:
        m = pat.match(line.strip())
        if m:
            sno, prod, gst, hsn, pack, qty, items, rate, amt = m.groups()
            try:
                products.append({
                    "sno": sno, "product": prod.strip(),
                    "gst_pct": gst, "hsn": hsn,
                    "packing": pack, "quantity": qty, "items": items,
                    "rate": float(rate.replace(",", "")),
                    "amount": float(amt.replace(",", "")),
                })
            except ValueError:
                pass
    return products


def _parse_page(text: str, pdf_page: int, source_pdf: str, company: str, seller_gstin: str) -> Optional[dict]:
    """Parse one PDF page into an invoice dict. Returns None for blank pages."""
    irn_m   = re.search(r"IRN\s*:\s*([a-f0-9]{64})", text)
    ack_m   = re.search(r"Ack No\.\:\s*(\d+)", text)
    eway_m  = re.search(r"E-?Way Bill[:\s]+(\d{12})", text)
    inv_m   = re.search(r"Inv\.No\.\:\s*(\d+)", text)
    date_m  = re.search(r"Date\s*:\s*(\d{2}-\d{2}-\d{4})", text)
    place_m = re.search(r"Place\s*:\s*([^\n]+)", text)
    state_m = re.search(r"State\s*:\s*([^\n]+)", text)

    inv_no   = inv_m.group(1)  if inv_m   else ""
    inv_date = date_m.group(1) if date_m  else ""
    place    = (place_m.group(1).strip().rstrip(",").strip() if place_m else "")
    state    = (state_m.group(1).strip() if state_m else "")

    if not inv_no:   # MF-05: skip blank/non-invoice pages
        return None

    irn  = irn_m.group(1)  if irn_m  else ""
    ack  = ack_m.group(1)  if ack_m  else ""
    eway = eway_m.group(1) if eway_m else ""

    parts      = inv_date.split("-") if inv_date else ["01","07","2026"]
    month_s    = parts[1] if len(parts) > 1 else "07"
    year_s     = parts[2] if len(parts) > 2 else "2026"
    mon_name   = ["","Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][int(month_s)]
    month_label= f"{mon_name}-{year_s}"

    all_gstins  = re.findall(r"GSTIN\s*[:：]\s*(\d{2}[A-Z0-9]{13})", text)
    buyer_gstin = next((g for g in all_gstins if g not in ALL_SELLER_GSTINS), "")

    buyer_name = buyer_address = city_pincode = ""
    addr_lines: list = []
    in_buyer = False
    for line in text.split("\n"):
        line = line.strip()
        if "Billed to Buyer" in line or "LORRY COPY" in line:
            in_buyer = True; continue
        if not in_buyer: continue
        if re.search(r"^SNo\s+Product|^(Phone|State|GSTIN)\s*:|Bank Name|CGST|SGST", line, re.I): break
        if re.match(r"^(Date|Place|State)\s*:", line, re.I): continue
        cleaned = _dedup(line.split("Inv.No.")[0] if "Inv.No." in line else line)
        if cleaned:
            addr_lines.append(cleaned)

    if addr_lines:
        buyer_name = addr_lines[0]
        for part in addr_lines[1:]:
            if re.search(r"\d{3}[\s\-]\d{3}", part) and not city_pincode:
                city_pincode = part
            buyer_address = (buyer_address + ", " + part).lstrip(", ")

    if not city_pincode:
        city_pincode = place

    ord_m   = re.search(r"Ord\.No\.\s*:\s*([^\n]+)", text)
    lorry_m = re.search(r"Lorry\s*:\s*([^\n]+)", text)
    odate_m = re.search(r"Ord\.Date[:\s]+(\d{2}-\d{2}-\d{4})", text)
    ord_raw  = (ord_m.group(1).strip() if ord_m else "").split("Ord.Date")[0].strip()
    lorry    = (lorry_m.group(1).strip() if lorry_m else "").split("GRAND")[0].strip()
    ord_date = odate_m.group(1).strip() if odate_m else inv_date
    _, rep_name, geo_area, area_code = _parse_rep(ord_raw)

    flat   = text.replace("\n", " ")
    tax_m  = re.search(r"(?:CGST|SGST)\s*@\s*[\d.]+%\s+on\s+([\d,]+(?:\.\d+)?)", flat)
    cgst_m = re.search(r"CGST\s*@\s*[\d.]+%\s+on\s+[\d,\.]+\s+([\d,]+(?:\.\d+)?)", flat)
    igst_m = re.search(r"IGST\s*@\s*[\d.]+%\s+on\s+([\d,]+(?:\.\d+)?)\s+([\d,]+(?:\.\d+)?)", flat)
    gt_m   = re.search(r"GRAND TOTAL\s+([\d,]+(?:\.\d+)?)", flat)
    tot_m  = re.search(r"Total\s*-->\s*\S+\s+([\d,]+(?:\.\d+)?)", flat)

    taxable = float(tax_m.group(1).replace(",","")) if tax_m else \
              float(tot_m.group(1).replace(",","")) if tot_m else 0.0
    cgst    = float(cgst_m.group(1).replace(",","")) if cgst_m else 0.0
    igst    = float(igst_m.group(2).replace(",","")) if igst_m else 0.0
    gt      = float(gt_m.group(1).replace(",","")) if gt_m else (taxable + cgst * 2 + igst)

    products = _parse_products(text.split("\n"))
    party_uid = _make_party_uid(buyer_gstin, buyer_name, place)

    return {
        "company":       company,
        "source_pdf":    source_pdf,
        "pdf_page":      pdf_page,
        "month_label":   month_label,
        "inv_no":        inv_no,
        "inv_date":      inv_date,
        "month":         month_s,
        "year":          year_s,
        "irn":           irn,
        "ack_no":        ack,
        "ewaybill":      eway,
        "buyer_name":    buyer_name,
        "buyer_address": buyer_address,
        "place":         place,
        "state":         state,
        "buyer_gstin":   buyer_gstin,
        "party_uid":     party_uid,
        "products":      products,
        "grand_total":   gt,
        "taxable_value": taxable,
        "cgst":          cgst,
        "igst":          igst,
        "sgst":          cgst,   # SGST = CGST for intrastate
        "rep_name":      rep_name,
        "area_code":     area_code,
        "ord_no_raw":    ord_raw,
        "lorry":         lorry,
    }


def extract_invoices_from_pdf(pdf_path: str, company: str) -> List[Dict[str, Any]]:
    """
    Main function: reads a UC/UP invoice PDF and returns list of invoice dicts.
    Uses the production-hardened parser — same one used to build Erp_Final.html.
    """
    seller_gstin = SELLER_GSTIN_UC if company == "UC" else SELLER_GSTIN_UP
    invoices = []
    skipped  = 0

    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        print(f"  📄 Reading {total} pages ({company}) from {pdf_path} ...")

        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            result = _parse_page(text, page_num, pdf_path, company, seller_gstin)
            if result:
                invoices.append(result)
            else:
                skipped += 1

    print(f"  ✅ Extracted {len(invoices)} invoices ({skipped} blank pages skipped)")
    return invoices
