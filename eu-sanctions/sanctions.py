import requests
import pandas as pd
import streamlit as st
import xml.etree.ElementTree as ET
from io import BytesIO
import feedparser
import math

# --- Konfiguration ---
RSS_FEED_URL = "https://webgate.ec.europa.eu/fsd/fsf/public/rss"
CACHE_TTL_SECONDS = 7 * 24 * 3600  # 7 Tage
TIMEOUT_SECONDS = 10

# HTTP-Session
session = requests.Session()

# --- XML Download mit TTL-Caching ---
@st.cache_data(ttl=CACHE_TTL_SECONDS)
def fetch_xml(feed_url: str) -> bytes:
    feed = feedparser.parse(feed_url)
    xml_url = None
    for entry in feed.entries:
        for enc in entry.get('enclosures', []):
            if enc.get('type') == 'application/xml':
                xml_url = enc.get('href')
                break
        if xml_url:
            break
    if not xml_url:
        raise RuntimeError("❌ Kein gültiger XML-Link im Feed gefunden!")
    resp = session.get(xml_url, timeout=TIMEOUT_SECONDS)
    resp.raise_for_status()
    return resp.content

# --- XML Parsing ---
@st.cache_data(ttl=CACHE_TTL_SECONDS)
def lade_sanktionen(xml_bytes: bytes) -> pd.DataFrame:
    tree = ET.parse(BytesIO(xml_bytes))
    root = tree.getroot()
    ns = {"ns": "http://eu.europa.ec/fpi/fsd/export"}
    rows = []
    for ent in root.findall(".//ns:sanctionEntity", ns):
        eu_ref = ent.get("euReferenceNumber", "")
        name_alias = ent.find("ns:nameAlias", ns)
        name = name_alias.get("wholeName") if name_alias is not None else ""
        stype = ent.find("ns:subjectType", ns)
        code = stype.get("code") if stype is not None else ""
        subject_type = "Person" if code.lower() == "person" else "Entity"
        reg = ent.find("ns:regulation", ns)
        pub_date = reg.get("publicationDate") if reg is not None else ""
        programme = reg.get("programme") if reg is not None else ""
        pub_url = ""
        if reg is not None:
            url_elem = ent.find("ns:regulation/ns:publicationUrl", ns)
            pub_url = url_elem.text.strip() if url_elem is not None and url_elem.text else ""
        remark = name_alias.findtext("ns:remark", default="", namespaces=ns) if name_alias is not None else ""
        addr = ent.find("ns:address", ns)
        country = addr.get("countryDescription").title() if addr is not None and addr.get("countryDescription") else ""
        rows.append({
            "EU-Referenznummer": eu_ref,
            "Name": name,
            "Typ": subject_type,
            "Land": country,
            "Publikationsdatum": pub_date,
            "Programm": programme,
            "Bemerkung": remark,
            "Publikations-URL": pub_url
        })
    return pd.DataFrame(rows)

# --- Streamlit UI ---
st.set_page_config(page_title="EU-Sanktionen", layout="wide")
st.title("🇪🇺 EU-Sanktionen Explorer")
st.markdown("Filtere nach Land und Typ – Ergebnis unten.")

# Daten laden
with st.spinner("🔄 Lade Daten..."):
    try:
        xml = fetch_xml(RSS_FEED_URL)
    except RuntimeError as e:
        st.error(str(e))
        st.stop()
    df = lade_sanktionen(xml)
if df.empty:
    st.error("❌ Keine Einträge gefunden.")
    st.stop()

# Sidebar: Filter & Pagination
st.sidebar.header("Filter & Anzeige")
countries = st.sidebar.multiselect("Länder", sorted(df['Land'].unique()))
types = st.sidebar.selectbox("Typ", ["Alle"] + sorted(df['Typ'].unique()))
search = st.sidebar.text_input("Suche Name (ab 3 Zeichen)")
page_size = st.sidebar.selectbox("Einträge pro Seite", [10, 25, 50, 100], index=2)

# Filter anwenden
filtered = df.copy()
if countries:
    filtered = filtered[filtered['Land'].isin(countries)]
if types != "Alle":
    filtered = filtered[filtered['Typ'] == types]
if 0 < len(search) < 3:
    st.sidebar.info("Bitte mindestens 3 Zeichen eingeben.")
elif len(search) >= 3:
    filtered = filtered[filtered['Name'].str.contains(search, case=False, na=False)]

# Pagination
total = len(filtered)
pages = math.ceil(total / page_size)
page = st.sidebar.number_input("Seite", min_value=1, max_value=pages, value=1)
start = (page - 1) * page_size
end = start + page_size
subset = filtered.iloc[start:end]

st.subheader(f"Gefundene Einträge: {total} (Seite {page} von {pages})")

# Darstellung native Streamlit-Tabelle mit klickbaren Links
if not subset.empty:
    disp = subset.copy()
    # Nummerierung ab 1
    disp = disp.reset_index(drop=True)
    disp.index = disp.index + 1

    # Mit LinkColumn wird die URL-Spalte klickbar
    st.dataframe(
        disp,
        use_container_width=True,
        column_config={
            "Publikations-URL": st.column_config.LinkColumn()
        }
    )

# CSV-Download
to_download = filtered.to_csv(index=False).encode('utf-8')
st.download_button("⬇️ CSV herunterladen", to_download, "eu_sanktionen.csv", "text/csv")
