import requests
import pandas as pd
import streamlit as st
import xml.etree.ElementTree as ET
from io import BytesIO
import feedparser

# Drittanbieter-Komponente für interaktive Tabellen
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode

# --- Konfiguration ---
RSS_FEED_URL = "https://webgate.ec.europa.eu/fsd/fsf/public/rss"
CACHE_TTL_SECONDS = 7 * 24 * 3600  # 7 Tage
TIMEOUT_SECONDS = 10

# Wiederverwendbare HTTP-Session
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
        eu_ref = entity.get("euReferenceNumber", "Unbekannt")
        name_alias = entity.find("ns:nameAlias", ns)
        name = name_alias.get("wholeName", "Unbekannt") if name_alias is not None else "Unbekannt"
        stype_elem = entity.find("ns:subjectType", ns)
        code = stype_elem.get("code", "Unbekannt") if stype_elem is not None else "Unbekannt"
        subject_type = "Person" if code.lower() == "person" else "Entity" if code.lower() in ["enterprise", "entity"] else code
        reg = entity.find("ns:regulation", ns)
        pub_date = reg.get("publicationDate", "") if reg is not None else ""
        programme = reg.get("programme", "Unbekannt") if reg is not None else "Unbekannt"
        pub_url = ""
        if reg is not None:
            url_elem = reg.find("ns:publicationUrl", ns)
            if url_elem is not None and url_elem.text:
                pub_url = url_elem.text.strip()
        remarks = name_alias.findtext("ns:remark", default="", namespaces=ns) if name_alias is not None else ""
        addr = entity.find("ns:address", ns)
        country = addr.get("countryDescription", "Unbekannt").title() if addr is not None else "Unbekannt"

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

    return pd.DataFrame(sanktionen)

# --- Streamlit UI ---
st.set_page_config(page_title="EU-Sanktionen", layout="wide")
st.title("🇪🇺 EU-Sanktionen Explorer")
st.markdown("Filtere nach Land und Typ – Ergebnisanzeige unten.")

with st.spinner("🔄 Lade XML-Daten..."):
    try:
        xml_bytes = fetch_xml(RSS_FEED_URL)
    except RuntimeError as e:
        st.error(str(e))
        st.stop()
    df = lade_sanktionen(xml_bytes)

if df.empty:
    st.error("❌ Keine Daten geladen.")
    st.stop()

st.subheader("📊 Übersicht")
col1, col2 = st.columns([3,1])
for t, cnt in df['Typ'].value_counts().items():
    col1.metric(label=t, value=f"{cnt:,}".replace(",", "."))
col2.metric(label="Gesamt Einträge", value=f"{len(df):,}".replace(",", "."))

st.sidebar.header("Filter")
land = st.sidebar.multiselect("🌍 Länder", options=sorted(df['Land'].unique()))
typ_options = df['Typ'].unique() if not land else df[df['Land'].isin(land)]['Typ'].unique()
typ = st.sidebar.selectbox("👤 Typ", options=["Alle"] + sorted(typ_options))
search = st.sidebar.text_input("🔍 Suche Name (ab 3 Zeichen)")

filtered = df.copy()
if land:
    filtered = filtered[filtered['Land'].isin(land)]
if typ != "Alle":
    filtered = filtered[filtered['Typ'] == typ]
if 0 < len(search) < 3:
    st.sidebar.info("Bitte mindestens 3 Zeichen eingeben.")
elif len(search) >= 3:
    filtered = filtered[filtered['Name'].str.contains(search, case=False, na=False)]

# angepasster Link-Renderer mit schönem Text
link_renderer = JsCode(
    """
    class LinkRenderer {
        init(params) {
            const link = document.createElement('a');
            link.href = params.value;
            link.target = '_blank';
            link.textContent = '🔗 Öffnen';
            this.eGui = link;
        }
        getGui() { return this.eGui; }
    }
    """
)

gb = GridOptionsBuilder.from_dataframe(filtered)
# Standard Spaltenkonfiguration
gb.configure_default_column(resizable=True, sortable=True, filter=True)
# Publikations-URL mit unserem Link-Renderer
gb.configure_column('Publikations-URL', cellRenderer=link_renderer, autoHeight=True)
# Grid-Optionen final bauen
grid_options = gb.build()


AgGrid(
    filtered,
    gridOptions=grid_options,
    enable_enterprise_modules=False,
    theme='streamlit',
    height=400,
    fit_columns_on_grid_load=True,
    allow_unsafe_jscode=True
)

csv = filtered.to_csv(index=False).encode('utf-8')
st.download_button("⬇️ CSV herunterladen", csv, "eu_sanktionen.csv", "text/csv")
