import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
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
    load_platnosci, load_leads, load_branze, load_wyjscia,
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
    leads = load_leads()
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

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "Przegląd ogólny",
    "Eventy i miasta",
    "Bilety",
    "Wystawcy i zamówienia",
    "Przychody i płatności",
    "Leady i rabaty",
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

        c13, c14, c15, c16 = st.columns(4)
        c13.metric("Rejestracje → zamówienie", f"{konw_rej}%",
                   help=f"{total_z_zam} z {total_rej} nowych klientów złożyło zamówienie")
        c14.metric("Powracający klienci", f"{pct_powracajacy}%",
                   help=f"{total_powracajacy} klientów złożyło więcej niż 1 zamówienie")
        c15.metric("Śr. zamówień na klienta", f"{sr_zam}")
        c16.metric("Klienci z zamówieniem", f"{total_z_zam} / {total_rej}")

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
    st.header("Leady i rabaty")

    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("Leady")
        c1, c2, c3 = st.columns(3)
        c1.metric("Łącznie leadów", len(leads))
        converted = leads[leads["makontoklienta"] == 1].shape[0]
        c2.metric("Skonwertowane", converted)
        c3.metric("Konwersja", f"{converted / max(len(leads), 1) * 100:.1f}%")

        interest = pd.DataFrame({
            "Typ usługi": ["Stoisko", "Ekspozycja", "Występ", "Pokaz", "Prowadzenie", "Reklama"],
            "Zainteresowanych": [
                leads["i_stoisko"].sum(),
                leads["i_ekspozycja"].sum(),
                leads["i_wystep"].sum(),
                leads["i_pokaz"].sum(),
                leads["i_prowadzenie"].sum(),
                leads["i_reklama"].sum(),
            ]
        })
        fig = px.bar(interest, x="Zainteresowanych", y="Typ usługi", orientation="h",
                     title="Leady — zainteresowanie typem usługi",
                     color_discrete_sequence=COLORS, text="Zainteresowanych")
        fig.update_layout(yaxis_title="")
        st.plotly_chart(fig, use_container_width=True)

        leads_copy = leads.copy()
        leads_copy["data_utw_dt"] = pd.to_datetime(leads_copy["data_utw"], errors="coerce")
        leads_copy["miesiac"] = leads_copy["data_utw_dt"].dt.to_period("M").astype(str)
        leads_m = leads_copy.groupby("miesiac").size().reset_index(name="ile")
        leads_m = leads_m.sort_values("miesiac").tail(24)
        fig = px.line(leads_m, x="miesiac", y="ile",
                      title="Nowe leady miesięcznie",
                      color_discrete_sequence=COLORS)
        fig.update_layout(xaxis_title="Miesiąc", yaxis_title="Leady")
        st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.subheader("Rabaty")
        c1, c2, c3 = st.columns(3)
        c1.metric("Kodów rabatowych", len(rabaty))
        c2.metric("Łączne użycia", int(rabaty["uzycia"].sum()))
        c3.metric("Wartość rabatów", format_pln(rabaty["suma_rabatu"].sum()))

        rabaty_top = rabaty[rabaty["uzycia"] > 0].sort_values("uzycia", ascending=True)
        fig = px.bar(rabaty_top, x="uzycia", y="kod", orientation="h",
                     title="Kody rabatowe — liczba użyć",
                     color_discrete_sequence=[COLORS[5]], text="uzycia")
        fig.update_layout(yaxis_title="Kod", xaxis_title="Użycia")
        st.plotly_chart(fig, use_container_width=True)

        rabaty_val = rabaty[rabaty["suma_rabatu"] > 0].sort_values("suma_rabatu", ascending=True)
        fig = px.bar(rabaty_val, x="suma_rabatu", y="kod", orientation="h",
                     title="Kody rabatowe — wartość rabatów",
                     color_discrete_sequence=[COLORS[3]], text_auto=".2s")
        fig.update_layout(yaxis_title="Kod", xaxis_title="zł")
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


# ── Footer ───────────────────────────────────────────────────
st.divider()
st.caption(f"Dane z bazy klimekar_sw | Odświeżono: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
