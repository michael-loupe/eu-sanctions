import requests
import pandas as pd
import streamlit as st
import xml.etree.ElementTree as ET
from io import BytesIO
import feedparser

# --- Konfiguration ---
RSS_FEED_URL = "https://webgate.ec.europa.eu/fsd/fsf/public/rss"
CACHE_TTL_SECONDS = 7 * 24 * 3600  # 7 Tage
TIMEOUT_SECONDS = 10

# Wiederverwendbare HTTP-Session
session = requests.Session()

# --- XML Download mit TTL-Caching ---
@st.cache_data(ttl=CACHE_TTL_SECONDS)
def fetch_xml(feed_url: str) -> bytes:
    """
    Lädt die XML-Datei aus dem RSS-Feed unter Verwendung einer Session.
    Wird über TTL automatisch neu geladen, wenn abgelaufen.
    """
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
    try:
        response = session.get(xml_url, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.content
    except requests.exceptions.RequestException as err:
        raise RuntimeError(f"❌ Fehler beim Download der XML-Datei: {err}")

# --- XML Parsing ---
@st.cache_data(ttl=CACHE_TTL_SECONDS)
def lade_sanktionen(xml_content: bytes) -> pd.DataFrame:
    tree = ET.parse(BytesIO(xml_content))
    root = tree.getroot()
    ns = {"ns": "http://eu.europa.ec/fpi/fsd/export"}
    sanktionen = []

    for entity in root.findall(".//ns:sanctionEntity", ns):
        # EU Reference Number direkt vom Element-Attribut
        eu_ref = entity.get("euReferenceNumber", "Unbekannt")
        # Name
        name_alias = entity.find("ns:nameAlias", ns)
        name = name_alias.get("wholeName", "Unbekannt") if name_alias is not None else "Unbekannt"
        # Typ (Person oder Entity)
        stype = entity.find("ns:subjectType", ns)
        code = stype.get("code", "Unbekannt") if stype is not None else "Unbekannt"
        subject_type = "Person" if code.lower() == "person" else "Entity" if code.lower() == "enterprise" else code.title()
        # Regulation node for publication
        reg = entity.find("ns:regulation", ns)
        pub_date = reg.get("publicationDate", "") if reg is not None else ""
        # Programm
        programme = reg.get("programme", "Unbekannt") if reg is not None else "Unbekannt"
        # Bemerkung
        remarks = name_alias.findtext("ns:remark", default="", namespaces=ns) if name_alias is not None else ""
        # Publikations-URL
        pub_url = ""
        if reg is not None:
            url_elem = reg.find("ns:publicationUrl", ns)
            if url_elem is not None and url_elem.text:
                pub_url = url_elem.text.strip()

        # Land
        country = "Unbekannt"
        addr = entity.find("ns:address", ns)
        if addr is not None:
            desc = addr.get("countryDescription", "").strip()
            if desc:
                country = desc.title()

        sanktionen.append({
            'EU-Referenznummer': eu_ref,
            'Name': name,
            'Typ': subject_type,
            'Land': country,
            'Publikationsdatum': pub_date,
            'Programm': programme,
            'Bemerkung': remarks,
            'Publikations-URL': pub_url
        })

    df = pd.DataFrame(sanktionen)
    df['Land'] = df['Land'].fillna('Unbekannt')
    return df

# --- Streamlit UI ---
st.set_page_config(page_title="EU-Sanktionen", layout="wide")
st.title("🇪🇺 EU-Sanktionen Explorer")
st.markdown("Filtere nach Land und Typ – Ergebnisanzeige unten.")

# Daten laden
with st.spinner("🔄 Lade XML-Daten..."):
    try:
        xml_bytes = fetch_xml(RSS_FEED_URL)
    except RuntimeError as e:
        st.error(str(e)); st.stop()
    df = lade_sanktionen(xml_bytes)

if df.empty:
    st.error("❌ Keine Daten geladen."); st.stop()

# Übersicht: Gesamt und nach Typ
st.subheader("📊 Übersicht")
col_t, col_tot = st.columns([3,1])
for t, cnt in df['Typ'].value_counts().items():
    label = t
    formatted = f"{cnt:,}".replace(",", ".")
    col_t.metric(label=label, value=formatted)
total = len(df)
col_tot.metric(label="Gesamt Einträge", value=f"{total:,}".replace(",", "."))

# Session-State Defaults
if "land_filter" not in st.session_state:
    st.session_state["land_filter"] = []
if "typ_filter" not in st.session_state:
    st.session_state["typ_filter"] = "Alle"

# Reset-Button
if st.button("Filter zurücksetzen"):
    st.session_state["land_filter"] = []
    st.session_state["typ_filter"] = "Alle"

# Filter-Widgets
col1, col2 = st.columns(2)
with col1:
    land_selection = st.multiselect(
        "🌍 Länder auswählen",
        options=sorted(df['Land'].unique()),
        key="land_filter"
    )

# Flag für Hinweis auf fehlenden Typ
warning_msg = None
with col2:
    # Alle verfügbaren Typen ermitteln (abhängig von Länder-Filter)
    types = sorted(
        (df if not st.session_state['land_filter']
         else df[df['Land'].isin(st.session_state['land_filter'])]
        )['Typ'].unique()
    )
    options = ["Alle"] + types
    selected = st.session_state.get("typ_filter", "Alle")
    if selected not in options:
        warning_msg = f"Keine «{selected}» im gewählten Land verfügbar."
        selected = "Alle"
        st.session_state["typ_filter"] = "Alle"
    index = options.index(selected)
    st.selectbox(
        "👤 Typ auswählen",
        options=options,
        index=index,
        key="typ_filter"
    )

# Anwenden der Filter und Volltextsuche
filtered = df.copy()
if st.session_state["land_filter"]:
    filtered = filtered[filtered['Land'].isin(st.session_state['land_filter'])]
if st.session_state["typ_filter"] != "Alle":
    filtered = filtered[filtered['Typ'] == st.session_state['typ_filter']]

search = st.text_input("🔍 Suche Name (ab 3 Zeichen)", key="search_term")
if len(search) >= 3:
    filtered = filtered[filtered['Name'].str.contains(search, case=False, na=False)]
elif 0 < len(search) < 3:
    st.info("Bitte mindestens 3 Zeichen eingeben.")

# Anzeige der Ergebnisse
# Warnung direkt über der Tabelle
if warning_msg:
    st.warning(warning_msg)

st.markdown(f"### 📄 Gefundene Einträge: {len(filtered):,}".replace(",", "."))
# Nummerierung ab 1
filtered = filtered.reset_index(drop=True)
filtered.index = filtered.index + 1
filtered.index.name = "Nr"
# Tabelle anzeigen
st.dataframe(filtered, use_container_width=True)

# CSV-Export
csv = filtered.to_csv(index=False).encode("utf-8")
st.download_button("⬇️ Tabelle als CSV herunterladen", csv, "eu_sanktionen.csv", "text/csv")
