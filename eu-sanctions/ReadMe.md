# 🇪🇺 EU-Sanktionen Explorer

Ein interaktives Streamlit-Dashboard zur Analyse und Filterung von EU-Sanktionsdaten basierend auf dem offiziellen [EU Financial Sanctions Files RSS Feed](https://webgate.ec.europa.eu/fsd/fsf/public/rss).

## 🔍 Funktionen

- Automatischer Abruf der aktuellen XML-Datei aus dem offiziellen EU-RSS-Feed
- Darstellung von:
  - Namen, Typen (Person / Entity), Ländern
  - Publikationsdatum, Programm, Bemerkungen und Publikations-URL
- Filterfunktion nach Land, Typ und Namenssuche (ab 3 Zeichen)
- Übersichtliche Darstellung der Einträge mit Zählung pro Typ und insgesamt
- Export der gefilterten Tabelle als CSV-Datei

## 🛠️ Installation

### 1. Repository klonen

```bash
git clone https://github.com/dein-benutzername/eu-sanktionen-explorer.git
cd eu-sanktionen-explorer
