import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from pathlib import Path
import numpy as np
from scipy import stats

st.set_page_config(
    page_title="Targi Młodej Pary — Dashboard",
    page_icon="💍",
    layout="wide",
    initial_sidebar_state="expanded",
)

from db import (
    load_events, load_bilety, load_zamowienia, load_klienci,
    load_platnosci, load_branze, load_wyjscia,
    load_rabaty, load_uslugi_zamowione, load_places,
)

# ── helpers ──────────────────────────────────────────────────

def safe_numeric(series):
    s = series.astype(str).str.replace(",", ".", regex=False).str.strip()
    return pd.to_numeric(s, errors="coerce").fillna(0)


def extract_year(date_series):
    return pd.to_datetime(date_series, errors="coerce").dt.year


def format_pln(val):
    if pd.isna(val) or val == 0:
        return "0 zł"
    return f"{val:,.0f} zł".replace(",", " ")


COLORS = px.colors.qualitative.Set2

CITY_COL_MAP = {
    'Kraków': 't_krakow', 'Warszawa': 't_warszawa', 'Gdańsk': 't_gdansk',
    'Rzeszów': 't_rzeszow', 'Poznań': 't_poznan', 'Białystok': 't_bialystok',
    'Gliwice': 't_gliwice', 'Lublin': 't_lublin', 'Katowice': 't_katowice',
    'Nowy Sącz': 't_nowysacz', 'Słupsk': 't_slupsk', 'Wałbrzych': 't_walbrzych',
    'Olsztyn': 't_ostroda',
}

# Cele sprzedażowe stoisk — jesień 2026 (liczba zamówień per miasto).
# Single source of truth: używane przez Cockpit sprzedażowy i TAB 8 (prognoza).
CELE_JESIEN_2026 = {
    "Rzeszów": 30,
    "Kraków": 45,
    "Gdańsk": 52,
    "Gliwice": 28,
    "Białystok": 34,
    "Poznań": 38,
    "Warszawa": 35,
}

# ── sidebar ──────────────────────────────────────────────────

st.sidebar.title("Targi Młodej Pary")
st.sidebar.caption("Dashboard analityczny")

if st.sidebar.button("Odśwież dane"):
    st.cache_data.clear()

# Load data
with st.spinner("Ładowanie danych z bazy..."):
    events = load_events()
    bilety = load_bilety()
    zamowienia = load_zamowienia()
    klienci = load_klienci()
    platnosci = load_platnosci()
    branze = load_branze()
    wyjscia = load_wyjscia()
    rabaty = load_rabaty()
    uslugi = load_uslugi_zamowione()
    places = load_places()

# Parse numerics
events["data_dt"] = pd.to_datetime(events["data"], errors="coerce")
events["rok"] = events["data_dt"].dt.year

klienci["time_utw_dt"] = pd.to_datetime(safe_numeric(klienci["time_utw"]).astype(int), unit="s", errors="coerce")
klienci["rok_rej"] = klienci["time_utw_dt"].dt.year
klienci["mies_rej"] = klienci["time_utw_dt"].dt.month
klienci["rok_mies_rej"] = klienci["time_utw_dt"].dt.to_period("M").astype(str)

bilety["kwota_netto_n"] = safe_numeric(bilety["cena"]) / 100
bilety["ileosob_n"] = safe_numeric(bilety["ileosob"])
bilety["data_utw_dt"] = pd.to_datetime(bilety["data_utw"], errors="coerce")
bilety["rok_targi"] = extract_year(bilety["data_targi"])

zamowienia["kwota_netto_n"] = safe_numeric(zamowienia["kwota_netto"])
zamowienia["ilem2_n"] = safe_numeric(zamowienia["ilem2"])
zamowienia["data_utw_dt"] = pd.to_datetime(zamowienia["data_utw"], errors="coerce")
zamowienia["rok_targi"] = extract_year(zamowienia["data_targi"])

platnosci["kwota_netto_n"] = safe_numeric(platnosci["kwota_netto"])
platnosci["data_wym_dt"] = pd.to_datetime(platnosci["data_wym"], errors="coerce")
platnosci["data_ksieg_dt"] = pd.to_datetime(platnosci["data_ksiegowania"], errors="coerce")

# ── Leady = konta klientów BEZ stoiska (rejestracja bez aktywnego zamówienia) ──
# Realna definicja leada wg firmy. Stara tabela `leads` (2017–2022) usunięta jako martwa.
_klienci_ze_stoiskiem = set(
    zamowienia[zamowienia["status"].astype(str) == "2"]["idklienta"].astype(str)
)
klienci["ma_stoisko"] = klienci["id"].astype(str).isin(_klienci_ze_stoiskiem)
klienci["mies_od_rej"] = (pd.Timestamp.now() - klienci["time_utw_dt"]).dt.days / 30.44

uslugi["cena_netto_n"] = safe_numeric(uslugi["cena_netto"])
places["powierzchnia_n"] = safe_numeric(places["powierzchnia"])

STATUS_ZAM = {"2": "W realizacji", "3": "Zatwierdzone", "9": "Anulowane"}
zamowienia["status_nazwa"] = zamowienia["status"].astype(str).map(STATUS_ZAM).fillna("Inne")

STATUS_PLAT = {"0": "Nowa", "1": "Wysłana", "2": "Zaległa", "3": "Opłacona", "4": "Historyczna"}
platnosci["status_nazwa"] = platnosci["status"].astype(str).map(STATUS_PLAT).fillna("Inne")

# Sidebar filters
all_years = sorted(events["rok"].dropna().unique().astype(int))
default_years = [y for y in all_years if y >= 2022]
selected_years = st.sidebar.multiselect("Rok", all_years, default=default_years)

all_cities = sorted(events["miasto"].dropna().unique())
selected_cities = st.sidebar.multiselect("Miasto", all_cities, default=[])

# Filter events
ev_filtered = events[events["rok"].isin(selected_years)] if selected_years else events
if selected_cities:
    ev_filtered = ev_filtered[ev_filtered["miasto"].isin(selected_cities)]
ev_ids_int = set(ev_filtered["id"].tolist())
ev_ids_str = {str(x) for x in ev_ids_int}

# Filter dependent data
bil_f = bilety[bilety["idtargi"].astype(str).isin(ev_ids_str)] if ev_ids_int else bilety
zam_f = zamowienia[zamowienia["idtargi"].astype(str).isin(ev_ids_str)] if ev_ids_int else zamowienia
wyj_f = wyjscia[wyjscia["idtargi"].astype(str).isin(ev_ids_str)] if ev_ids_int else wyjscia
pl_f = places[places["idtargi"].astype(str).isin(ev_ids_str)] if ev_ids_int else places
klienci_f = klienci[klienci["rok_rej"].isin(selected_years)] if selected_years else klienci

# Aktywne zamówienia (status 2)
zam_active = zam_f[zam_f["status"].isin(["2"])]

# Bilety z wejściem
bil_wejscia = bil_f[bil_f["ts_wejscie"].notna() & (bil_f["ts_wejscie"] != "")]

# ── TABS ─────────────────────────────────────────────────────

tab_cockpit, tab_strat, tab_leady, tab8, tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "🎯 Cockpit sprzedażowy",
    "📋 Strategia",
    "💼 Leady / Pipeline",
    "Targi jesień 2026",
    "Przegląd ogólny",
    "Eventy i miasta",
    "Bilety",
    "Wystawcy i zamówienia",
    "Przychody i płatności",
    "Rabaty",
    "Analizy i wnioski",
])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 1 — Przegląd ogólny
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab1:
    st.header("Przegląd ogólny")

    c1, c2, c3 = st.columns(3)
    c1.metric("Eventów", len(ev_filtered))
    c2.metric("Sprzedanych biletów (osoby)", f"{int(bil_f['ileosob_n'].sum()):,}".replace(",", " "))
    c3.metric("Łączne wejścia (osoby)", f"{int(bil_wejscia['ileosob_n'].sum()):,}".replace(",", " "))

    c4, c5, c6 = st.columns(3)
    c4.metric("Przychód ze stoisk (netto)", format_pln(zam_active["kwota_netto_n"].sum()))
    c5.metric("Przychód z biletów (netto)", format_pln(bil_f["kwota_netto_n"].sum()))
    c6.metric("Nowych rejestracji", f"{len(klienci_f):,}".replace(",", " "))

    c7, c8, c9, c10 = st.columns(4)
    total_m2 = zam_active["ilem2_n"].sum()
    c7.metric("Sprzedanych m²", f"{total_m2:,.0f}".replace(",", " "))
    avg_m2 = zam_active["ilem2_n"].mean() if len(zam_active) > 0 else 0
    c8.metric("Śr. m² na stoisko", f"{avg_m2:.1f}")
    avg_cena_m2 = zam_active["kwota_netto_n"].sum() / total_m2 if total_m2 > 0 else 0
    c9.metric("Śr. cena za m²", format_pln(avg_cena_m2))
    total_osoby = bil_f["ileosob_n"].sum()
    avg_bilet = bil_f["kwota_netto_n"].sum() / total_osoby if total_osoby > 0 else 0
    c10.metric("Śr. cena za bilet", format_pln(avg_bilet))

    # Współczynnik konwersji rejestracji → stoisko
    conv_rows = []
    for _, ev in ev_filtered.iterrows():
        col = CITY_COL_MAP.get(ev["miasto"])
        if col and col in klienci.columns:
            registered = int((klienci[col].astype(str).isin(["1", "1.0"])).sum())
            buyers = zam_active[zam_active["idtargi"].astype(str) == str(ev["id"])]["idklienta"].nunique()
            conv_rows.append({
                "symbol": ev["symbol"], "miasto": ev["miasto"], "rok": ev["rok"],
                "zarejestrowani": registered, "kupili": buyers,
                "konwersja": round(buyers / registered * 100, 1) if registered > 0 else 0,
            })
    conv_df = pd.DataFrame(conv_rows) if conv_rows else pd.DataFrame()

    if not conv_df.empty and len(conv_df) > 0:
        avg_conv = conv_df["konwersja"].mean()
        c11, c12 = st.columns(2)
        c11.metric("Śr. konwersja rejestracji → stoisko", f"{avg_conv:.1f}%")
        c12.metric("Najwyższa konwersja",
                   f"{conv_df.loc[conv_df['konwersja'].idxmax(), 'symbol']} — {conv_df['konwersja'].max():.1f}%"
                   if conv_df["konwersja"].max() > 0 else "—")

    # Konwersja nowych rejestracji → zamówienie
    klienci_sel = klienci_f[klienci_f["time_utw_dt"].notna()].copy()
    if len(klienci_sel) > 0:
        # Klienci z zamówieniami (status 2, bez wewnętrznych)
        # Zamówienia z ok_email != targi@ są już odfiltrowane w SQL (db.py)
        zam_ok = zamowienia[zamowienia["status"] == "2"]
        klienci_z_zam = set(zam_ok["idklienta"].astype(str).unique())
        klienci_sel["ma_zamowienie"] = klienci_sel["id"].astype(str).isin(klienci_z_zam)

        # Ile zamówień per klient
        zam_per_klient = zam_ok.groupby(zam_ok["idklienta"].astype(str)).size().reset_index(name="zam_cnt")
        klienci_sel = klienci_sel.merge(zam_per_klient, left_on=klienci_sel["id"].astype(str),
                                         right_on="idklienta", how="left")
        klienci_sel["zam_cnt"] = klienci_sel["zam_cnt"].fillna(0).astype(int)
        klienci_sel["powracajacy"] = klienci_sel["zam_cnt"] > 1

        total_rej = len(klienci_sel)
        total_z_zam = int(klienci_sel["ma_zamowienie"].sum())
        total_powracajacy = int(klienci_sel["powracajacy"].sum())
        konw_rej = round(total_z_zam / total_rej * 100, 1) if total_rej > 0 else 0
        pct_powracajacy = round(total_powracajacy / total_z_zam * 100, 1) if total_z_zam > 0 else 0
        sr_zam = round(klienci_sel.loc[klienci_sel["ma_zamowienie"], "zam_cnt"].mean(), 1) if total_z_zam > 0 else 0

        total_bez_zam = total_rej - total_z_zam

        c13, c14, c15, c16, c17 = st.columns(5)
        c13.metric("Rejestracje łącznie", f"{total_rej:,}".replace(",", " "))
        c14.metric("Z zamówieniem", f"{total_z_zam:,}".replace(",", " "),
                   help=f"{konw_rej}% rejestracji")
        c15.metric("Bez zamówienia", f"{total_bez_zam:,}".replace(",", " "))
        c16.metric("Konwersja rej. → zam.", f"{konw_rej}%")
        c17.metric("Powracający (>1 zam.)", f"{total_powracajacy} ({pct_powracajacy}%)")

    st.divider()

    col_l, col_r = st.columns(2)

    with col_l:
        ev_per_year = ev_filtered.groupby("rok").size().reset_index(name="ile")
        fig = px.bar(ev_per_year, x="rok", y="ile", title="Liczba eventów w roku",
                     color_discrete_sequence=COLORS, text="ile")
        fig.update_xaxes(dtick=1)
        fig.update_layout(xaxis_title="Rok", yaxis_title="Liczba eventów")
        st.plotly_chart(fig, use_container_width=True)

    with col_r:
        miasta_rank = ev_filtered.groupby("miasto").size().reset_index(name="edycje").sort_values("edycje", ascending=True)
        fig = px.bar(miasta_rank, x="edycje", y="miasto", orientation="h",
                     title="Ranking miast — liczba edycji",
                     color_discrete_sequence=COLORS, text="edycje")
        fig.update_layout(yaxis_title="", xaxis_title="Liczba edycji")
        st.plotly_chart(fig, use_container_width=True)

    col_l2, col_r2 = st.columns(2)

    with col_l2:
        zam_year_agg = zam_active.groupby("rok_targi").agg(
            przychod=("kwota_netto_n", "sum"),
        ).reset_index()
        fig = px.bar(zam_year_agg, x="rok_targi", y="przychod",
                     title="Przychód ze stoisk rocznie (netto)",
                     color_discrete_sequence=[COLORS[1]], text_auto=".2s")
        fig.update_xaxes(dtick=1)
        fig.update_layout(xaxis_title="Rok", yaxis_title="zł")
        st.plotly_chart(fig, use_container_width=True)

    with col_r2:
        bil_year = bil_f.groupby("rok_targi").agg(
            przychod=("kwota_netto_n", "sum"),
        ).reset_index()
        fig = px.bar(bil_year, x="rok_targi", y="przychod",
                     title="Przychód z biletów rocznie (netto)",
                     color_discrete_sequence=COLORS, text_auto=".2s")
        fig.update_xaxes(dtick=1)
        fig.update_layout(xaxis_title="Rok", yaxis_title="zł")
        st.plotly_chart(fig, use_container_width=True)

    col_l3, col_r3 = st.columns(2)

    with col_l3:
        m2_year = zam_active.groupby("rok_targi").agg(
            m2=("ilem2_n", "sum"),
        ).reset_index()
        fig = px.bar(m2_year, x="rok_targi", y="m2",
                     title="Sprzedane m² rocznie",
                     color_discrete_sequence=[COLORS[4]], text_auto=".0f")
        fig.update_xaxes(dtick=1)
        fig.update_layout(xaxis_title="Rok", yaxis_title="m²")
        st.plotly_chart(fig, use_container_width=True)

    with col_r3:
        avg_m2_year = zam_active.groupby("rok_targi").agg(
            sr_m2=("ilem2_n", "mean"),
        ).reset_index()
        avg_m2_year["sr_m2"] = avg_m2_year["sr_m2"].round(1)
        fig = px.bar(avg_m2_year, x="rok_targi", y="sr_m2",
                     title="Śr. m² na stoisko rocznie",
                     color_discrete_sequence=[COLORS[3]], text="sr_m2")
        fig.update_xaxes(dtick=1)
        fig.update_layout(xaxis_title="Rok", yaxis_title="m²")
        st.plotly_chart(fig, use_container_width=True)

    # Średnie ceny rocznie
    col_l4, col_r4 = st.columns(2)

    with col_l4:
        cena_m2_year = zam_active.groupby("rok_targi").agg(
            przychod=("kwota_netto_n", "sum"),
            m2=("ilem2_n", "sum"),
        ).reset_index()
        cena_m2_year["sr_cena_m2"] = (cena_m2_year["przychod"] / cena_m2_year["m2"]).round(0)
        cena_m2_year = cena_m2_year[cena_m2_year["m2"] > 0]
        fig = px.line(cena_m2_year, x="rok_targi", y="sr_cena_m2",
                      title="Śr. cena za m² rocznie (netto)",
                      color_discrete_sequence=[COLORS[5]], markers=True, text="sr_cena_m2")
        fig.update_xaxes(dtick=1)
        fig.update_traces(textposition="top center")
        fig.update_layout(xaxis_title="Rok", yaxis_title="zł / m²")
        st.plotly_chart(fig, use_container_width=True)

    with col_r4:
        bil_cena_year = bil_f.groupby("rok_targi").agg(
            przychod=("kwota_netto_n", "sum"),
            osoby=("ileosob_n", "sum"),
        ).reset_index()
        bil_cena_year["sr_cena_bilet"] = (bil_cena_year["przychod"] / bil_cena_year["osoby"]).round(0)
        bil_cena_year = bil_cena_year[bil_cena_year["osoby"] > 0]
        fig = px.line(bil_cena_year, x="rok_targi", y="sr_cena_bilet",
                      title="Śr. cena za bilet rocznie",
                      color_discrete_sequence=[COLORS[0]], markers=True, text="sr_cena_bilet")
        fig.update_xaxes(dtick=1)
        fig.update_traces(textposition="top center")
        fig.update_layout(xaxis_title="Rok", yaxis_title="zł / bilet")
        st.plotly_chart(fig, use_container_width=True)

    # Wykres konwersji rejestracji → stoisko per event
    if not conv_df.empty and conv_df["konwersja"].sum() > 0:
        col_l5, col_r5 = st.columns(2)
        with col_l5:
            conv_sorted = conv_df.sort_values("konwersja", ascending=True)
            fig = px.bar(conv_sorted, x="konwersja", y="symbol", orientation="h",
                         color="miasto", title="Konwersja rejestracji → stoisko per event",
                         color_discrete_sequence=COLORS, text="konwersja")
            fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
            fig.update_layout(xaxis_title="Konwersja %", yaxis_title="", showlegend=True)
            st.plotly_chart(fig, use_container_width=True)

        with col_r5:
            conv_city = conv_df.groupby("miasto").agg(
                sr_konwersja=("konwersja", "mean"),
                eventow=("symbol", "count"),
            ).reset_index().sort_values("sr_konwersja", ascending=True)
            fig = px.bar(conv_city, x="sr_konwersja", y="miasto", orientation="h",
                         title="Śr. konwersja per miasto",
                         color_discrete_sequence=[COLORS[2]], text="sr_konwersja")
            fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
            fig.update_layout(xaxis_title="Śr. konwersja %", yaxis_title="")
            st.plotly_chart(fig, use_container_width=True)

    # ── Wykresy konwersji nowych rejestracji → zamówienie ──
    if len(klienci_sel) > 0:
        st.divider()
        st.subheader("Konwersja nowych rejestracji → zamówienie")

        # Dane per rok rejestracji
        rej_year = klienci_sel.groupby("rok_rej").agg(
            rejestracje=("id", "count"),
            z_zamowieniem=("ma_zamowienie", "sum"),
            powracajacy=("powracajacy", "sum"),
        ).reset_index()
        rej_year["z_zamowieniem"] = rej_year["z_zamowieniem"].astype(int)
        rej_year["powracajacy"] = rej_year["powracajacy"].astype(int)
        rej_year["bez_zamowienia"] = rej_year["rejestracje"] - rej_year["z_zamowieniem"]
        rej_year["konwersja_pct"] = (rej_year["z_zamowieniem"] / rej_year["rejestracje"] * 100).round(1)
        rej_year["pct_powracajacy"] = (rej_year["powracajacy"] / rej_year["z_zamowieniem"].replace(0, 1) * 100).round(1)
        rej_year["sr_zam"] = rej_year.apply(
            lambda r: round(klienci_sel[(klienci_sel["rok_rej"] == r["rok_rej"]) & (klienci_sel["ma_zamowienie"])]["zam_cnt"].mean(), 1)
            if r["z_zamowieniem"] > 0 else 0, axis=1
        )

        col_a, col_b = st.columns(2)

        with col_a:
            # Stacked bar: rejestracje z zamówieniem vs bez
            rej_melt = rej_year[["rok_rej", "z_zamowieniem", "bez_zamowienia"]].melt(
                id_vars="rok_rej", var_name="typ", value_name="klientow"
            )
            rej_melt["typ"] = rej_melt["typ"].map({
                "z_zamowieniem": "Złożyli zamówienie",
                "bez_zamowienia": "Bez zamówienia",
            })
            fig = px.bar(rej_melt, x="rok_rej", y="klientow", color="typ",
                         title="Nowe rejestracje — z zamówieniem vs bez",
                         color_discrete_sequence=[COLORS[2], COLORS[7]],
                         text="klientow", barmode="stack")
            fig.update_xaxes(dtick=1)
            fig.update_layout(xaxis_title="Rok rejestracji", yaxis_title="Klientów", legend_title="")
            st.plotly_chart(fig, use_container_width=True)

        with col_b:
            # Konwersja % rocznie
            fig = px.line(rej_year, x="rok_rej", y="konwersja_pct",
                          title="% nowych rejestracji z zamówieniem",
                          color_discrete_sequence=[COLORS[1]], markers=True, text="konwersja_pct")
            fig.update_xaxes(dtick=1)
            fig.update_traces(textposition="top center", texttemplate="%{text:.1f}%")
            fig.update_layout(xaxis_title="Rok rejestracji", yaxis_title="%")
            st.plotly_chart(fig, use_container_width=True)

        col_c, col_d = st.columns(2)

        with col_c:
            # Powracający klienci %
            fig = px.bar(rej_year, x="rok_rej", y="pct_powracajacy",
                         title="% kupujących z >1 zamówieniem (powracający)",
                         color_discrete_sequence=[COLORS[4]], text="pct_powracajacy")
            fig.update_xaxes(dtick=1)
            fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
            fig.update_layout(xaxis_title="Rok rejestracji", yaxis_title="%")
            st.plotly_chart(fig, use_container_width=True)

        with col_d:
            # Średnia ilość zamówień na klienta
            fig = px.bar(rej_year, x="rok_rej", y="sr_zam",
                         title="Śr. zamówień na klienta (kupujący)",
                         color_discrete_sequence=[COLORS[3]], text="sr_zam")
            fig.update_xaxes(dtick=1)
            fig.update_traces(textposition="outside")
            fig.update_layout(xaxis_title="Rok rejestracji", yaxis_title="Zamówień")
            st.plotly_chart(fig, use_container_width=True)

        # ── Miesięczne zestawienie rejestracji i zamówień ──
        st.divider()
        st.subheader("Miesięczne zestawienie rejestracji i zamówień")

        MIES_NAMES = {1: "Sty", 2: "Lut", 3: "Mar", 4: "Kwi", 5: "Maj", 6: "Cze",
                      7: "Lip", 8: "Sie", 9: "Wrz", 10: "Paź", 11: "Lis", 12: "Gru"}

        rej_month = klienci_sel.groupby("rok_mies_rej").agg(
            rejestracje=("id", "count"),
            z_zamowieniem=("ma_zamowienie", "sum"),
        ).reset_index()
        rej_month["z_zamowieniem"] = rej_month["z_zamowieniem"].astype(int)
        rej_month["bez_zamowienia"] = rej_month["rejestracje"] - rej_month["z_zamowieniem"]
        rej_month["konwersja_pct"] = (rej_month["z_zamowieniem"] / rej_month["rejestracje"] * 100).round(1)
        rej_month = rej_month.sort_values("rok_mies_rej")

        # Zamówienia per miesiąc (data utworzenia)
        zam_active_m = zam_active.copy()
        zam_active_m["data_utw_dt"] = pd.to_datetime(zam_active_m["data_utw"], errors="coerce")
        zam_active_m["rok_mies_zam"] = zam_active_m["data_utw_dt"].dt.to_period("M").astype(str)
        zam_month = zam_active_m.groupby("rok_mies_zam").agg(
            zamowienia=("id", "count"),
            przychod=("kwota_netto_n", "sum"),
        ).reset_index().rename(columns={"rok_mies_zam": "rok_mies"})
        zam_month = zam_month.sort_values("rok_mies")

        # Wykres 1: Stacked bar rejestracje z/bez zamówienia miesięcznie
        rej_m_melt = rej_month[["rok_mies_rej", "z_zamowieniem", "bez_zamowienia"]].melt(
            id_vars="rok_mies_rej", var_name="typ", value_name="klientow"
        )
        rej_m_melt["typ"] = rej_m_melt["typ"].map({
            "z_zamowieniem": "Z zamówieniem",
            "bez_zamowienia": "Bez zamówienia",
        })
        fig = px.bar(rej_m_melt, x="rok_mies_rej", y="klientow", color="typ",
                     title="Rejestracje miesięcznie — z zamówieniem vs bez (łącznie na szczycie)",
                     color_discrete_sequence=[COLORS[2], COLORS[7]],
                     text="klientow", barmode="stack")
        # Dodaj łączną sumę jako anotację na szczycie każdego słupka
        for _, row in rej_month.iterrows():
            fig.add_annotation(
                x=row["rok_mies_rej"], y=row["rejestracje"],
                text=f"<b>{row['rejestracje']}</b>",
                showarrow=False, yshift=12,
                font=dict(size=12, color="black"),
            )
        fig.update_layout(xaxis_title="Miesiąc", yaxis_title="Klientów", legend_title="",
                          xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)

        # Osobny wykres: łączne rejestracje miesięcznie (linia trendu)
        col_rej_total1, col_rej_total2 = st.columns(2)
        with col_rej_total1:
            fig = px.bar(rej_month, x="rok_mies_rej", y="rejestracje",
                         title="Łączne nowe rejestracje miesięcznie",
                         color_discrete_sequence=[COLORS[5]], text="rejestracje")
            fig.update_traces(textposition="outside")
            fig.update_layout(xaxis_title="Miesiąc", yaxis_title="Rejestracji", xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)

        with col_rej_total2:
            # Rejestracje tygodniowo
            klienci_sel["rok_tydz_rej"] = klienci_sel["time_utw_dt"].dt.to_period("W").apply(
                lambda p: str(p.start_time.date())
            )
            rej_week = klienci_sel.groupby("rok_tydz_rej").agg(
                rejestracje=("id", "count"),
            ).reset_index().sort_values("rok_tydz_rej")
            fig = px.line(rej_week, x="rok_tydz_rej", y="rejestracje",
                          title="Nowe rejestracje tygodniowo",
                          color_discrete_sequence=[COLORS[3]], markers=False)
            fig.update_layout(xaxis_title="Tydzień (od)", yaxis_title="Rejestracji", xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)

        col_m1, col_m2 = st.columns(2)

        with col_m1:
            # Konwersja % miesięcznie
            fig = px.line(rej_month, x="rok_mies_rej", y="konwersja_pct",
                          title="Konwersja rejestracji → zamówienie (miesięcznie)",
                          color_discrete_sequence=[COLORS[1]], markers=True)
            fig.update_layout(xaxis_title="Miesiąc", yaxis_title="%", xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)

        with col_m2:
            # Zamówienia per miesiąc
            fig = px.bar(zam_month, x="rok_mies", y="zamowienia",
                         title="Zamówienia na stoiska miesięcznie",
                         color_discrete_sequence=[COLORS[0]], text="zamowienia")
            fig.update_traces(textposition="outside")
            fig.update_layout(xaxis_title="Miesiąc", yaxis_title="Zamówień", xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)

        # Tabela podsumowująca miesięcznie
        with st.expander("📋 Tabela miesięczna — rejestracje i zamówienia"):
            rej_table = rej_month.copy()
            rej_table = rej_table.rename(columns={
                "rok_mies_rej": "Miesiąc",
                "rejestracje": "Rejestracje łącznie",
                "z_zamowieniem": "Z zamówieniem",
                "bez_zamowienia": "Bez zamówienia",
                "konwersja_pct": "Konwersja %",
            })
            # Merge z zamówieniami
            rej_table = rej_table.merge(
                zam_month.rename(columns={"rok_mies": "Miesiąc", "zamowienia": "Zamówień na stoiska",
                                           "przychod": "Przychód stoiska (netto)"}),
                on="Miesiąc", how="left"
            ).fillna(0)
            rej_table["Przychód stoiska (netto)"] = rej_table["Przychód stoiska (netto)"].apply(
                lambda x: f"{x:,.0f} zł".replace(",", " ")
            )
            rej_table["Zamówień na stoiska"] = rej_table["Zamówień na stoiska"].astype(int)
            st.dataframe(rej_table, use_container_width=True, hide_index=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 2 — Eventy i miasta
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab2:
    st.header("Eventy i miasta")

    # Dane per miasto
    zam_miasto = zam_active.groupby("miasto").agg(
        przychod_stoiska=("kwota_netto_n", "sum"),
        zamowien=("id", "count"),
        m2=("ilem2_n", "sum"),
    ).reset_index()

    bil_miasto = bil_f.groupby("miasto").agg(
        przychod_bilety=("kwota_netto_n", "sum"),
        biletow=("ileosob_n", "sum"),
    ).reset_index()

    bil_wej_miasto = bil_wejscia.groupby("miasto").agg(wejsc=("ileosob_n", "sum")).reset_index()
    ev_miasto = ev_filtered.groupby("miasto").size().reset_index(name="edycje")

    miasto_df = ev_miasto.merge(zam_miasto, on="miasto", how="left") \
                         .merge(bil_miasto, on="miasto", how="left") \
                         .merge(bil_wej_miasto, on="miasto", how="left") \
                         .fillna(0)
    miasto_df["przychod_total"] = miasto_df["przychod_stoiska"] + miasto_df["przychod_bilety"]

    col1, col2 = st.columns(2)
    with col1:
        fig = px.bar(miasto_df.sort_values("przychod_total", ascending=True),
                     x="przychod_total", y="miasto", orientation="h",
                     title="Łączny przychód per miasto (netto)",
                     color_discrete_sequence=COLORS, text_auto=".2s")
        fig.update_layout(yaxis_title="", xaxis_title="zł")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        fig = px.bar(miasto_df.sort_values("wejsc", ascending=True),
                     x="wejsc", y="miasto", orientation="h",
                     title="Frekwencja per miasto (osoby z biletów)",
                     color_discrete_sequence=[COLORS[2]], text_auto=".0f")
        fig.update_layout(yaxis_title="", xaxis_title="Osoby")
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # Porównanie edycji
    st.subheader("Porównanie edycji rok do roku")
    ev_city = ev_filtered.copy()

    bil_ev = bil_f.groupby("idtargi").agg(
        bilety=("ileosob_n", "sum"),
        przychod_bil=("kwota_netto_n", "sum"),
    ).reset_index()

    zam_ev = zam_active.groupby("idtargi").agg(
        zamowien=("id", "count"),
        przychod_st=("kwota_netto_n", "sum"),
    ).reset_index()
    zam_ev["idtargi"] = zam_ev["idtargi"].astype(str)

    bil_wej_ev = bil_wejscia.groupby("idtargi").agg(wejsc=("ileosob_n", "sum")).reset_index()

    ev_detail = ev_city.merge(bil_ev, left_on="id", right_on="idtargi", how="left") \
                       .merge(zam_ev, left_on=ev_city["id"].astype(str), right_on="idtargi", how="left", suffixes=("", "_z")) \
                       .merge(bil_wej_ev, left_on="id", right_on="idtargi", how="left", suffixes=("", "_w")) \
                       .fillna(0)

    compare_city = st.selectbox("Wybierz miasto", sorted(ev_city["miasto"].unique()))
    city_data = ev_detail[ev_detail["miasto"] == compare_city].sort_values("data_dt")

    if not city_data.empty:
        fig = go.Figure()
        fig.add_trace(go.Bar(x=city_data["symbol"], y=city_data["bilety"], name="Bilety (osoby)", marker_color=COLORS[0]))
        fig.add_trace(go.Bar(x=city_data["symbol"], y=city_data["wejsc"], name="Wejścia (osoby)", marker_color=COLORS[2]))
        fig.update_layout(title=f"{compare_city} — bilety i wejścia per edycja",
                          barmode="group", xaxis_title="Edycja", yaxis_title="Osoby")
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # Tabela eventów
    st.subheader("Lista eventów")
    ev_display = ev_detail[["symbol", "miasto", "data", "bilety", "wejsc", "zamowien", "przychod_bil", "przychod_st"]].copy()
    ev_display.columns = ["Symbol", "Miasto", "Data", "Bilety (osoby)", "Wejścia", "Zamówienia", "Przychód bilety", "Przychód stoiska"]
    ev_display = ev_display.sort_values("Data", ascending=False)
    st.dataframe(ev_display, use_container_width=True, hide_index=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 3 — Bilety
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab3:
    st.header("Sprzedaż biletów")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Biletów (osoby)", f"{int(bil_f['ileosob_n'].sum()):,}".replace(",", " "))
    c2.metric("Wejścia (osoby)", f"{int(bil_wejscia['ileosob_n'].sum()):,}".replace(",", " "))
    c3.metric("Przychód netto", format_pln(bil_f["kwota_netto_n"].sum()))
    avg_ticket = bil_f[bil_f["kwota_netto_n"] > 0]["kwota_netto_n"].mean()
    c4.metric("Śr. cena biletu", format_pln(avg_ticket))

    col1, col2 = st.columns(2)

    with col1:
        bil_per_event = bil_f.groupby(["symbol_targi", "miasto"]).agg(
            osoby=("ileosob_n", "sum"),
            przychod=("kwota_netto_n", "sum"),
        ).reset_index().sort_values("osoby", ascending=False).head(20)
        fig = px.bar(bil_per_event, x="symbol_targi", y="osoby",
                     title="Top 20 eventów — bilety (osoby)",
                     color="miasto", color_discrete_sequence=COLORS)
        fig.update_layout(xaxis_title="Event", yaxis_title="Osoby", xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        bil_monthly = bil_f.copy()
        bil_monthly["miesiac"] = bil_monthly["data_utw_dt"].dt.to_period("M").astype(str)
        bil_month_agg = bil_monthly.groupby("miesiac").agg(osoby=("ileosob_n", "sum")).reset_index()
        bil_month_agg = bil_month_agg.sort_values("miesiac").tail(24)
        fig = px.line(bil_month_agg, x="miesiac", y="osoby",
                      title="Sprzedaż biletów miesięcznie (osoby, ost. 24 mies.)",
                      color_discrete_sequence=COLORS)
        fig.update_layout(xaxis_title="Miesiąc", yaxis_title="Osoby")
        st.plotly_chart(fig, use_container_width=True)

    col3, col4 = st.columns(2)

    with col3:
        # Konwersja bilety → wejścia
        bil_ev_cnt = bil_f.groupby("idtargi")["ileosob_n"].sum().reset_index(name="bilety_osoby")
        wej_ev_cnt = bil_wejscia.groupby("idtargi")["ileosob_n"].sum().reset_index(name="wejsc_osoby")
        konw = bil_ev_cnt.merge(wej_ev_cnt, on="idtargi", how="inner")
        konw = konw.merge(events[["id", "symbol", "miasto"]], left_on="idtargi", right_on="id", how="left")
        konw["konwersja"] = (konw["wejsc_osoby"] / konw["bilety_osoby"] * 100).round(1)
        konw = konw.sort_values("konwersja", ascending=False).head(15)
        fig = px.bar(konw, x="symbol", y="konwersja",
                     title="Konwersja: bilety → wejścia (%)",
                     color="miasto", color_discrete_sequence=COLORS, text="konwersja")
        fig.update_layout(xaxis_title="Event", yaxis_title="%", xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)

    with col4:
        typ_labels = {0: "Inny", 1: "Zwykły", 2: "VIP"}
        bil_typ = bil_f.copy()
        bil_typ["typ_nazwa"] = bil_typ["typ"].map(typ_labels).fillna("Inny")
        typ_agg = bil_typ.groupby("typ_nazwa").agg(osoby=("ileosob_n", "sum")).reset_index()
        fig = px.pie(typ_agg, values="osoby", names="typ_nazwa",
                     title="Struktura biletów (osoby)",
                     color_discrete_sequence=COLORS)
        st.plotly_chart(fig, use_container_width=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 4 — Wystawcy i zamówienia
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab4:
    st.header("Wystawcy i zamówienia stoisk")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Zamówień", f"{len(zam_active):,}".replace(",", " "))
    c2.metric("Przychód netto", format_pln(zam_active["kwota_netto_n"].sum()))
    c3.metric("Łączne m²", f"{zam_active['ilem2_n'].sum():,.0f}".replace(",", " "))
    c4.metric("Śr. m² na stoisko", f"{zam_active['ilem2_n'].mean():.1f}" if len(zam_active) > 0 else "0")

    col1, col2 = st.columns(2)

    with col1:
        branze_map = dict(zip(branze["id"].astype(str), branze["nazwa"]))
        zam_branza = zam_active.copy()
        zam_branza["branza_nazwa"] = zam_branza["branza"].astype(str).map(branze_map).fillna("Brak")
        br_agg = zam_branza.groupby("branza_nazwa").agg(
            ile=("id", "count"),
            przychod=("kwota_netto_n", "sum"),
        ).reset_index().sort_values("ile", ascending=True)
        fig = px.bar(br_agg, x="ile", y="branza_nazwa", orientation="h",
                     title="Zamówienia per branża",
                     color_discrete_sequence=COLORS, text="ile")
        fig.update_layout(yaxis_title="", xaxis_title="Liczba zamówień")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        # Nowi vs powracający
        klient_events = zam_active.groupby("idklienta")["idtargi"].nunique().reset_index(name="ile_eventow")
        klient_events["typ"] = klient_events["ile_eventow"].apply(
            lambda x: "Jednorazowy (1 event)" if x == 1
            else "Powracający (2-3)" if x <= 3
            else "Stały (4+)"
        )
        typ_agg = klient_events.groupby("typ").size().reset_index(name="ile")
        fig = px.pie(typ_agg, values="ile", names="typ",
                     title="Wystawcy — lojalność",
                     color_discrete_sequence=COLORS)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # Top wystawcy
    st.subheader("Top 15 wystawców — przychód")
    top_klienci = zam_active.groupby("idklienta").agg(
        zamowien=("id", "count"),
        przychod=("kwota_netto_n", "sum"),
        m2=("ilem2_n", "sum"),
    ).reset_index().sort_values("przychod", ascending=False).head(15)
    top_klienci = top_klienci.merge(
        klienci[["id", "nazwa"]],
        left_on="idklienta", right_on=klienci["id"].astype(str), how="left"
    )
    fig = px.bar(top_klienci, x="przychod", y="nazwa", orientation="h",
                 title="Top 15 wystawców — przychód netto",
                 color_discrete_sequence=[COLORS[3]], text_auto=".2s")
    fig.update_layout(yaxis_title="", xaxis_title="zł", height=500)
    st.plotly_chart(fig, use_container_width=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 5 — Przychody i płatności
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab5:
    st.header("Przychody i płatności")

    c1, c2, c3, c4 = st.columns(4)
    oplacone = platnosci[platnosci["status"].astype(str) == "3"]["kwota_netto_n"].sum()
    zaleg = platnosci[platnosci["status"].astype(str) == "2"]["kwota_netto_n"].sum()
    c1.metric("Opłacone (netto)", format_pln(oplacone))
    c2.metric("Zaległe (netto)", format_pln(zaleg))
    c3.metric("Łącznie płatności", f"{len(platnosci):,}".replace(",", " "))
    if oplacone + zaleg > 0:
        c4.metric("% ściągalności", f"{oplacone / (oplacone + zaleg) * 100:.1f}%")

    col1, col2 = st.columns(2)

    with col1:
        plat_status = platnosci.groupby("status_nazwa")["kwota_netto_n"].sum().reset_index()
        fig = px.pie(plat_status, values="kwota_netto_n", names="status_nazwa",
                     title="Płatności — rozkład kwot per status",
                     color_discrete_sequence=COLORS)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        plat_monthly = platnosci[platnosci["status"].astype(str) == "3"].copy()
        plat_monthly["miesiac"] = plat_monthly["data_ksieg_dt"].dt.to_period("M").astype(str)
        plat_m_agg = plat_monthly.groupby("miesiac")["kwota_netto_n"].sum().reset_index()
        plat_m_agg = plat_m_agg.sort_values("miesiac").tail(24)
        fig = px.bar(plat_m_agg, x="miesiac", y="kwota_netto_n",
                     title="Wpływy miesięczne (netto, ost. 24 mies.)",
                     color_discrete_sequence=[COLORS[1]], text_auto=".2s")
        fig.update_layout(xaxis_title="Miesiąc", yaxis_title="zł")
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # Struktura przychodów
    st.subheader("Struktura przychodów")
    przychody = pd.DataFrame({
        "Źródło": ["Stoiska", "Bilety", "Usługi dodatkowe"],
        "Kwota": [
            zam_active["kwota_netto_n"].sum(),
            bil_f["kwota_netto_n"].sum(),
            uslugi["cena_netto_n"].sum(),
        ]
    })
    fig = px.pie(przychody, values="Kwota", names="Źródło",
                 title="Struktura przychodów (netto)",
                 color_discrete_sequence=COLORS)
    st.plotly_chart(fig, use_container_width=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 6 — Leady i rabaty
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab6:
    st.header("Rabaty")

    c1, c2, c3 = st.columns(3)
    c1.metric("Kodów rabatowych", len(rabaty))
    c2.metric("Łączne użycia", int(rabaty["uzycia"].sum()))
    c3.metric("Wartość rabatów", format_pln(rabaty["suma_rabatu"].sum()))

    col_a, col_b = st.columns(2)

    with col_a:
        rabaty_top = rabaty[rabaty["uzycia"] > 0].sort_values("uzycia", ascending=True)
        fig = px.bar(rabaty_top, x="uzycia", y="kod", orientation="h",
                     title="Kody rabatowe — liczba użyć",
                     color_discrete_sequence=[COLORS[5]], text="uzycia")
        fig.update_layout(yaxis_title="Kod", xaxis_title="Użycia")
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        rabaty_val = rabaty[rabaty["suma_rabatu"] > 0].sort_values("suma_rabatu", ascending=True)
        fig = px.bar(rabaty_val, x="suma_rabatu", y="kod", orientation="h",
                     title="Kody rabatowe — wartość rabatów",
                     color_discrete_sequence=[COLORS[3]], text_auto=".2s")
        fig.update_layout(yaxis_title="Kod", xaxis_title="zł")
        st.plotly_chart(fig, use_container_width=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 8 — Targi jesienne
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab8:
    st.header("Targi jesienne 2026 — postęp sprzedaży")

    # Eventy jesienne 2026 (X, XI, XII) — niezależnie od filtrów w sidebarze
    ev_all = events.copy()
    ev_all["miesiac_n"] = ev_all["data_dt"].dt.month
    ev_all["rok_n"] = ev_all["data_dt"].dt.year
    ev_jesien_2026 = ev_all[(ev_all["rok_n"] == 2026) & (ev_all["miesiac_n"].isin([10, 11, 12]))].copy()

    # Historyczne jesienne eventy do porównania (te same miasta)
    miasta_2026 = ev_jesien_2026["miasto"].unique().tolist()
    ev_jesien_hist = ev_all[
        (ev_all["rok_n"] < 2026) & (ev_all["rok_n"] >= 2022) &
        (ev_all["miesiac_n"].isin([10, 11, 12])) &
        (ev_all["miasto"].isin(miasta_2026))
    ].copy()
    ev_jesien = pd.concat([ev_jesien_hist, ev_jesien_2026], ignore_index=True)

    # Zamówienia i bilety — bez filtrów sidebarowych, własne filtrowanie
    jes_event_ids = ev_jesien["id"].astype(int).tolist()
    zam_jes = zamowienia[
        (pd.to_numeric(zamowienia["idtargi"], errors="coerce").isin(jes_event_ids)) &
        (zamowienia["status"].astype(str) == "2")
    ].copy()
    zam_jes["kwota_netto_n"] = pd.to_numeric(zam_jes["kwota_netto"].astype(str).str.replace(" ", "").str.replace(",", "."), errors="coerce").fillna(0)
    zam_jes["ilem2_n"] = pd.to_numeric(zam_jes["ilem2"].astype(str).str.replace(",", "."), errors="coerce").fillna(0)
    zam_jes["idtargi_n"] = pd.to_numeric(zam_jes["idtargi"], errors="coerce")

    bil_jes = bilety[
        (pd.to_numeric(bilety["idtargi"], errors="coerce").isin(jes_event_ids)) &
        (bilety["status"].isin([2, 3]))
    ].copy()
    bil_jes["kwota_netto_n"] = pd.to_numeric(bil_jes["kwota_netto"].astype(str).str.replace(" ", "").str.replace(",", "."), errors="coerce").fillna(0) / 100
    bil_jes["ileosob_n"] = pd.to_numeric(bil_jes["ileosob"], errors="coerce").fillna(0)
    bil_wej_jes = bil_jes[bil_jes["ts_wejscie"].apply(lambda x: x is not None and str(x).strip() not in ("", "0"))]

    if ev_jesien_2026.empty:
        st.info("Brak eventów jesiennych 2026 w bazie.")
    else:
        # Dane per event jesienny
        jes_zam = zam_jes
        jes_bil = bil_jes
        jes_wej = bil_wej_jes

        # Buduj tabelę per event
        jes_zam["idtargi_n"] = pd.to_numeric(jes_zam["idtargi"], errors="coerce")
        jes_bil["idtargi_n"] = pd.to_numeric(jes_bil["idtargi"], errors="coerce")
        jes_wej["idtargi_n"] = pd.to_numeric(jes_wej["idtargi"], errors="coerce")

        jes_stats = []
        for _, ev in ev_jesien.iterrows():
            eid = int(ev["id"])
            z = jes_zam[jes_zam["idtargi_n"] == eid]
            b = jes_bil[jes_bil["idtargi_n"] == eid]
            w = jes_wej[jes_wej["idtargi_n"] == eid]

            przychod_st = z["kwota_netto_n"].sum()
            m2 = z["ilem2_n"].sum()
            zamowien = len(z)
            cena_m2 = round(przychod_st / m2, 0) if m2 > 0 else 0
            sr_m2_stoisko = round(m2 / zamowien, 1) if zamowien > 0 else 0
            osoby = b["ileosob_n"].sum()
            przychod_bil = b["kwota_netto_n"].sum()
            sr_cena_bilet = round(przychod_bil / osoby, 0) if osoby > 0 else 0
            wejscia = w["ileosob_n"].sum()
            frekwencja = round(wejscia / osoby * 100, 1) if osoby > 0 else 0

            jes_stats.append({
                "ev_id": int(eid),
                "symbol": ev["symbol"],
                "data": ev["data"],
                "miasto": ev["miasto"],
                "rok": ev["rok"],
                "zamowien": zamowien,
                "m2": m2,
                "sr_m2_stoisko": sr_m2_stoisko,
                "cena_m2": cena_m2,
                "przychod_stoiska": przychod_st,
                "osoby_bilety": osoby,
                "sr_cena_bilet": sr_cena_bilet,
                "przychod_bilety": przychod_bil,
                "przychod_lacznie": przychod_st + przychod_bil,
                "wejscia": wejscia,
                "frekwencja": frekwencja,
            })

        jes_df = pd.DataFrame(jes_stats)
        jes_df = jes_df.sort_values("data", ascending=False)

        # Rozdziel dane 2026 vs historia
        jes_2026 = jes_df[jes_df["rok"] == 2026]
        jes_hist = jes_df[jes_df["rok"] < 2026]

        # KPI — jesień 2026 z porównaniem do śr. historycznej
        st.subheader("Jesień 2026 — aktualny stan sprzedaży")

        # Średnie historyczne per event (do porównania)
        if not jes_hist.empty:
            hist_per_ev = jes_hist.groupby("miasto").agg(
                sr_zamowien=("zamowien", "mean"),
                sr_m2=("m2", "mean"),
                sr_przychod=("przychod_stoiska", "mean"),
            )

        kj1, kj2, kj3, kj4, kj5 = st.columns(5)
        kj1.metric("Eventów jesień 2026", len(jes_2026))
        kj2.metric("Zamówienia (łącznie)", int(jes_2026["zamowien"].sum()))
        kj3.metric("Przychód ze stoisk", f"{jes_2026['przychod_stoiska'].sum():,.0f} zł")
        kj4.metric("Sprzedane m²", f"{jes_2026['m2'].sum():,.0f}")
        kj5.metric("Dni do pierwszego eventu",
                    max(0, (pd.to_datetime(jes_2026["data"].min()) - pd.Timestamp.now()).days))

        # ── PROGNOZA SPRZEDAŻY ──────────────────────────────────────
        st.divider()
        st.subheader("Prognoza sprzedaży — jesień 2026")
        st.caption("Na podstawie historycznego rozkładu zamówień wg miesięcy przed eventem")

        # Oblicz historyczny wzorzec sprzedaży per miasto
        zam_jes_timing = zam_jes.copy()
        zam_jes_timing["data_utw_dt"] = pd.to_datetime(zam_jes_timing["data_utw"], errors="coerce")
        if "miasto" in zam_jes_timing.columns:
            zam_jes_timing = zam_jes_timing.drop(columns=["miasto"])
        zam_jes_timing = zam_jes_timing.merge(
            ev_jesien[["id", "data_dt", "miasto", "rok_n"]].rename(columns={"id": "ev_id", "data_dt": "data_eventu"}),
            left_on="idtargi_n", right_on="ev_id", how="left"
        )
        zam_jes_timing["dni_przed"] = (zam_jes_timing["data_eventu"] - zam_jes_timing["data_utw_dt"]).dt.days
        zam_jes_timing["mies_przed"] = (zam_jes_timing["dni_przed"] / 30.44).round(0).astype(int)

        hist_timing = zam_jes_timing[zam_jes_timing["rok_n"] < 2026]
        cur_timing = zam_jes_timing[zam_jes_timing["rok_n"] == 2026]

        prognoza_rows = []
        for _, ev26 in jes_2026.iterrows():
            miasto = ev26["miasto"]
            ev_data = pd.to_datetime(ev26["data"])
            ev_id = int(ev26["ev_id"])

            h = hist_timing[hist_timing["miasto"] == miasto]
            if len(h) == 0:
                continue

            h_total_per_ev = h.groupby("ev_id")["id"].count().mean()
            h_dist = h.groupby("mies_przed")["id"].count()
            h_dist_pct = (h_dist / h_dist.sum()).to_dict()

            hist_same = jes_hist[jes_hist["miasto"] == miasto]
            last_year = hist_same[hist_same["rok"] == hist_same["rok"].max()]
            last_year_zam = last_year["zamowien"].sum() if len(last_year) > 0 else h_total_per_ev

            # Ręczne cele sprzedażowe per miasto (stała globalna — patrz góra pliku)
            cel_100pct = CELE_JESIEN_2026.get(miasto, int(last_year_zam * 2))

            cur_ev = cur_timing[cur_timing["ev_id"] == ev_id]
            aktualnie = len(cur_ev)

            dni_do = (ev_data - pd.Timestamp.now()).days
            mies_do = max(0, round(dni_do / 30.44))

            pct_pozostale = sum(v for k, v in h_dist_pct.items() if k <= mies_do)
            pct_juz = 1 - pct_pozostale

            # Prognoza: aktualnie sprzedane + oczekiwana reszta (z historii)
            # Im bliżej eventu (pct_juz rośnie), tym mniejsza "reszta" historyczna
            # Im dalej od eventu, tym prognoza bliższa średniej hist. + aktualne zamówienia
            prog_hist = round(h_total_per_ev)
            prognoza_total = max(aktualnie, round(aktualnie + (1 - pct_juz) * h_total_per_ev))

            prognoza_rows.append({
                "Event": ev26["symbol"],
                "Miasto": miasto,
                "Data eventu": ev_data.strftime("%Y-%m-%d"),
                "Dni do eventu": dni_do,
                "Zeszły rok": int(last_year_zam),
                "Cel": cel_100pct,
                "Aktualnie": aktualnie,
                "% hist. wzorca": round(pct_juz * 100, 1),
                "Prognoza końcowa": prognoza_total,
                "Brakuje do celu": max(0, cel_100pct - aktualnie),
                "Prognoza vs cel": round(prognoza_total / cel_100pct * 100, 1) if cel_100pct > 0 else 0,
            })

        if prognoza_rows:
            prog_df = pd.DataFrame(prognoza_rows)

            st.dataframe(
                prog_df.style.format({
                    "% hist. wzorca": "{:.1f}%",
                    "Prognoza vs cel": "{:.1f}%",
                }).apply(lambda x: [
                    "background-color: #d4edda" if v >= 80 else
                    "background-color: #fff3cd" if v >= 50 else
                    "background-color: #f8d7da"
                    for v in x
                ] if x.name == "Prognoza vs cel" else [""] * len(x), axis=0),
                use_container_width=True, hide_index=True,
            )

            with st.expander("Jak czytać tę tabelę?"):
                st.markdown("""
**Kolumny:**
- **Zeszły rok** — ile zamówień miał ten event w ostatniej edycji jesiennej
- **Cel** — cel sprzedażowy ustalony dla danego miasta
- **Aktualnie** — ile zamówień już wpłynęło na ten event
- **% hist. wzorca** — jaki % wszystkich zamówień historycznie wpływał do tego momentu (tyle miesięcy przed eventem). Jeśli 0% — znaczy, że historycznie w tym okresie jeszcze żadne zamówienia nie wpływały
- **Prognoza końcowa** — przewidywana liczba zamówień na koniec sprzedaży, obliczona na podstawie aktualnego tempa i historycznego wzorca
- **Brakuje do celu** — ile zamówień trzeba jeszcze pozyskać, żeby osiągnąć cel 2x
- **Prognoza vs cel** — czy prognoza osiągnie cel? >100% = przekroczymy cel, <100% = nie dojdziemy

**Kolory w kolumnie "Prognoza vs cel":**
- :green[Zielony] (>=80%) — na dobrej drodze do osiągnięcia celu
- :orange[Żółty] (50-79%) — wymaga uwagi, sprzedaż poniżej oczekiwań
- :red[Czerwony] (<50%) — alarm, znacząco poniżej celu

**Uwaga:** Prognoza jest najbardziej wiarygodna gdy **% hist. wzorca > 30%**. Przy niskim % (np. 0-10%) prognoza opiera się na bardzo małej próbce i może być niedokładna.
""")

            st.subheader("Aktualny stan vs cel (2x zeszły rok)")
            prog_chart = prog_df[["Event", "Aktualnie", "Cel", "Prognoza końcowa"]].melt(
                id_vars="Event", var_name="Typ", value_name="Zamówień"
            )
            fig = px.bar(prog_chart, x="Event", y="Zamówień", color="Typ",
                         barmode="group",
                         color_discrete_map={
                             "Aktualnie": COLORS[2],
                             "Cel": COLORS[1],
                             "Prognoza końcowa": COLORS[4],
                         },
                         text="Zamówień")
            fig.update_traces(textposition="outside", textfont_size=10)
            fig.update_layout(legend_title="", xaxis_title="")
            st.plotly_chart(fig, use_container_width=True)

            st.subheader("Kiedy wpływają zamówienia? (historyczny wzorzec)")
            with st.expander("Jak czytać te wykresy?"):
                st.markdown("""
**Lewy wykres — % zamówień per miesiąc przed eventem:**
Pokazuje w którym momencie przed targami historycznie wpływały zamówienia na stoiska.
Np. "2 mies. przed = 21.7%" oznacza, że co piąte zamówienie wpływa na 2 miesiące przed wydarzeniem.

**Prawy wykres — skumulowany % zamówień:**
Pokazuje ile % wszystkich zamówień jest już złożonych na X miesięcy przed eventem.
Np. "3 mies. przed = 62.1%" oznacza, że na 3 miesiące przed targami mamy dopiero ~62% zamówień — reszta wpłynie w ostatnich 3 miesiącach.

**Kluczowe wnioski:**
- Sprzedaż startuje ~7 mies. przed eventem (pierwsza fala ~15% zamówień)
- Pik sprzedaży to 1-2 miesiące przed eventem (~40% zamówień)
- Na miesiąc przed targami brakuje jeszcze ~15-20% zamówień
- Zamówienia wpływają nawet w miesiącu eventu (~8%)

**Jak to wykorzystać:** Jeśli na 3 mies. przed eventem mamy mniej niż 62% celu — zintensyfikujmy działania sprzedażowe. Jeśli mamy więcej — jesteśmy powyżej normy.
""")
            hist_dist_all = hist_timing.groupby("mies_przed")["id"].count().reset_index(name="zamowien")
            hist_dist_all["pct"] = (hist_dist_all["zamowien"] / hist_dist_all["zamowien"].sum() * 100).round(1)
            hist_dist_all["pct_kum"] = hist_dist_all["pct"].cumsum().round(1)
            hist_dist_all = hist_dist_all.sort_values("mies_przed", ascending=False)
            hist_dist_all["label"] = hist_dist_all["mies_przed"].apply(
                lambda x: f"{x} mies. przed" if x >= 0 else f"{abs(x)} mies. po"
            )

            col_p1, col_p2 = st.columns(2)
            with col_p1:
                fig = px.bar(hist_dist_all, x="label", y="pct",
                             title="% zamówień per miesiąc przed eventem",
                             color_discrete_sequence=[COLORS[0]], text="pct")
                fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
                fig.update_layout(xaxis_title="", yaxis_title="% zamówień")
                st.plotly_chart(fig, use_container_width=True)

            with col_p2:
                hist_dist_kum = hist_dist_all.sort_values("mies_przed", ascending=True)
                fig = px.line(hist_dist_kum, x="label", y="pct_kum",
                              title="Skumulowany % zamówień (od najwcześniejszych)",
                              color_discrete_sequence=[COLORS[2]], markers=True, text="pct_kum")
                fig.update_traces(texttemplate="%{text:.1f}%", textposition="top center")
                fig.update_layout(xaxis_title="", yaxis_title="% skumulowany")
                st.plotly_chart(fig, use_container_width=True)

            st.subheader("Plan sprzedaży miesięczny per event")
            with st.expander("Jak czytać te tabele?"):
                st.markdown("""
**Kolumny:**
- **Miesiąc** — miesiąc kalendarzowy
- **Mies. przed** — ile miesięcy przed datą eventu (0 = miesiąc eventu)
- **% hist.** — jaki procent wszystkich zamówień historycznie wpływał w tym miesiącu przed eventem
- **Plan zamówień** — ile zamówień powinno wpłynąć w tym miesiącu żeby osiągnąć cel (na podstawie historycznego rozkładu)
- **Realizacja** — ile zamówień faktycznie wpłynęło w tym miesiącu
- **Plan kum.** — planowana suma narastająca zamówień
- **Real. kum.** — faktyczna suma narastająca zamówień
- **% planu** — realizacja kumulatywna vs plan kumulatywny (ile % planu zrealizowano na dany moment)
- **% celu** — realizacja kumulatywna jako procent celu końcowego

**Wykres pod tabelą:**
- Półprzezroczyste słupki = plan miesięczny, kolorowe = realizacja
- Przerywana linia = plan kumulatywny, ciągła = realizacja kumulatywna
- Czerwona linia przerywana = cel końcowy
""")
            for _, ev26 in jes_2026.iterrows():
                miasto = ev26["miasto"]
                ev_data = pd.to_datetime(ev26["data"])
                ev_id = int(ev26["ev_id"])

                h = hist_timing[hist_timing["miasto"] == miasto]
                if len(h) == 0:
                    continue

                prog_row = prog_df[prog_df["Event"] == ev26["symbol"]].iloc[0]
                cel = prog_row["Cel"]

                h_dist = h.groupby("mies_przed")["id"].count()
                h_dist_pct = (h_dist / h_dist.sum())

                cur_ev = cur_timing[cur_timing["ev_id"] == ev_id]
                cur_per_mies = cur_ev.groupby("mies_przed")["id"].count().to_dict()
                aktualnie_total = len(cur_ev)

                # Zakres miesięcy: od najwcześniejszego z historii LUB z aktualnych zamówień, do 0
                all_mies_przed = set(h_dist_pct.index) | set(cur_per_mies.keys())
                # Pomijamy ujemne (po evencie) i ograniczamy do max sensownego zakresu
                mies_range = sorted([m for m in all_mies_przed if m >= 0], reverse=True)

                plan_rows = []
                for mp in mies_range:
                    mies_data = ev_data - pd.DateOffset(months=mp)
                    plan_zam = round(cel * h_dist_pct.get(mp, 0))
                    realizacja = cur_per_mies.get(mp, 0)
                    plan_rows.append({
                        "Miesiąc": mies_data.strftime("%Y-%m"),
                        "Mies. przed": mp,
                        "% hist.": round(h_dist_pct.get(mp, 0) * 100, 1),
                        "Plan zamówień": plan_zam,
                        "Realizacja": int(realizacja),
                    })

                plan_df = pd.DataFrame(plan_rows)
                plan_df = plan_df[plan_df["Mies. przed"] >= 0]
                plan_df["Plan kum."] = plan_df["Plan zamówień"].cumsum()
                plan_df["Real. kum."] = plan_df["Realizacja"].cumsum()
                plan_df["% planu"] = (plan_df["Real. kum."] / plan_df["Plan kum."].replace(0, 1) * 100).round(0)
                plan_df["% celu"] = (plan_df["Real. kum."] / cel * 100).round(1)

                with st.expander(f"{ev26['symbol']} — {miasto} ({ev_data.strftime('%Y-%m-%d')}) | Cel: {cel} zamówień | Aktualnie: {aktualnie_total}"):
                    st.dataframe(plan_df.style.format({
                        "% hist.": "{:.1f}%",
                        "% planu": "{:.0f}%",
                        "% celu": "{:.1f}%",
                    }), hide_index=True, use_container_width=True)

                    fig = go.Figure()
                    fig.add_trace(go.Bar(
                        x=plan_df["Miesiąc"], y=plan_df["Plan zamówień"],
                        name="Plan miesięczny", marker_color=COLORS[0],
                        text=plan_df["Plan zamówień"], textposition="outside",
                        opacity=0.5,
                    ))
                    fig.add_trace(go.Bar(
                        x=plan_df["Miesiąc"], y=plan_df["Realizacja"],
                        name="Realizacja", marker_color=COLORS[2],
                        text=plan_df["Realizacja"], textposition="outside",
                    ))
                    fig.add_trace(go.Scatter(
                        x=plan_df["Miesiąc"], y=plan_df["Plan kum."],
                        name="Plan kumulat.", mode="lines+markers",
                        line=dict(color=COLORS[0], width=2, dash="dash"),
                    ))
                    fig.add_trace(go.Scatter(
                        x=plan_df["Miesiąc"], y=plan_df["Real. kum."],
                        name="Realizacja kumulat.", mode="lines+markers+text",
                        line=dict(color=COLORS[2], width=2),
                        text=plan_df["Real. kum."], textposition="top center",
                    ))
                    fig.add_hline(y=cel, line_dash="dash", line_color="red",
                                  annotation_text=f"Cel: {cel}")
                    fig.update_layout(
                        title=f"Plan sprzedaży — {ev26['symbol']}",
                        xaxis_title="", yaxis_title="Zamówienia",
                        legend=dict(orientation="h", y=-0.2),
                    )
                    st.plotly_chart(fig, use_container_width=True)

        st.divider()

        # Tabela per event 2026 z porównaniem do historii
        st.subheader("Postęp sprzedaży per event — jesień 2026")
        with st.expander("Jak czytać tę tabelę?"):
            st.markdown("""
**Kolumny:**
- **Zamówień** — ile zamówień aktualnie ma ten event (status: w realizacji)
- **Śr. hist.** — średnia liczba zamówień z poprzednich jesiennych edycji tego miasta
- **% normy (zam.)** — aktualnie zamówień vs średnia historyczna (100% = na poziomie średniej)
- **m²** — łącznie sprzedanych metrów kwadratowych
- **Śr. m² hist.** — średnia historyczna m² dla tego miasta
- **% normy (m²)** — jak wyżej, ale dla metrów kwadratowych
- **Przychód stoiska** — aktualny przychód netto ze stoisk
- **Śr. przych. hist.** — średni historyczny przychód dla tego miasta
- **% normy (przych.)** — aktualny przychód vs średnia historyczna
- **Cena/m²** — aktualna średnia cena za metr kwadratowy
""")

        display_rows = []
        for _, ev26 in jes_2026.iterrows():
            miasto = ev26["miasto"]
            hist_miasto = jes_hist[jes_hist["miasto"] == miasto]
            sr_zam = hist_miasto["zamowien"].mean() if len(hist_miasto) > 0 else 0
            sr_m2 = hist_miasto["m2"].mean() if len(hist_miasto) > 0 else 0
            sr_prz = hist_miasto["przychod_stoiska"].mean() if len(hist_miasto) > 0 else 0

            pct_zam = round(ev26["zamowien"] / sr_zam * 100, 0) if sr_zam > 0 else 0
            pct_m2 = round(ev26["m2"] / sr_m2 * 100, 0) if sr_m2 > 0 else 0
            pct_prz = round(ev26["przychod_stoiska"] / sr_prz * 100, 0) if sr_prz > 0 else 0

            display_rows.append({
                "Event": ev26["symbol"],
                "Miasto": miasto,
                "Data": ev26["data"],
                "Zamówień": ev26["zamowien"],
                "Śr. hist.": round(sr_zam, 0),
                "% normy (zam.)": pct_zam,
                "m²": ev26["m2"],
                "Śr. m² hist.": round(sr_m2, 0),
                "% normy (m²)": pct_m2,
                "Przychód stoiska": ev26["przychod_stoiska"],
                "Śr. przych. hist.": round(sr_prz, 0),
                "% normy (przych.)": pct_prz,
                "Cena/m²": ev26["cena_m2"],
            })

        disp_2026 = pd.DataFrame(display_rows)
        disp_2026["Data"] = pd.to_datetime(disp_2026["Data"]).dt.strftime("%Y-%m-%d")
        st.dataframe(
            disp_2026.style.format({
                "Śr. hist.": "{:.0f}", "% normy (zam.)": "{:.0f}%",
                "Śr. m² hist.": "{:.0f}", "% normy (m²)": "{:.0f}%",
                "Przychód stoiska": "{:,.0f} zł", "Śr. przych. hist.": "{:,.0f} zł",
                "% normy (przych.)": "{:.0f}%", "Cena/m²": "{:.0f} zł",
                "m²": "{:.0f}",
            }),
            use_container_width=True, hide_index=True,
        )

        # Wykres: % normy per event
        st.subheader("Realizacja vs średnia historyczna")
        norma_df = pd.DataFrame(display_rows)
        norma_melt = norma_df[["Event", "% normy (zam.)", "% normy (m²)", "% normy (przych.)"]].melt(
            id_vars="Event", var_name="Wskaźnik", value_name="% normy"
        )
        fig = px.bar(norma_melt, x="Event", y="% normy", color="Wskaźnik",
                     barmode="group", color_discrete_sequence=[COLORS[0], COLORS[2], COLORS[4]],
                     text="% normy")
        fig.update_traces(texttemplate="%{text:.0f}%", textposition="outside", textfont_size=9)
        fig.add_hline(y=100, line_dash="dash", line_color="red",
                      annotation_text="100% = średnia historyczna", annotation_position="top left")
        fig.update_layout(xaxis_title="", yaxis_title="% realizacji vs historia", legend_title="")
        st.plotly_chart(fig, use_container_width=True)

        st.divider()

        # Porównanie historyczne per miasto
        st.subheader("Porównanie z poprzednimi latami (te same miasta)")

        # Tabela historyczna
        display_jes_all = jes_df[[
            "symbol", "miasto", "data", "zamowien", "m2", "sr_m2_stoisko", "cena_m2",
            "przychod_stoiska", "osoby_bilety", "sr_cena_bilet", "przychod_bilety",
            "przychod_lacznie", "wejscia", "frekwencja"
        ]].copy()
        display_jes_all.columns = [
            "Event", "Miasto", "Data", "Zamówień", "m²", "Śr. m²/stoisko", "Cena/m²",
            "Przychód stoiska", "Osoby (bilety)", "Śr. cena biletu", "Przychód bilety",
            "Przychód łącznie", "Wejścia", "Frekwencja %"
        ]
        display_jes_all["Data"] = pd.to_datetime(display_jes_all["Data"]).dt.strftime("%Y-%m-%d")
        st.dataframe(
            display_jes_all.style.format({
                "Cena/m²": "{:.0f} zł", "Przychód stoiska": "{:,.0f} zł",
                "Śr. cena biletu": "{:.0f} zł", "Przychód bilety": "{:,.0f} zł",
                "Przychód łącznie": "{:,.0f} zł", "Frekwencja %": "{:.1f}%",
                "m²": "{:.0f}", "Śr. m²/stoisko": "{:.1f}",
            }),
            use_container_width=True, hide_index=True,
        )

        st.divider()

        # Wykresy porównawcze
        st.subheader("Porównanie rok do roku")

        # Przychód ze stoisk per miasto/rok
        col_j1, col_j2 = st.columns(2)

        with col_j1:
            jes_miasto_rok = jes_df.groupby(["miasto", "rok"]).agg(
                przychod=("przychod_stoiska", "sum"),
            ).reset_index()
            jes_miasto_rok["rok"] = jes_miasto_rok["rok"].astype(str)
            fig = px.bar(jes_miasto_rok, x="miasto", y="przychod", color="rok",
                         title="Przychód ze stoisk — jesień per miasto/rok",
                         color_discrete_sequence=COLORS, barmode="group",
                         text="przychod")
            fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside", textfont_size=9)
            fig.update_layout(xaxis_title="", yaxis_title="zł netto", legend_title="Rok")
            st.plotly_chart(fig, use_container_width=True)

        with col_j2:
            jes_m2_rok = jes_df.groupby(["miasto", "rok"]).agg(
                m2=("m2", "sum"),
            ).reset_index()
            jes_m2_rok["rok"] = jes_m2_rok["rok"].astype(str)
            fig = px.bar(jes_m2_rok, x="miasto", y="m2", color="rok",
                         title="Sprzedane m² — jesień per miasto/rok",
                         color_discrete_sequence=COLORS, barmode="group",
                         text="m2")
            fig.update_traces(texttemplate="%{text:.0f}", textposition="outside", textfont_size=9)
            fig.update_layout(xaxis_title="", yaxis_title="m²", legend_title="Rok")
            st.plotly_chart(fig, use_container_width=True)

        col_j3, col_j4 = st.columns(2)

        with col_j3:
            jes_zamowien_rok = jes_df.groupby(["miasto", "rok"]).agg(
                zamowien=("zamowien", "sum"),
            ).reset_index()
            jes_zamowien_rok["rok"] = jes_zamowien_rok["rok"].astype(str)
            fig = px.bar(jes_zamowien_rok, x="miasto", y="zamowien", color="rok",
                         title="Zamówienia — jesień per miasto/rok",
                         color_discrete_sequence=COLORS, barmode="group",
                         text="zamowien")
            fig.update_traces(textposition="outside", textfont_size=9)
            fig.update_layout(xaxis_title="", yaxis_title="Zamówień", legend_title="Rok")
            st.plotly_chart(fig, use_container_width=True)

        with col_j4:
            jes_cena_src = jes_df[jes_df["m2"] > 0].groupby(["miasto", "rok"]).agg(
                przychod_sum=("przychod_stoiska", "sum"),
                m2_sum=("m2", "sum"),
            ).reset_index()
            jes_cena_src["cena_m2"] = jes_cena_src["przychod_sum"] / jes_cena_src["m2_sum"]
            jes_cena_rok = jes_cena_src
            jes_cena_rok["rok"] = jes_cena_rok["rok"].astype(str)
            fig = px.bar(jes_cena_rok, x="miasto", y="cena_m2", color="rok",
                         title="Śr. cena za m² — jesień per miasto/rok",
                         color_discrete_sequence=COLORS, barmode="group",
                         text="cena_m2")
            fig.update_traces(texttemplate="%{text:.0f} zł", textposition="outside", textfont_size=9)
            fig.update_layout(xaxis_title="", yaxis_title="zł / m²", legend_title="Rok")
            st.plotly_chart(fig, use_container_width=True)

        col_j5, col_j6 = st.columns(2)

        with col_j5:
            jes_osoby_rok = jes_df.groupby(["miasto", "rok"]).agg(
                osoby=("osoby_bilety", "sum"),
            ).reset_index()
            jes_osoby_rok["rok"] = jes_osoby_rok["rok"].astype(str)
            fig = px.bar(jes_osoby_rok, x="miasto", y="osoby", color="rok",
                         title="Osoby (bilety) — jesień per miasto/rok",
                         color_discrete_sequence=COLORS, barmode="group",
                         text="osoby")
            fig.update_traces(textposition="outside", textfont_size=9)
            fig.update_layout(xaxis_title="", yaxis_title="Osób", legend_title="Rok")
            st.plotly_chart(fig, use_container_width=True)

        with col_j6:
            jes_frekw_src = jes_df[jes_df["osoby_bilety"] > 0].groupby(["miasto", "rok"]).agg(
                wejscia_sum=("wejscia", "sum"),
                osoby_sum=("osoby_bilety", "sum"),
            ).reset_index()
            jes_frekw_src["frekwencja"] = jes_frekw_src["wejscia_sum"] / jes_frekw_src["osoby_sum"] * 100
            jes_frekw_rok = jes_frekw_src
            jes_frekw_rok["rok"] = jes_frekw_rok["rok"].astype(str)
            fig = px.bar(jes_frekw_rok, x="miasto", y="frekwencja", color="rok",
                         title="Frekwencja % — jesień per miasto/rok",
                         color_discrete_sequence=COLORS, barmode="group",
                         text="frekwencja")
            fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside", textfont_size=9)
            fig.update_layout(xaxis_title="", yaxis_title="%", legend_title="Rok")
            st.plotly_chart(fig, use_container_width=True)

        # Trend roczny — łączne przychody jesień
        st.divider()
        st.subheader("Trend roczny — jesień łącznie")

        col_jt1, col_jt2 = st.columns(2)
        jes_rok = jes_df.groupby("rok").agg(
            przychod_stoiska=("przychod_stoiska", "sum"),
            przychod_bilety=("przychod_bilety", "sum"),
            przychod_lacznie=("przychod_lacznie", "sum"),
            zamowien=("zamowien", "sum"),
            m2=("m2", "sum"),
            osoby=("osoby_bilety", "sum"),
            eventow=("symbol", "count"),
        ).reset_index()

        with col_jt1:
            jes_rok_melt = jes_rok[["rok", "przychod_stoiska", "przychod_bilety"]].melt(
                id_vars="rok", var_name="typ", value_name="przychod"
            )
            jes_rok_melt["typ"] = jes_rok_melt["typ"].map({
                "przychod_stoiska": "Stoiska",
                "przychod_bilety": "Bilety",
            })
            fig = px.bar(jes_rok_melt, x="rok", y="przychod", color="typ",
                         title="Łączny przychód jesień — stoiska vs bilety",
                         color_discrete_sequence=[COLORS[2], COLORS[0]],
                         text="przychod", barmode="stack")
            fig.update_traces(texttemplate="%{text:,.0f}", textfont_size=9)
            fig.update_xaxes(dtick=1)
            # Dodaj łączną sumę na szczycie
            for _, row in jes_rok.iterrows():
                fig.add_annotation(
                    x=row["rok"], y=row["przychod_lacznie"],
                    text=f"<b>{row['przychod_lacznie']:,.0f}</b>",
                    showarrow=False, yshift=14, font=dict(size=11),
                )
            fig.update_layout(xaxis_title="Rok", yaxis_title="zł netto", legend_title="")
            st.plotly_chart(fig, use_container_width=True)

        with col_jt2:
            fig = px.bar(jes_rok, x="rok", y="zamowien",
                         title="Zamówienia jesień — trend roczny",
                         color_discrete_sequence=[COLORS[4]], text="zamowien")
            fig.update_traces(textposition="outside")
            fig.update_xaxes(dtick=1)
            fig.update_layout(xaxis_title="Rok", yaxis_title="Zamówień")
            st.plotly_chart(fig, use_container_width=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 7 — Analizy i wnioski
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab7:
    st.header("Analizy i wnioski")

    # ── Przygotowanie danych per event ──
    ev_analiza = ev_filtered.copy()

    # Zamówienia per event
    zam_per_ev = zam_active.groupby("idtargi").agg(
        zamowien=("id", "count"),
        przychod_stoiska=("kwota_netto_n", "sum"),
        m2=("ilem2_n", "sum"),
    ).reset_index()
    zam_per_ev["idtargi"] = zam_per_ev["idtargi"].astype(str)
    zam_per_ev["cena_m2"] = (zam_per_ev["przychod_stoiska"] / zam_per_ev["m2"]).replace([np.inf, -np.inf], 0).fillna(0)

    # Bilety per event
    bil_per_ev = bil_f.groupby("idtargi").agg(
        osoby_bilety=("ileosob_n", "sum"),
        przychod_bilety=("kwota_netto_n", "sum"),
    ).reset_index()
    bil_per_ev["cena_bilet"] = (bil_per_ev["przychod_bilety"] / bil_per_ev["osoby_bilety"]).replace([np.inf, -np.inf], 0).fillna(0)

    # Wejścia per event
    wej_per_ev = bil_wejscia.groupby("idtargi").agg(
        osoby_wejscia=("ileosob_n", "sum"),
    ).reset_index()

    # Złączenie
    analiza = ev_analiza.merge(zam_per_ev, left_on=ev_analiza["id"].astype(str), right_on="idtargi", how="left") \
                        .merge(bil_per_ev, left_on="id", right_on="idtargi", how="left") \
                        .merge(wej_per_ev, left_on="id", right_on="idtargi", how="left") \
                        .fillna(0)
    analiza["konwersja"] = (analiza["osoby_wejscia"] / analiza["osoby_bilety"] * 100).replace([np.inf, -np.inf], 0).fillna(0)
    analiza["przychod_total"] = analiza["przychod_stoiska"] + analiza["przychod_bilety"]
    analiza = analiza[analiza["przychod_total"] > 0]  # tylko eventy z danymi

    # ── Helper do korelacji ──
    def korelacja_opis(r, p):
        sila = abs(r)
        if sila < 0.3:
            opis_sily = "Słaba"
        elif sila < 0.6:
            opis_sily = "Umiarkowana"
        elif sila < 0.8:
            opis_sily = "Silna"
        else:
            opis_sily = "Bardzo silna"
        kierunek = "dodatnia" if r > 0 else "ujemna"
        istotnosc = "istotna statystycznie" if p < 0.05 else "nieistotna statystycznie"
        return f"{opis_sily} korelacja {kierunek} (r={r:.2f}, p={p:.3f}) — {istotnosc}"

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 1. KORELACJE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    st.subheader("1. Korelacje cenowe")

    col1, col2 = st.columns(2)

    with col1:
        # Cena m² vs sprzedane m²
        a_valid = analiza[(analiza["cena_m2"] > 0) & (analiza["m2"] > 0)]
        if len(a_valid) > 3:
            r, p = stats.pearsonr(a_valid["cena_m2"], a_valid["m2"])
            fig = px.scatter(a_valid, x="cena_m2", y="m2", hover_name="symbol",
                             color="miasto", trendline="ols",
                             title="Cena za m² vs sprzedane m²",
                             color_discrete_sequence=COLORS)
            fig.update_layout(xaxis_title="Cena za m² (zł)", yaxis_title="Sprzedane m²")
            st.plotly_chart(fig, use_container_width=True)
            st.info(f"**Wynik:** {korelacja_opis(r, p)}")
        else:
            st.warning("Za mało danych do analizy korelacji cena m² vs sprzedaż m²")

    with col2:
        # Cena m² vs przychód ze stoisk
        if len(a_valid) > 3:
            r, p = stats.pearsonr(a_valid["cena_m2"], a_valid["przychod_stoiska"])
            fig = px.scatter(a_valid, x="cena_m2", y="przychod_stoiska", hover_name="symbol",
                             color="miasto", trendline="ols",
                             title="Cena za m² vs przychód ze stoisk",
                             color_discrete_sequence=COLORS)
            fig.update_layout(xaxis_title="Cena za m² (zł)", yaxis_title="Przychód netto (zł)")
            st.plotly_chart(fig, use_container_width=True)
            st.info(f"**Wynik:** {korelacja_opis(r, p)}")

    # ── Analiza YoY per miasto: zmiana ceny m² vs zmiana przychodu/zamówień ──
    st.divider()
    st.subheader("1b. Wpływ zmiany ceny m² na sprzedaż — porównanie YoY per miasto")

    miasto_rok = analiza[analiza["cena_m2"] > 0].groupby(["miasto", "rok"]).agg(
        sr_cena_m2=("cena_m2", "mean"),
        total_m2=("m2", "sum"),
        total_przychod_st=("przychod_stoiska", "sum"),
        zamowien=("zamowien", "sum"),
    ).reset_index().sort_values(["miasto", "rok"])

    yoy_rows = []
    for miasto in miasto_rok["miasto"].unique():
        df_m = miasto_rok[miasto_rok["miasto"] == miasto].sort_values("rok")
        for i in range(1, len(df_m)):
            prev = df_m.iloc[i - 1]
            curr = df_m.iloc[i]
            if prev["sr_cena_m2"] > 0 and prev["total_m2"] > 0 and prev["total_przychod_st"] > 0 and prev["zamowien"] > 0:
                yoy_rows.append({
                    "miasto": miasto,
                    "rok": f"{int(prev['rok'])}→{int(curr['rok'])}",
                    "zmiana_ceny_m2_pct": (curr["sr_cena_m2"] / prev["sr_cena_m2"] - 1) * 100,
                    "zmiana_m2_pct": (curr["total_m2"] / prev["total_m2"] - 1) * 100,
                    "zmiana_przychodu_pct": (curr["total_przychod_st"] / prev["total_przychod_st"] - 1) * 100,
                    "zmiana_zamowien_pct": (curr["zamowien"] / prev["zamowien"] - 1) * 100,
                    "cena_m2_prev": prev["sr_cena_m2"],
                    "cena_m2_curr": curr["sr_cena_m2"],
                })

    if yoy_rows:
        yoy = pd.DataFrame(yoy_rows)

        col_a, col_b = st.columns(2)

        with col_a:
            fig = px.scatter(yoy, x="zmiana_ceny_m2_pct", y="zmiana_przychodu_pct",
                             hover_name="rok", color="miasto", trendline="ols",
                             title="Zmiana ceny m² vs zmiana przychodu (YoY %)",
                             color_discrete_sequence=COLORS)
            fig.add_hline(y=0, line_dash="dash", line_color="gray")
            fig.add_vline(x=0, line_dash="dash", line_color="gray")
            fig.update_layout(xaxis_title="Zmiana ceny m² (%)", yaxis_title="Zmiana przychodu (%)")
            st.plotly_chart(fig, use_container_width=True)

            yoy_valid = yoy.dropna(subset=["zmiana_ceny_m2_pct", "zmiana_przychodu_pct"])
            if len(yoy_valid) > 3:
                r, p = stats.pearsonr(yoy_valid["zmiana_ceny_m2_pct"], yoy_valid["zmiana_przychodu_pct"])
                st.info(f"**Wynik:** {korelacja_opis(r, p)}")

        with col_b:
            fig = px.scatter(yoy, x="zmiana_ceny_m2_pct", y="zmiana_zamowien_pct",
                             hover_name="rok", color="miasto", trendline="ols",
                             title="Zmiana ceny m² vs zmiana liczby zamówień (YoY %)",
                             color_discrete_sequence=COLORS)
            fig.add_hline(y=0, line_dash="dash", line_color="gray")
            fig.add_vline(x=0, line_dash="dash", line_color="gray")
            fig.update_layout(xaxis_title="Zmiana ceny m² (%)", yaxis_title="Zmiana zamówień (%)")
            st.plotly_chart(fig, use_container_width=True)

            if len(yoy_valid) > 3:
                r2, p2 = stats.pearsonr(yoy_valid["zmiana_ceny_m2_pct"], yoy_valid["zmiana_zamowien_pct"])
                st.info(f"**Wynik:** {korelacja_opis(r2, p2)}")

        # Analiza praktyczna
        wzrost_ceny = yoy[yoy["zmiana_ceny_m2_pct"] > 0]
        if len(wzrost_ceny) > 0:
            spadek_przychodu = wzrost_ceny[wzrost_ceny["zmiana_przychodu_pct"] < 0]
            spadek_zamowien = wzrost_ceny[wzrost_ceny["zmiana_zamowien_pct"] < 0]
            pct_spadek_p = len(spadek_przychodu) / len(wzrost_ceny) * 100
            pct_spadek_z = len(spadek_zamowien) / len(wzrost_ceny) * 100
            sr_wzrost_ceny = wzrost_ceny["zmiana_ceny_m2_pct"].mean()
            sr_spadek_przychodu = wzrost_ceny["zmiana_przychodu_pct"].mean()
            sr_spadek_zamowien = wzrost_ceny["zmiana_zamowien_pct"].mean()

            st.error(
                f"**Kluczowy wniosek:** W **{pct_spadek_p:.0f}%** przypadków ({len(spadek_przychodu)} z {len(wzrost_ceny)}) "
                f"wzrost ceny za m² skutkował **spadkiem przychodu**.  \n"
                f"Średnio: wzrost ceny o **{sr_wzrost_ceny:.1f}%** → spadek przychodu o **{abs(sr_spadek_przychodu):.1f}%**, "
                f"spadek zamówień o **{abs(sr_spadek_zamowien):.1f}%**."
            )

        st.markdown("**Szczegółowe zmiany per miasto rok do roku:**")
        yoy_display = yoy[["miasto", "rok", "cena_m2_prev", "cena_m2_curr",
                           "zmiana_ceny_m2_pct", "zmiana_przychodu_pct", "zmiana_zamowien_pct", "zmiana_m2_pct"]].copy()
        yoy_display.columns = ["Miasto", "Okres", "Cena m² przed", "Cena m² po",
                               "Zmiana ceny %", "Zmiana przychodu %", "Zmiana zamówień %", "Zmiana m² %"]
        yoy_display = yoy_display.round(1)
        st.dataframe(yoy_display, use_container_width=True, hide_index=True)
    else:
        st.warning("Za mało danych do analizy YoY per miasto")

    st.divider()

    col3, col4 = st.columns(2)

    with col3:
        # Cena biletu vs liczba osób
        b_valid = analiza[(analiza["cena_bilet"] > 0) & (analiza["osoby_bilety"] > 0)]
        if len(b_valid) > 3:
            r, p = stats.pearsonr(b_valid["cena_bilet"], b_valid["osoby_bilety"])
            fig = px.scatter(b_valid, x="cena_bilet", y="osoby_bilety", hover_name="symbol",
                             color="miasto", trendline="ols",
                             title="Cena biletu vs liczba osób (bilety)",
                             color_discrete_sequence=COLORS)
            fig.update_layout(xaxis_title="Śr. cena biletu (zł)", yaxis_title="Osoby")
            st.plotly_chart(fig, use_container_width=True)
            st.info(f"**Wynik:** {korelacja_opis(r, p)}")
        else:
            st.warning("Za mało danych do analizy korelacji cen biletów")

    with col4:
        # Cena biletu vs konwersja (wejścia)
        bk_valid = analiza[(analiza["cena_bilet"] > 0) & (analiza["konwersja"] > 0)]
        if len(bk_valid) > 3:
            r, p = stats.pearsonr(bk_valid["cena_bilet"], bk_valid["konwersja"])
            fig = px.scatter(bk_valid, x="cena_bilet", y="konwersja", hover_name="symbol",
                             color="miasto", trendline="ols",
                             title="Cena biletu vs konwersja wejść (%)",
                             color_discrete_sequence=COLORS)
            fig.update_layout(xaxis_title="Śr. cena biletu (zł)", yaxis_title="Konwersja %")
            st.plotly_chart(fig, use_container_width=True)
            st.info(f"**Wynik:** {korelacja_opis(r, p)}")

    st.divider()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 2. ANALIZA MIAST
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    st.subheader("2. Efektywność miast")

    miasto_analiza = analiza.groupby("miasto").agg(
        eventow=("id", "count"),
        sr_przychod_event=("przychod_total", "mean"),
        sr_m2=("m2", "mean"),
        sr_cena_m2=("cena_m2", "mean"),
        sr_bilety=("osoby_bilety", "mean"),
        sr_konwersja=("konwersja", "mean"),
        sr_cena_bilet=("cena_bilet", "mean"),
        total_przychod=("przychod_total", "sum"),
    ).reset_index()
    miasto_analiza = miasto_analiza[miasto_analiza["eventow"] >= 2].round(1)

    col1, col2 = st.columns(2)

    with col1:
        fig = px.scatter(miasto_analiza, x="sr_cena_m2", y="sr_przychod_event",
                         size="eventow", hover_name="miasto", text="miasto",
                         title="Miasta: śr. cena m² vs śr. przychód na event",
                         color_discrete_sequence=COLORS)
        fig.update_traces(textposition="top center")
        fig.update_layout(xaxis_title="Śr. cena za m² (zł)", yaxis_title="Śr. przychód na event (zł)")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        fig = px.scatter(miasto_analiza, x="sr_bilety", y="sr_konwersja",
                         size="eventow", hover_name="miasto", text="miasto",
                         title="Miasta: śr. bilety vs śr. konwersja wejść",
                         color_discrete_sequence=COLORS)
        fig.update_traces(textposition="top center")
        fig.update_layout(xaxis_title="Śr. bilety (osoby) na event", yaxis_title="Śr. konwersja %")
        st.plotly_chart(fig, use_container_width=True)

    # Ranking miast
    st.markdown("**Ranking miast — śr. przychód na event:**")
    miasto_rank = miasto_analiza.sort_values("sr_przychod_event", ascending=False)
    for i, row in enumerate(miasto_rank.itertuples(), 1):
        st.write(f"**{i}. {row.miasto}** — śr. przychód: {format_pln(row.sr_przychod_event)}, "
                 f"śr. cena m²: {format_pln(row.sr_cena_m2)}, "
                 f"śr. bilety: {row.sr_bilety:.0f} osób, "
                 f"konwersja: {row.sr_konwersja:.1f}%")

    st.divider()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 3. SEZONOWOŚĆ
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    st.subheader("3. Sezonowość")

    analiza["miesiac_ev"] = pd.to_datetime(analiza["data"], errors="coerce").dt.month
    sezon = analiza.groupby("miesiac_ev").agg(
        eventow=("id", "count"),
        sr_przychod=("przychod_total", "mean"),
        sr_bilety=("osoby_bilety", "mean"),
        sr_konwersja=("konwersja", "mean"),
    ).reset_index()
    miesiace = {1:"Sty",2:"Lut",3:"Mar",4:"Kwi",5:"Maj",6:"Cze",7:"Lip",8:"Sie",9:"Wrz",10:"Paź",11:"Lis",12:"Gru"}
    sezon["miesiac_nazwa"] = sezon["miesiac_ev"].map(miesiace)

    col1, col2 = st.columns(2)
    with col1:
        fig = px.bar(sezon, x="miesiac_nazwa", y="sr_przychod",
                     title="Śr. przychód na event wg miesiąca",
                     color_discrete_sequence=[COLORS[1]], text_auto=".2s")
        fig.update_layout(xaxis_title="Miesiąc", yaxis_title="zł")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        fig = px.bar(sezon, x="miesiac_nazwa", y="sr_bilety",
                     title="Śr. liczba osób (bilety) wg miesiąca",
                     color_discrete_sequence=[COLORS[0]], text_auto=".0f")
        fig.update_layout(xaxis_title="Miesiąc", yaxis_title="Osoby")
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 4. RETENCJA WYSTAWCÓW
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    st.subheader("4. Retencja wystawców")

    # Ile eventów per klient
    klient_hist = zam_active.groupby("idklienta").agg(
        ile_eventow=("idtargi", "nunique"),
        total_przychod=("kwota_netto_n", "sum"),
        total_m2=("ilem2_n", "sum"),
    ).reset_index()

    col1, col2 = st.columns(2)

    with col1:
        # Rozkład liczby eventów
        bins = [0, 1, 2, 3, 5, 10, 100]
        labels = ["1", "2", "3", "4-5", "6-10", "11+"]
        klient_hist["grupa"] = pd.cut(klient_hist["ile_eventow"], bins=bins, labels=labels)
        grupa_agg = klient_hist.groupby("grupa", observed=True).agg(
            klientow=("idklienta", "count"),
            sr_przychod=("total_przychod", "mean"),
        ).reset_index()
        fig = px.bar(grupa_agg, x="grupa", y="klientow",
                     title="Rozkład wystawców wg liczby eventów",
                     color_discrete_sequence=COLORS, text="klientow")
        fig.update_layout(xaxis_title="Liczba eventów", yaxis_title="Wystawców")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        fig = px.bar(grupa_agg, x="grupa", y="sr_przychod",
                     title="Śr. przychód od wystawcy wg lojalności",
                     color_discrete_sequence=[COLORS[3]], text_auto=".2s")
        fig.update_layout(xaxis_title="Liczba eventów", yaxis_title="Śr. przychód (zł)")
        st.plotly_chart(fig, use_container_width=True)

    # Procent przychodu od stałych klientów
    stali = klient_hist[klient_hist["ile_eventow"] >= 3]
    jednorazowi = klient_hist[klient_hist["ile_eventow"] == 1]
    total_rev = klient_hist["total_przychod"].sum()
    if total_rev > 0:
        pct_stali = stali["total_przychod"].sum() / total_rev * 100
        pct_jedno = jednorazowi["total_przychod"].sum() / total_rev * 100
        st.info(f"**Stali wystawcy (3+ eventów)** stanowią {len(stali)} z {len(klient_hist)} klientów "
                f"({len(stali)/len(klient_hist)*100:.1f}%), ale generują **{pct_stali:.1f}% przychodu** "
                f"({format_pln(stali['total_przychod'].sum())})")

    st.divider()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 5. BRANŻE — ANALIZA WARTOŚCI
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    st.subheader("5. Analiza branż")

    branze_map = dict(zip(branze["id"].astype(str), branze["nazwa"]))
    zam_br = zam_active.copy()
    zam_br["branza_nazwa"] = zam_br["branza"].astype(str).map(branze_map).fillna("Brak")

    br_analiza = zam_br.groupby("branza_nazwa").agg(
        zamowien=("id", "count"),
        przychod=("kwota_netto_n", "sum"),
        m2=("ilem2_n", "sum"),
        sr_m2=("ilem2_n", "mean"),
        sr_kwota=("kwota_netto_n", "mean"),
    ).reset_index()
    br_analiza["cena_m2"] = (br_analiza["przychod"] / br_analiza["m2"]).replace([np.inf, -np.inf], 0).fillna(0).round(0)
    br_analiza = br_analiza[br_analiza["zamowien"] >= 3].sort_values("przychod", ascending=False)

    col1, col2 = st.columns(2)

    with col1:
        fig = px.bar(br_analiza.sort_values("sr_kwota", ascending=True), x="sr_kwota", y="branza_nazwa",
                     orientation="h", title="Śr. wartość zamówienia per branża",
                     color_discrete_sequence=COLORS, text_auto=".0f")
        fig.update_layout(yaxis_title="", xaxis_title="Śr. zamówienie netto (zł)")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        fig = px.bar(br_analiza.sort_values("sr_m2", ascending=True), x="sr_m2", y="branza_nazwa",
                     orientation="h", title="Śr. powierzchnia stoiska per branża",
                     color_discrete_sequence=[COLORS[4]], text_auto=".1f")
        fig.update_layout(yaxis_title="", xaxis_title="Śr. m²")
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 6. TRENDY I DYNAMIKA
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    st.subheader("6. Trendy i dynamika rok do roku")

    rok_analiza = analiza.groupby("rok").agg(
        eventow=("id", "count"),
        total_przychod=("przychod_total", "sum"),
        sr_przychod_event=("przychod_total", "mean"),
        total_m2=("m2", "sum"),
        sr_cena_m2=("cena_m2", "mean"),
        total_bilety=("osoby_bilety", "sum"),
        sr_konwersja=("konwersja", "mean"),
    ).reset_index().sort_values("rok")
    rok_analiza = rok_analiza[rok_analiza["total_przychod"] > 0]

    # Dynamika YoY
    rok_analiza["zmiana_przychod"] = rok_analiza["total_przychod"].pct_change() * 100
    rok_analiza["zmiana_m2"] = rok_analiza["total_m2"].pct_change() * 100
    rok_analiza["zmiana_bilety"] = rok_analiza["total_bilety"].pct_change() * 100

    col1, col2 = st.columns(2)

    with col1:
        fig = go.Figure()
        fig.add_trace(go.Bar(x=rok_analiza["rok"], y=rok_analiza["zmiana_przychod"],
                             name="Przychód", marker_color=COLORS[1]))
        fig.add_trace(go.Bar(x=rok_analiza["rok"], y=rok_analiza["zmiana_m2"],
                             name="m²", marker_color=COLORS[4]))
        fig.update_layout(title="Dynamika rok do roku (%)",
                          barmode="group", xaxis_title="Rok", yaxis_title="Zmiana %",
                          xaxis_dtick=1)
        fig.add_hline(y=0, line_dash="dash", line_color="gray")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        fig = px.line(rok_analiza, x="rok", y="sr_przychod_event",
                      title="Śr. przychód na event — trend",
                      color_discrete_sequence=[COLORS[3]], markers=True)
        fig.update_xaxes(dtick=1)
        fig.update_layout(xaxis_title="Rok", yaxis_title="zł")
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 7. PODSUMOWANIE — WNIOSKI
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    st.subheader("7. Kluczowe wnioski")

    wnioski = []

    # Wniosek 1: Wpływ ceny m² — analiza praktyczna YoY
    if yoy_rows:
        yoy_df = pd.DataFrame(yoy_rows)
        wzrost = yoy_df[yoy_df["zmiana_ceny_m2_pct"] > 0]
        if len(wzrost) > 0:
            spadki = wzrost[wzrost["zmiana_przychodu_pct"] < 0]
            pct = len(spadki) / len(wzrost) * 100
            wnioski.append(
                f"Wzrost ceny za m² skutkuje spadkiem przychodu w **{pct:.0f}%** przypadków "
                f"({len(spadki)} z {len(wzrost)}). Dane YoY per miasto potwierdzają: "
                f"**podwyżki cen obniżają przychody i liczbę zamówień.**"
            )

    # Wniosek 2: Korelacja cena biletu vs frekwencja
    if len(b_valid) > 3:
        r_bil, p_bil = stats.pearsonr(b_valid["cena_bilet"], b_valid["osoby_bilety"])
        if r_bil < -0.3 and p_bil < 0.05:
            wnioski.append("Wyższa cena biletu **zmniejsza** frekwencję. "
                           f"Korelacja r={r_bil:.2f}. Cena biletu jest barierą wejścia.")
        elif r_bil > 0.3 and p_bil < 0.05:
            wnioski.append("Wyższa cena biletu **nie zmniejsza** frekwencji. "
                           "Odwiedzający są gotowi płacić więcej.")
        else:
            wnioski.append("Cena biletu **nie ma istotnego wpływu** na frekwencję. "
                           "Inne czynniki (miasto, termin) są ważniejsze.")

    # Wniosek 3: Najlepsze miasto
    if not miasto_analiza.empty:
        best_city = miasto_analiza.sort_values("sr_przychod_event", ascending=False).iloc[0]
        worst_city = miasto_analiza.sort_values("sr_przychod_event", ascending=True).iloc[0]
        wnioski.append(f"**Najlepsze miasto** pod względem śr. przychodu: **{best_city.miasto}** "
                       f"({format_pln(best_city.sr_przychod_event)}/event). "
                       f"Najsłabsze: **{worst_city.miasto}** ({format_pln(worst_city.sr_przychod_event)}/event).")

    # Wniosek 4: Sezonowość
    if not sezon.empty:
        best_month = sezon.sort_values("sr_przychod", ascending=False).iloc[0]
        wnioski.append(f"**Najlepszy miesiąc** na targi: **{best_month.miesiac_nazwa}** — "
                       f"śr. przychód {format_pln(best_month.sr_przychod)} na event.")

    # Wniosek 5: Retencja
    if total_rev > 0:
        wnioski.append(f"**Retencja jest kluczowa:** {len(stali)} stałych wystawców (3+ eventów) generuje "
                       f"**{pct_stali:.0f}%** całego przychodu. Inwestycja w utrzymanie klientów zwraca się.")

    # Wniosek 6: Branże
    if not br_analiza.empty:
        top_br = br_analiza.sort_values("sr_kwota", ascending=False).iloc[0]
        wnioski.append(f"**Najcenniejsza branża:** {top_br.branza_nazwa} — śr. zamówienie "
                       f"{format_pln(top_br.sr_kwota)}, śr. {top_br.sr_m2:.1f} m².")

    # Wniosek 7: Trend przychodu
    if len(rok_analiza) >= 3:
        last_3 = rok_analiza.tail(3)
        trend_r, _ = stats.pearsonr(range(len(last_3)), last_3["sr_przychod_event"])
        if trend_r > 0.5:
            wnioski.append("**Trend wzrostowy** — śr. przychód na event rośnie w ostatnich 3 latach.")
        elif trend_r < -0.5:
            wnioski.append("**Trend spadkowy** — śr. przychód na event spada w ostatnich 3 latach. "
                           "Warto zrewidować strategię cenową i ofertę.")

    # Wniosek 8: Konwersja
    sr_konw = analiza[analiza["konwersja"] > 0]["konwersja"].mean()
    if sr_konw > 0:
        wnioski.append(f"**Średnia konwersja** bilet → wejście: **{sr_konw:.1f}%**. "
                       + ("Wysoki wynik — odwiedzający przychodzą." if sr_konw > 70
                          else "Jest potencjał na zwiększenie frekwencji osób z biletami."))

    for i, w in enumerate(wnioski, 1):
        st.success(f"**{i}.** {w}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COCKPIT SPRZEDAŻOWY — operacjonalizacja strategii jesień 2026
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_cockpit:
    st.header("🎯 Cockpit sprzedażowy — jesień 2026")
    st.caption(
        "Operacyjny widok dowiezienia celów. Status liczony **względem historycznej krzywej sprzedaży** "
        "(gdzie powinniśmy być dziś), a nie surowego % celu. Pełna metodyka i plan: **STRATEGIA_SPRZEDAZY_2026.md**"
    )

    # ── Dane bazowe (niezależne od filtrów sidebara) ──
    ev_c = events.copy()
    ev_c["mies_n"] = ev_c["data_dt"].dt.month
    ev_c["rok_n"] = ev_c["data_dt"].dt.year
    ev26_c = ev_c[(ev_c["rok_n"] == 2026) & (ev_c["mies_n"].isin([10, 11, 12]))].copy()

    zam_c = zamowienia[zamowienia["status"].astype(str) == "2"].copy()
    zam_c["idtargi_n"] = pd.to_numeric(zam_c["idtargi"], errors="coerce")
    zam_c = zam_c.drop(columns=[c for c in ["miasto", "data_targi"] if c in zam_c.columns])
    zam_c = zam_c.merge(
        ev_c[["id", "miasto", "data_dt", "mies_n", "rok_n"]].rename(columns={"id": "ev_id_join"}),
        left_on="idtargi_n", right_on="ev_id_join", how="left",
    )

    if ev26_c.empty:
        st.info("Brak eventów jesiennych 2026 w bazie — cockpit uruchomi się, gdy pojawią się edycje X–XII 2026.")
    else:
        # ── Historyczna krzywa sprzedaży (jesień 2022–2025, wszystkie miasta docelowe) ──
        zam_aut = zam_c[zam_c["mies_n"].isin([10, 11, 12])].copy()
        zam_aut["dni_przed"] = (zam_aut["data_dt"] - zam_aut["data_utw_dt"]).dt.days
        zam_aut["mies_przed"] = (zam_aut["dni_przed"] / 30.44).round(0)
        # Pełna historia jesienna — definiuje przynależność „był wystawcą" (pula reaktywacji)
        pool_hist = zam_aut[(zam_aut["rok_n"] >= 2022) & (zam_aut["rok_n"] < 2026)]
        # Wersja odfiltrowana do KRZYWEJ czasowej (potrzebuje sensownego mies_przed)
        hist_aut = pool_hist[(pool_hist["mies_przed"].notna()) & (pool_hist["mies_przed"] >= 0)]
        curve = hist_aut.groupby("mies_przed")["id"].count()
        curve_pct = (curve / curve.sum()).to_dict() if curve.sum() > 0 else {}

        def pct_juz_dla(mies_do):
            """Jaki % zamówień historycznie już wpłynął, gdy jesteśmy `mies_do` mies. przed eventem."""
            return sum(v for k, v in curve_pct.items() if k > mies_do)

        now = pd.Timestamp.now()
        rows = []
        for _, e in ev26_c.iterrows():
            eid = int(e["id"]); miasto = e["miasto"]; edate = e["data_dt"]
            akt = zam_c[zam_c["idtargi_n"] == eid]
            aktualnie = len(akt)
            przychod = akt["kwota_netto_n"].sum()
            cel = CELE_JESIEN_2026.get(miasto, 0)

            dni_do = (edate - now).days
            mies_do = max(0, dni_do / 30.44)
            pct_juz = pct_juz_dla(mies_do)
            oczek = cel * pct_juz

            # Status względem krzywej
            if cel <= 0:
                status, sev = "— brak celu", 5
            elif oczek < 1.5:
                status, sev = "⏳ start sezonu", 3
            else:
                ratio = aktualnie / oczek if oczek > 0 else 0
                if ratio >= 1.0:
                    status, sev = "🟢 powyżej krzywej", 0
                elif ratio >= 0.7:
                    status, sev = "🟡 lekko pod krzywą", 1
                else:
                    status, sev = "🔴 pod krzywą — eskalujmy", 2

            # Pula reaktywacji: byli wystawcy jesienni tego miasta bez zam. na 2026
            past = pool_hist[pool_hist["miasto"] == miasto]
            past_clients = set(past["idklienta"].dropna())
            cur_clients = set(akt["idklienta"].dropna())
            pula_reak = len(past_clients - cur_clients)

            weeks = max(1, dni_do / 7)
            brakuje = max(0, cel - aktualnie)
            tempo_tydz = brakuje / weeks

            rows.append({
                "Event": e["symbol"], "Miasto": miasto,
                "Data": edate.strftime("%Y-%m-%d"), "Dni do": dni_do,
                "Aktualnie": aktualnie, "Cel": cel,
                "Oczek. wg krzywej": round(oczek),
                "Status": status, "_sev": sev,
                "Brakuje": brakuje,
                "Tempo/tydz": round(tempo_tydz, 1),
                "Pula reaktywacji": pula_reak,
                "Przychód": przychod,
                "_dni": dni_do,
            })

        cdf = pd.DataFrame(rows)

        # ── KPI nagłówek (tylko miasta z celem — spójnie z celem łącznym) ──
        cel_cities = cdf[cdf["Cel"] > 0]
        tot_akt = int(cel_cities["Aktualnie"].sum())
        tot_cel = int(cel_cities["Cel"].sum())
        tot_brak = int(cel_cities["Brakuje"].sum())
        n_pod = int((cdf["_sev"] == 2).sum())
        tot_reak = int(cel_cities["Pula reaktywacji"].sum())

        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric(f"Zamówienia ({len(cel_cities)} miast)", tot_akt)
        k2.metric("Cel łączny", tot_cel)
        k3.metric("Brakuje do celu", tot_brak, delta=f"-{tot_brak}", delta_color="inverse")
        k4.metric("Eventy pod krzywą", n_pod, delta="eskalujmy" if n_pod else "ok",
                  delta_color="inverse" if n_pod else "normal")
        k5.metric("Pula reaktywacji", tot_reak, help="Byli wystawcy jesienni bez zamówienia na 2026")

        st.divider()

        # ── Tabela statusu per event ──
        st.subheader("Status per event — gdzie jesteśmy vs gdzie powinniśmy być")
        cdf_show = cdf.sort_values(["_sev", "_dni"], ascending=[False, True]).drop(columns=["_sev", "_dni"])

        def koloruj_status(val):
            if "🔴" in str(val):
                return "background-color: #f8d7da"
            if "🟡" in str(val):
                return "background-color: #fff3cd"
            if "🟢" in str(val):
                return "background-color: #d4edda"
            return ""

        st.dataframe(
            cdf_show.style
                .format({"Przychód": "{:,.0f} zł", "Tempo/tydz": "{:.1f}"})
                .map(koloruj_status, subset=["Status"]),
            use_container_width=True, hide_index=True,
        )
        with st.expander("Jak czytać status?"):
            st.markdown("""
- **Oczek. wg krzywej** — ile zamówień *powinniśmy* już mieć dziś, gdyby ten event szedł dokładnie wg historycznego tempa (krzywa jesień 2022–2025).
- **Status** liczony jako `Aktualnie / Oczek. wg krzywej`:
  - 🟢 **powyżej krzywej** (≥100%) — idzie lepiej niż historycznie
  - 🟡 **lekko pod** (70–99%) — obserwujmy
  - 🔴 **pod krzywą** (<70%) — eskalujmy: dodajmy turę reaktywacji + kampanię
  - ⏳ **start sezonu** — za wcześnie na wiarygodną ocenę (event daleko, historycznie prawie nic jeszcze nie wpływało)
- **Tempo/tydz** — ile zamówień/tydzień musimy pozyskać do dnia eventu, żeby dobić cel.
- **Pula reaktywacji** — ilu byłych wystawców jesiennych tego miasta jeszcze nie zamówiło na 2026 (gotowa ciepła lista).
""")

        # ── Wykres: aktualnie vs oczekiwane vs cel ──
        st.subheader("Aktualnie vs oczekiwane wg krzywej vs cel")
        chart_df = cdf.sort_values("_dni")[["Event", "Aktualnie", "Oczek. wg krzywej", "Cel"]].melt(
            id_vars="Event", var_name="Miara", value_name="Zamówień")
        fig = px.bar(chart_df, x="Event", y="Zamówień", color="Miara", barmode="group",
                     color_discrete_map={
                         "Aktualnie": COLORS[2],
                         "Oczek. wg krzywej": COLORS[0],
                         "Cel": COLORS[1],
                     }, text="Zamówień")
        fig.update_traces(textposition="outside", textfont_size=10)
        fig.update_layout(legend_title="", xaxis_title="")
        st.plotly_chart(fig, use_container_width=True)

        # ── Lista priorytetowa działań ──
        st.subheader("Priorytety na ten tydzień")
        prio = cdf.sort_values(["_sev", "_dni"], ascending=[False, True]).to_dict("records")
        ramki = {2: ("🔴", st.error), 1: ("🟡", st.warning), 3: ("⏳", st.info)}
        for r in prio:
            ikona, ramka = ramki.get(r["_sev"], ("🟢", st.success))
            ramka(
                f"**{ikona} {r['Miasto']}** ({r['Data']}, za {r['_dni']} dni) — "
                f"{r['Aktualnie']}/{r['Cel']} zam. (oczek. dziś ~{r['Oczek. wg krzywej']}). "
                f"Brakuje **{r['Brakuje']}**, tempo **{r['Tempo/tydz']}/tydz**. "
                f"Ciepła pula reaktywacji: **{r['Pula reaktywacji']}** wystawców."
            )

        st.caption(
            "Pełny plan działań (reaktywacja VIP-ów, mailing do byłych wystawców, early-bird, polityka cenowa) "
            "— w dokumencie **STRATEGIA_SPRZEDAZY_2026.md**."
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STRATEGIA — operacyjna wersja STRATEGIA_SPRZEDAZY_2026.md
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_strat:
    st.header("📋 Strategia sprzedaży stoisk — jesień 2026")
    st.caption(
        "Operacyjna wersja dokumentu **STRATEGIA_SPRZEDAZY_2026.md** — z **listami do działania na żywo z bazy**. "
        "Status i tempo per event: zakładka **Cockpit sprzedażowy**."
    )

    # ── Dane bazowe (niezależne od filtrów sidebara) ──
    ev_s = events.copy()
    ev_s["mies_s"] = ev_s["data_dt"].dt.month
    ev_s["rok_s"] = ev_s["data_dt"].dt.year

    zam_s = zamowienia[zamowienia["status"].astype(str) == "2"].copy()
    zam_s["idtargi_n"] = pd.to_numeric(zam_s["idtargi"], errors="coerce")
    zam_s = zam_s.drop(columns=[c for c in ["miasto", "data_targi"] if c in zam_s.columns])
    zam_s = zam_s.merge(
        ev_s[["id", "miasto", "data_dt", "mies_s", "rok_s"]].rename(columns={"id": "ev_join"}),
        left_on="idtargi_n", right_on="ev_join", how="left",
    )

    # Widok do analiz klienckich — bez pustych idklienta (czyste listy bez „nan")
    zam_cli = zam_s[zam_s["idklienta"].notna()].copy()
    zam_cli["idklienta_s"] = zam_cli["idklienta"].astype(str)
    zam_cli = zam_cli[~zam_cli["idklienta_s"].str.lower().isin(["nan", "none", ""])]

    kli = klienci.copy()
    kli["id_s"] = kli["id"].astype(str)
    kli_info = kli[["id_s", "nazwa", "email", "miasto"]].rename(columns={"miasto": "miasto_klienta"})

    cur26_ids = set(zam_cli[zam_cli["rok_s"] == 2026]["idklienta_s"])
    kev = zam_cli.groupby("idklienta_s").agg(
        ile_edycji=("idtargi_n", "nunique"),
        przychod_zycia=("kwota_netto_n", "sum"),
    ).reset_index()

    zam_aut_s = zam_cli[zam_cli["mies_s"].isin([10, 11, 12])]
    hist_aut_s = zam_aut_s[(zam_aut_s["rok_s"] >= 2022) & (zam_aut_s["rok_s"] < 2026)]

    CELE = CELE_JESIEN_2026

    # Pule
    vip_pool = kev[(kev["ile_edycji"] >= 6) & (~kev["idklienta_s"].isin(cur26_ids))]
    stali_pool = kev[(kev["ile_edycji"] >= 3) & (~kev["idklienta_s"].isin(cur26_ids))]

    # Leady = konta BEZ stoiska, świeże (ostatnie 18 mies.), z flagą miasta docelowego
    LEAD_OKNO_MIES = 18
    cele_cols = [CITY_COL_MAP[c] for c in CELE if c in CITY_COL_MAP]
    leady_baza = klienci[
        (~klienci["ma_stoisko"]) & klienci["time_utw_dt"].notna() &
        (klienci["mies_od_rej"] <= LEAD_OKNO_MIES)
    ].copy()
    flag_target = pd.Series(False, index=leady_baza.index)
    for _c in cele_cols:
        if _c in leady_baza.columns:
            flag_target = flag_target | (pd.to_numeric(leady_baza[_c], errors="coerce").fillna(0) > 0)
    leady_target = leady_baza[flag_target]
    n_leady = len(leady_target)
    n_warm = int((leady_target["mies_od_rej"] <= 3).sum())  # ciepłe okno ≤3 mies.

    reak_per_city = {}
    for miasto in CELE:
        past_ids = set(hist_aut_s[hist_aut_s["miasto"] == miasto]["idklienta_s"])
        cur_ids = set(zam_aut_s[(zam_aut_s["miasto"] == miasto) & (zam_aut_s["rok_s"] == 2026)]["idklienta_s"])
        reak_per_city[miasto] = past_ids - cur_ids
    reak_total = sum(len(v) for v in reak_per_city.values())

    ev26_target_ids = ev_s[
        (ev_s["rok_s"] == 2026) & (ev_s["mies_s"].isin([10, 11, 12])) & (ev_s["miasto"].isin(CELE))
    ]["id"].astype(int).tolist()
    akt_jes = len(zam_s[zam_s["idtargi_n"].isin(ev26_target_ids)])
    cel_total = sum(CELE.values())

    # ── 1. Streszczenie wykonawcze (na żywo) ──
    st.subheader("Streszczenie wykonawcze")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric(f"Zamówienia ({len(CELE)} miast)", akt_jes)
    m2.metric("Cel łączny", cel_total)
    m3.metric("Brakuje", max(0, cel_total - akt_jes), delta=f"-{max(0, cel_total - akt_jes)}", delta_color="inverse")
    m4.metric("Pula reaktywacji", reak_total, help="Byli wystawcy jesienni bez zamówienia na 2026")
    m5.metric("Leady (18 mies.)", n_leady, help="Konta bez stoiska, zarejestrowane w ostatnich 18 mies., z flagą miasta docelowego")
    st.info(
        f"Brakuje **{max(0, cel_total - akt_jes)} zamówień** do celu. Domykamy je z ciepłej bazy, nie z cold-callingu: "
        f"**{reak_total} byłych wystawców** do reaktywacji (w tym **{len(vip_pool)} VIP-ów 6+** i **{len(stali_pool)} stałych 3+** "
        f"bez zam. 2026) + **{n_leady} świeżych leadów** (konta bez stoiska, 18 mies.) w miastach docelowych."
    )

    # ── 2. Trzy dźwignie ──
    st.subheader("Trzy dźwignie (wg ROI)")
    d1, d2, d3 = st.columns(3)
    with d1:
        st.markdown(
            f"#### A. Reaktywacja\n"
            f"**{reak_total}** byłych wystawców + **{len(vip_pool)}** VIP-ów.\n\n"
            f"Najtańsze i najpewniejsze źródło. Stały wystawca wart 4–15× więcej niż jednorazowy. "
            f"VIP-y = **telefon imienny**, nie mailing. Lista niżej ⬇️"
        )
    with d2:
        st.markdown(
            f"#### B. Konwersja leadów\n"
            f"**{n_leady}** świeżych leadów, w tym **{n_warm}** w 🔥 ciepłym oknie (≤3 mies.).\n\n"
            f"**Reguła 72h:** świeży lead dotykamy w 3 dni — 55% kupuje w 1. miesiącu. "
            f"Sekwencja: oferta → case study → social proof → early-bird. Pełny pipeline: zakładka **Leady**."
        )
    with d3:
        st.markdown(
            "#### C. Dyscyplina cenowa\n"
            "**Nie podnośmy ceny m²** w miastach z luką.\n\n"
            "Dane: podwyżki obniżają wolumen. Grajmy **early-bird** (zamrożona cena do terminu X) "
            "i **pakietami**, nie wyższym cennikiem."
        )

    st.divider()

    # ── 3. Listy do działania (eksport) ──
    st.subheader("🎯 Listy do działania")
    st.caption("Gotowe, ciepłe listy kontaktów. Każdą można pobrać jako CSV (Excel-friendly) i wrzucić do mailingu/CRM.")

    lt1, lt2, lt3 = st.tabs([
        f"⭐ VIP-y do reaktywacji ({len(vip_pool)})",
        "🔁 Pula reaktywacji per miasto",
        f"📨 Leady — konta bez stoiska ({n_leady})",
    ])

    with lt1:
        st.markdown("**Wystawcy 6+ edycji bez zamówienia na 2026** — najwyższy priorytet, kontakt osobisty (telefon).")
        vip_list = vip_pool.merge(kli_info, left_on="idklienta_s", right_on="id_s", how="left")
        vip_list = vip_list[["nazwa", "email", "miasto_klienta", "ile_edycji", "przychod_zycia"]] \
            .sort_values("przychod_zycia", ascending=False)
        vip_list.columns = ["Wystawca", "E-mail", "Miasto", "Edycji łącznie", "Wartość życiowa (zł)"]
        st.dataframe(
            vip_list.style.format({"Wartość życiowa (zł)": "{:,.0f}"}),
            use_container_width=True, hide_index=True,
        )
        st.download_button(
            "⬇️ Pobierz listę VIP (CSV)",
            vip_list.to_csv(index=False).encode("utf-8-sig"),
            "reaktywacja_VIP_jesien2026.csv", "text/csv", key="dl_vip",
        )

    with lt2:
        sel_city = st.selectbox("Miasto", list(CELE.keys()), key="reak_city")
        pool_ids = reak_per_city[sel_city]
        past_city = hist_aut_s[(hist_aut_s["miasto"] == sel_city) & (hist_aut_s["idklienta_s"].isin(pool_ids))]
        if past_city.empty:
            st.info("Brak puli reaktywacji dla tego miasta.")
        else:
            pool = past_city.groupby("idklienta_s").agg(
                edycje_jesien=("idtargi_n", "nunique"),
                ostatni_rok=("rok_s", "max"),
                hist_wartosc=("kwota_netto_n", "sum"),
            ).reset_index()
            pool = pool.merge(kli_info, left_on="idklienta_s", right_on="id_s", how="left")
            max_rok = pool["ostatni_rok"].max()
            pool["priorytet"] = np.where(pool["ostatni_rok"] == max_rok, "🔥 z ost. edycji", "")
            pool = pool.sort_values(["ostatni_rok", "hist_wartosc"], ascending=[False, False])
            pool_show = pool[["nazwa", "email", "edycje_jesien", "ostatni_rok", "hist_wartosc", "priorytet"]].copy()
            pool_show.columns = ["Wystawca", "E-mail", "Edycji jesień", "Ostatnia edycja", "Hist. wartość (zł)", "Priorytet"]
            swiezi = int((pool["ostatni_rok"] == max_rok).sum())
            st.caption(f"**{len(pool)}** wystawców do reaktywacji w mieście {sel_city}, "
                       f"w tym **{swiezi}** z ostatniej edycji (najcieplejsi). "
                       f"Potencjał: ~{pool['hist_wartosc'].sum() / 1000:.0f}k zł historycznej wartości.")
            st.dataframe(
                pool_show.style.format({"Hist. wartość (zł)": "{:,.0f}", "Ostatnia edycja": "{:.0f}"}),
                use_container_width=True, hide_index=True,
            )
            st.download_button(
                f"⬇️ Pobierz pulę reaktywacji — {sel_city} (CSV)",
                pool_show.to_csv(index=False).encode("utf-8-sig"),
                f"reaktywacja_{sel_city}_jesien2026.csv", "text/csv", key="dl_reak",
            )

    with lt3:
        st.markdown("**Konta zarejestrowane bez stoiska** (ostatnie 18 mies., miasta docelowe). "
                    "Pełny pipeline z suwakiem świeżości i filtrem miasta — zakładka **💼 Leady / Pipeline**.")
        branze_map_s = dict(zip(branze["id"].astype(str), branze["nazwa"]))
        leads_list = leady_target.copy()
        leads_list["Branża"] = leads_list["branza"].astype(str).map(branze_map_s).fillna("—")
        leads_list["Zarejestrowano"] = leads_list["time_utw_dt"].dt.strftime("%Y-%m-%d")
        leads_list = leads_list.sort_values("time_utw_dt", ascending=False)
        leads_list = leads_list[["nazwa", "email", "telefon", "Branża", "miasto", "Zarejestrowano"]]
        leads_list.columns = ["Nazwa", "E-mail", "Telefon", "Branża", "Miasto (konto)", "Zarejestrowano"]
        st.dataframe(leads_list, use_container_width=True, hide_index=True, height=300)
        st.download_button(
            "⬇️ Pobierz leady — konta bez stoiska (CSV)",
            leads_list.to_csv(index=False).encode("utf-8-sig"),
            "leady_konta_bez_stoiska_jesien2026.csv", "text/csv", key="dl_leads",
        )

    st.divider()

    # ── 4. Plan w czasie ──
    st.subheader("🗓️ Plan w czasie (zsynchronizowany z krzywą sprzedaży)")
    plan_czas = pd.DataFrame([
        ["Czerwiec–lipiec (teraz)", "przed falą (~14–21%)", "Reaktywujmy VIP-ów + „z ost. edycji”. Uruchommy early-bird (deadline 31.08). Wyczyśćmy bazę leadów."],
        ["Sierpień", "start fali (~37%)", "Odpalmy pełną kampanię leadową. Zróbmy drugą turę reaktywacji. Domknijmy early-bird."],
        ["Wrzesień", "PIK (~65%)", "Wrzućmy maks. intensywność. Dzwońmy do niezdecydowanych. Gliwice (4.10) wchodzi w finał."],
        ["Październik", "finał (~87%)", "Grajmy „last call”, ostatnie miejsca. Gdańsk/Kraków/Rzeszów/Białystok/Poznań finiszują."],
        ["Listopad", "miesiąc eventu (~13%)", "Dobijajmy zamówienia last-minute, pełna sala."],
    ], columns=["Okres", "Faza krzywej", "Działania"])
    st.dataframe(plan_czas, use_container_width=True, hide_index=True)
    st.caption("Reguła: jeśli na 3 mies. przed eventem mamy < 37% celu — jesteśmy pod krzywą, eskalujmy (patrz Cockpit).")

    st.divider()

    # ── 5. Polityka cenowa (na żywo) ──
    st.subheader("💰 Polityka cenowa")
    st.markdown(
        "Dane jednoznacznie: **wzrost ceny m² → spadek wolumenu i przychodu.** Dla celów wolumenowych:\n"
        "- **Zamroźmy cenę bazową m²** (poziom 2025) w miastach z luką (Rzeszów, Kraków, Gliwice).\n"
        "- Grajmy **early-bird** (niższa cena do terminu X), nie wyższym cennikiem — pilność bez sygnału drożyzny.\n"
        "- **Dajmy cenę lojalnościową** dla 3+ edycji = argument reaktywacji. **Oferujmy pakiety** zamiast rabatu wprost.\n"
    )
    g = zam_s[zam_s["rok_s"].between(2022, 2026)].groupby(["miasto", "rok_s"]).agg(
        k=("kwota_netto_n", "sum"), mkw=("ilem2_n", "sum")).reset_index()
    g["cena_m2"] = (g["k"] / g["mkw"]).replace([np.inf, -np.inf], 0).fillna(0).round(0)
    pokaz_miasta = list(CELE.keys()) + ["Warszawa"]
    price_piv = g[g["miasto"].isin(pokaz_miasta)].pivot(index="miasto", columns="rok_s", values="cena_m2")
    st.markdown("**Średnia cena za m² (zł) per miasto i rok** — widać tempo podwyżek:")
    st.dataframe(price_piv.style.format("{:.0f}", na_rep="—").background_gradient(cmap="Reds", axis=None),
                 use_container_width=True)
    st.caption("Uwaga: Warszawa — najwyższa cena m² i równoległy spadek wolumenu (prawdopodobnie przepalona cenowo).")

    st.divider()

    # ── 6. Ryzyka ──
    st.subheader("⚠️ Ryzyka i rekomendacje")
    st.warning(
        "1. **Cele Rzeszowa (×3,0) i Krakowa (×2,4 ost. edycji) mogą być nierealne** — rozważmy osobny cel *committed* "
        "(np. Rzeszów 20, Kraków 32) do liczenia budżetu kampanii.\n\n"
        "2. **Definicja leada poprawiona** — starą tabelę `leads` (2017–2022) usunęliśmy jako martwą; lead = konto bez stoiska (na żywo). "
        "Liczmy tylko świeże (≤18 mies.) i monitorujmy je w zakładce Leady.\n\n"
        "3. **Słabe tagowanie branż** (większość zamówień „Brak”) — blokuje targetowany przekaz. Wymuśmy tag przy rejestracji.\n\n"
        "4. **Warszawa w trendzie spadkowym** mimo najwyższej ceny — zróbmy osobną diagnozę."
    )

    # ── 7. Quick wins ──
    st.subheader("✅ Quick wins — najbliższe 2 tygodnie")
    st.markdown(
        f"1. **Pobierzmy 3 listy** (przyciski wyżej): {len(vip_pool)} VIP-ów, {reak_total} pula reaktywacji, {n_leady} leadów.\n"
        f"2. **Zadzwońmy do {len(vip_pool)} VIP-ów** — imiennie, gwarancja ceny i miejsca. Najwyższy ROI.\n"
        "3. **Wyślijmy mailing reaktywacyjny** do „z ostatniej edycji” (Gdańsk, Poznań najpierw) z deadline early-bird 31.08.\n"
        "4. **Ustawmy early-bird** (zamrożona cena 2025 do 31.08) w miastach z luką.\n"
        "5. **Wdróżmy regułę 72h** — każdy nowy lead (konto bez stoiska) dotykamy w 3 dni; ciepłe okno to pierwsze 3 mies.\n"
        "6. **Przeglądajmy Cockpit co tydzień** (poniedziałek) — stały rytuał."
    )

    # ── Pełny dokument ──
    with st.expander("📄 Pełny dokument strategii (STRATEGIA_SPRZEDAZY_2026.md)"):
        doc_path = Path(__file__).parent / "STRATEGIA_SPRZEDAZY_2026.md"
        try:
            st.markdown(doc_path.read_text(encoding="utf-8"))
        except Exception as e:
            st.warning(f"Nie udało się wczytać dokumentu: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LEADY / PIPELINE — konta bez stoiska (realna definicja leada)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_leady:
    st.header("💼 Leady / Pipeline")
    st.caption(
        "**Lead = zarejestrowane konto w systemie BEZ stoiska** (konto klienta bez aktywnego zamówienia). "
        "Dane na żywo — baza rośnie codziennie. Atrybucja miasta wg flag rejestracji `t_<miasto>`. "
        "_(Stara tabela `leads` 2017–2022 została usunięta jako martwa, myląca dana.)_"
    )

    n_kont = int(klienci["time_utw_dt"].notna().sum())
    n_wyst = int((klienci["ma_stoisko"] & klienci["time_utw_dt"].notna()).sum())
    leady_all = klienci[(~klienci["ma_stoisko"]) & klienci["time_utw_dt"].notna()].copy()
    n_lead = len(leady_all)

    # ── Suwak świeżości ──
    okno_opcje = {
        "Ostatnie 3 mies.": 3, "Ostatnie 6 mies.": 6, "Ostatnie 12 mies.": 12,
        "Ostatnie 18 mies.": 18, "Ostatnie 24 mies.": 24, "Wszystkie": None,
    }
    okno_label = st.select_slider(
        "Okno rejestracji (świeżość leada)", options=list(okno_opcje.keys()),
        value="Ostatnie 18 mies.",
        help="Konta bez stoiska sprzed lat to zwykle martwy potencjał. Domyślnie pokazujemy świeże (ostatnie 18 mies.).",
    )
    okno = okno_opcje[okno_label]
    leady_f = leady_all if okno is None else leady_all[leady_all["mies_od_rej"] <= okno]

    # ── KPI ──
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Konta łącznie", f"{n_kont:,}".replace(",", " "))
    k2.metric("Wystawcy (ze stoiskiem)", f"{n_wyst:,}".replace(",", " "))
    k3.metric("Leady (bez stoiska)", f"{n_lead:,}".replace(",", " "))
    k4.metric("Leady w oknie", f"{len(leady_f):,}".replace(",", " "))

    konw = n_wyst / n_kont * 100 if n_kont else 0
    st.info(
        f"Konwersja **konto → stoisko: {konw:.1f}%** ({n_wyst} z {n_kont}). "
        f"Pozostałe **{n_lead}** kont to leady. W wybranym oknie (**{okno_label.lower()}**) "
        f"do konwersji jest **{len(leady_f)}** świeżych leadów."
    )

    # ── 🔥 Ciepłe okno — priorytet sprzedażowy (niezależne od suwaka) ──
    leady_warm = leady_all[leady_all["mies_od_rej"] <= 3]
    n_warm = len(leady_warm)
    _cele_cols = [CITY_COL_MAP[c] for c in CELE_JESIEN_2026 if c in CITY_COL_MAP]
    _warm_mask = pd.Series(False, index=leady_warm.index)
    for _c in _cele_cols:
        if _c in leady_warm.columns:
            _warm_mask = _warm_mask | (pd.to_numeric(leady_warm[_c], errors="coerce").fillna(0) > 0)
    n_warm_target = int(_warm_mask.sum())
    st.success(
        f"🔥 **Ciepłe okno — priorytet:** **{n_warm}** leadów zarejestrowanych w ostatnich **3 miesiącach** "
        f"({n_warm_target} w miastach docelowych). To moment najwyższej konwersji — **55% kupuje w 1. miesiącu**. "
        f"**Reguła 72h:** każdy nowy lead dotykamy w ciągu 3 dni i dociskamy w pierwsze 3 mies. — potem stygnie."
    )

    st.divider()

    # ── Lejek i trend ──
    col_f, col_t = st.columns(2)
    with col_f:
        funnel = pd.DataFrame({
            "Etap": ["Konta (rejestracje)", "Leady (bez stoiska)", "Wystawcy (stoisko)"],
            "Liczba": [n_kont, n_lead, n_wyst],
        })
        fig = px.funnel(funnel, x="Liczba", y="Etap", title="Lejek: rejestracja → stoisko",
                        color_discrete_sequence=[COLORS[2]])
        st.plotly_chart(fig, use_container_width=True)

    with col_t:
        trend = leady_all.copy()
        trend["mies"] = trend["time_utw_dt"].dt.to_period("M").astype(str)
        trend_m = trend[trend["rok_rej"] >= 2022].groupby("mies").size().reset_index(name="leady")
        trend_m = trend_m.sort_values("mies").tail(30)
        fig = px.bar(trend_m, x="mies", y="leady", title="Nowe leady miesięcznie (od 2022)",
                     color_discrete_sequence=[COLORS[0]])
        fig.update_layout(xaxis_title="", yaxis_title="Nowe leady")
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ── Konwersja konto → stoisko (kohortowo + czas) ──
    st.subheader("📈 Konwersja konto → stoisko")

    # Pierwszy zakup per klient
    zam_buy = zamowienia[zamowienia["status"].astype(str) == "2"].copy()
    zam_buy["id_s"] = zam_buy["idklienta"].astype(str)
    first_buy = zam_buy.groupby("id_s")["data_utw_dt"].min()
    klc = klienci[klienci["rok_rej"] >= 2016].copy()
    klc["id_s"] = klc["id"].astype(str)
    klc["pierwszy_zakup"] = klc["id_s"].map(first_buy)
    klc["mies_do_zakupu"] = (klc["pierwszy_zakup"] - klc["time_utw_dt"]).dt.days / 30.44
    klc["kup_12m"] = klc["ma_stoisko"] & (klc["mies_do_zakupu"] <= 12) & (klc["mies_do_zakupu"] >= -1)

    konw_ogol = klc["ma_stoisko"].mean() * 100 if len(klc) else 0
    dojrz = klc[klc["rok_rej"].between(2022, 2024)]
    konw_12_dojrz = dojrz["kup_12m"].sum() / len(dojrz) * 100 if len(dojrz) else 0
    kupujacy = klc[klc["ma_stoisko"] & klc["mies_do_zakupu"].notna()]
    mediana_mies = kupujacy["mies_do_zakupu"].median() if len(kupujacy) else 0
    pct_1mc = (kupujacy["mies_do_zakupu"] <= 1).mean() * 100 if len(kupujacy) else 0

    kc1, kc2, kc3, kc4 = st.columns(4)
    kc1.metric("Konwersja ogółem", f"{konw_ogol:.1f}%", help="Wszystkie konta 2016+ — zaniżone przez świeże, niedojrzałe rejestracje")
    kc2.metric("Konwersja w 12 mies.", f"{konw_12_dojrz:.1f}%", help="Dojrzałe kohorty 2022–2024 — standaryzowana miara apples-to-apples")
    kc3.metric("Mediana czasu do zakupu", f"{mediana_mies:.1f} mies")
    kc4.metric("Zakupy w 1. miesiącu", f"{pct_1mc:.0f}%", help="Tyle % kupujących bierze stoisko w ciągu miesiąca od rejestracji")

    st.caption(
        "⚠️ **Jak czytać:** surowa konwersja ogółem jest zaniżona, bo świeże konta nie zdążyły jeszcze kupić. "
        "Uczciwa miara to **konwersja w 12 mies. per kohorta**. Uwaga: konwersja jest **dwumodalna** — większość kupuje "
        "od razu (≤1 mies.), reszta zostaje leadem; ciepłe okno to pierwsze ~3 miesiące od rejestracji."
    )

    # Kohortowa konwersja wg roku rejestracji
    coh = klc.groupby("rok_rej").agg(
        konta=("id_s", "count"), kupili=("ma_stoisko", "sum"), kup12=("kup_12m", "sum"),
    ).reset_index()
    coh["konw_ever"] = (coh["kupili"] / coh["konta"] * 100).round(1)
    coh["konw_12m"] = (coh["kup12"] / coh["konta"] * 100).round(1)

    fig = go.Figure()
    fig.add_bar(x=coh["rok_rej"], y=coh["konta"], name="Konta (rejestracje)", marker_color=COLORS[7])
    fig.add_bar(x=coh["rok_rej"], y=coh["kupili"], name="Kupili stoisko", marker_color=COLORS[2])
    fig.add_trace(go.Scatter(x=coh["rok_rej"], y=coh["konw_ever"], name="Konwersja % (kiedykolwiek)",
                             yaxis="y2", mode="lines+markers+text", text=coh["konw_ever"],
                             texttemplate="%{text:.0f}%", textposition="top center",
                             line=dict(color=COLORS[1], width=3)))
    fig.add_trace(go.Scatter(x=coh["rok_rej"], y=coh["konw_12m"], name="Konwersja % (w 12 mies.)",
                             yaxis="y2", mode="lines+markers", line=dict(color=COLORS[3], width=2, dash="dash")))
    fig.update_layout(
        title="Konwersja kohortowa — wg roku rejestracji konta",
        barmode="group", xaxis=dict(title="Rok rejestracji", dtick=1),
        yaxis=dict(title="Liczba kont"),
        yaxis2=dict(title="Konwersja %", overlaying="y", side="right", range=[0, max(35, coh["konw_ever"].max() * 1.2)]),
        legend=dict(orientation="h", y=-0.2),
    )
    st.plotly_chart(fig, use_container_width=True)

    col_cz, col_cm = st.columns(2)
    with col_cz:
        m = kupujacy["mies_do_zakupu"]
        bucket_def = [(-1, 1, "0–1 mies"), (1, 3, "1–3 mies"), (3, 6, "3–6 mies"),
                      (6, 12, "6–12 mies"), (12, 24, "12–24 mies"), (24, 9999, "24+ mies")]
        bdf = pd.DataFrame([{"Okno": lab, "Zakupów": int(((m > lo) & (m <= hi)).sum())}
                            for lo, hi, lab in bucket_def])
        fig = px.bar(bdf, x="Okno", y="Zakupów", title="Czas od rejestracji do zakupu stoiska",
                     color_discrete_sequence=[COLORS[4]], text="Zakupów")
        fig.update_layout(xaxis_title="", yaxis_title="Liczba kupujących")
        st.plotly_chart(fig, use_container_width=True)

    with col_cm:
        city_rows = []
        for miasto in CELE_JESIEN_2026:
            col = CITY_COL_MAP.get(miasto)
            if not col or col not in klc.columns:
                continue
            sel = pd.to_numeric(klc[col], errors="coerce").fillna(0) > 0
            sub = klc[sel]
            if len(sub):
                city_rows.append({"Miasto": miasto, "Konwersja %": round(sub["ma_stoisko"].mean() * 100, 1)})
        citydf = pd.DataFrame(city_rows).sort_values("Konwersja %", ascending=True)
        fig = px.bar(citydf, x="Konwersja %", y="Miasto", orientation="h",
                     title="Konwersja konto → stoisko per miasto (kiedykolwiek)",
                     color_discrete_sequence=[COLORS[0]], text="Konwersja %")
        fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig.update_layout(xaxis_title="Konwersja %", yaxis_title="")
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ── Pipeline per miasto ──
    st.subheader("Pipeline per miasto — leady do konwersji (w oknie)")
    st.caption("Leady z flagą rejestracji danego miasta. Lead może być zainteresowany kilkoma miastami (sumy się nakładają).")
    pipe_rows = []
    for miasto, col in CITY_COL_MAP.items():
        if col not in leady_f.columns:
            continue
        n_okno = int((pd.to_numeric(leady_f[col], errors="coerce").fillna(0) > 0).sum())
        n_all = int((pd.to_numeric(leady_all[col], errors="coerce").fillna(0) > 0).sum())
        if n_all == 0 and miasto not in CELE_JESIEN_2026:
            continue
        pipe_rows.append({
            "Miasto": miasto,
            "Leady (okno)": n_okno,
            "Leady (wszyscy)": n_all,
            "Cel jesień 2026": CELE_JESIEN_2026.get(miasto, 0),
            "_cel": miasto in CELE_JESIEN_2026,
        })
    pipe = pd.DataFrame(pipe_rows).sort_values("Leady (okno)", ascending=False)

    col_p1, col_p2 = st.columns([3, 2])
    with col_p1:
        pipe_plot = pipe[pipe["Leady (okno)"] > 0]
        fig = px.bar(pipe_plot, x="Miasto", y="Leady (okno)",
                     title="Leady w oknie per miasto", color="_cel",
                     color_discrete_map={True: COLORS[1], False: COLORS[7]},
                     text="Leady (okno)")
        fig.update_layout(showlegend=False, xaxis_title="", yaxis_title="Leady")
        st.plotly_chart(fig, use_container_width=True)
    with col_p2:
        pipe_show = pipe[pipe["_cel"]].drop(columns=["_cel"])
        st.markdown("**Miasta docelowe jesień 2026:**")
        st.dataframe(pipe_show, use_container_width=True, hide_index=True)

    st.divider()

    # ── Lista kontaktów do eksportu ──
    st.subheader("📨 Lista leadów do kontaktu (eksport)")
    branze_map_l = dict(zip(branze["id"].astype(str), branze["nazwa"]))
    miasta_opcje = ["(wszystkie miasta)"] + list(CITY_COL_MAP.keys())
    cs1, cs2 = st.columns([3, 2])
    sel_m = cs1.selectbox("Miasto (flaga rejestracji)", miasta_opcje, key="lead_city")
    tylko_warm = cs2.checkbox("🔥 Tylko ciepłe okno (≤3 mies.)", value=False, key="lead_warm_only")

    lst = leady_f.copy()
    if sel_m != "(wszystkie miasta)":
        col = CITY_COL_MAP.get(sel_m)
        if col in lst.columns:
            lst = lst[pd.to_numeric(lst[col], errors="coerce").fillna(0) > 0]
    if tylko_warm:
        lst = lst[lst["mies_od_rej"] <= 3]

    lst["Priorytet"] = np.where(lst["mies_od_rej"] <= 3, "🔥 72h", "")
    lst["Branża"] = lst["branza"].astype(str).map(branze_map_l).fillna("—")
    lst["Zarejestrowano"] = lst["time_utw_dt"].dt.strftime("%Y-%m-%d")
    lst["Mies. temu"] = lst["mies_od_rej"].round(0).astype("Int64")
    lst = lst.sort_values("time_utw_dt", ascending=False)
    lst_show = lst[["Priorytet", "nazwa", "email", "telefon", "Branża", "miasto", "Zarejestrowano", "Mies. temu"]].copy()
    lst_show.columns = ["Priorytet", "Nazwa", "E-mail", "Telefon", "Branża", "Miasto (konto)", "Zarejestrowano", "Mies. temu"]

    n_warm_sel = int((lst["mies_od_rej"] <= 3).sum())
    st.caption(f"**{len(lst_show)}** leadów w wyborze (okno: {okno_label.lower()}, miasto: {sel_m}) — "
               f"w tym **{n_warm_sel}** w ciepłym oknie 🔥.")
    st.dataframe(lst_show, use_container_width=True, hide_index=True, height=360)
    fname_m = sel_m.replace("(wszystkie miasta)", "wszystkie").replace(" ", "")
    st.download_button(
        "⬇️ Pobierz listę leadów (CSV)",
        lst_show.to_csv(index=False).encode("utf-8-sig"),
        f"leady_{fname_m}_{okno_label.replace(' ', '').replace('.', '')}.csv",
        "text/csv", key="dl_leady_pipe",
    )


# ── Footer ───────────────────────────────────────────────────
st.divider()
st.caption(f"Dane z bazy klimekar_sw | Odświeżono: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
