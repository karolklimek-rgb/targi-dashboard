import mysql.connector
import pandas as pd
import streamlit as st

DB_CONFIG = {
    "host": st.secrets["db"]["host"],
    "port": st.secrets["db"]["port"],
    "user": st.secrets["db"]["user"],
    "password": st.secrets["db"]["password"],
    "database": st.secrets["db"]["database"],
}


def get_connection():
    return mysql.connector.connect(**DB_CONFIG)


@st.cache_data(ttl=300)
def query(sql: str) -> pd.DataFrame:
    conn = get_connection()
    try:
        df = pd.read_sql(sql, conn)
        return df
    finally:
        conn.close()


@st.cache_data(ttl=300)
def load_events() -> pd.DataFrame:
    return query("""
        SELECT id, symbol, miasto, data, akt, suma_m2,
               cena1m2, cena2m2, bilet_akt, bilet_cena, bilet_vip_cena
        FROM events
        ORDER BY data DESC
    """)


@st.cache_data(ttl=300)
def load_bilety() -> pd.DataFrame:
    return query("""
        SELECT b.id, b.idtargi, b.typ, b.status, b.ileosob, b.cena,
               b.kwota_brutto, b.kwota_netto, b.data_utw, b.ts_utw,
               b.ts_wejscie, b.godz_wejscie, b.kod_rabatu,
               e.symbol AS symbol_targi, e.miasto, e.data AS data_targi
        FROM bilety b
        LEFT JOIN events e ON b.idtargi = e.id
        WHERE b.status IN (2, 3)
    """)


@st.cache_data(ttl=300)
def load_zamowienia() -> pd.DataFrame:
    return query("""
        SELECT z.id, z.idtargi, z.symbol_targi, z.idklienta,
               z.ilem2, z.kwota_netto, z.kwota_brutto,
               z.data_utw, z.status, z.branza,
               e.miasto, e.data AS data_targi
        FROM zamowienia z
        LEFT JOIN events e ON CAST(z.idtargi AS UNSIGNED) = e.id
        WHERE z.ok_email != 'targi@targimlodejpary.pl'
          AND z.status NOT IN ('1', '4')
    """)


@st.cache_data(ttl=300)
def load_klienci() -> pd.DataFrame:
    return query("""
        SELECT id, nazwa, branza, miasto, email, akt, time_utw,
               rejestracja50, pierwszezamowienie
        FROM klienci
    """)


@st.cache_data(ttl=300)
def load_platnosci() -> pd.DataFrame:
    return query("""
        SELECT p.id, p.idzamowienia, p.kwota_brutto, p.kwota_netto,
               p.status, p.data_wym, p.data_ksiegowania,
               p.data_wystawienia_fv
        FROM platnosci p
    """)


@st.cache_data(ttl=300)
def load_leads() -> pd.DataFrame:
    return query("""
        SELECT id, nazwa, email, telefon, data_utw, makontoklienta, kolor,
               i_stoisko, i_ekspozycja, i_wystep, i_pokaz, i_prowadzenie, i_reklama
        FROM leads
    """)


@st.cache_data(ttl=300)
def load_branze() -> pd.DataFrame:
    return query("SELECT id, nazwa FROM branze ORDER BY kolejnosc")


@st.cache_data(ttl=300)
def load_wyjscia() -> pd.DataFrame:
    return query("""
        SELECT w.id, w.idtargi, w.ileosob, w.ts_utw,
               e.symbol AS symbol_targi, e.miasto, e.data AS data_targi
        FROM wyjscia w
        LEFT JOIN events e ON w.idtargi = e.id
    """)


@st.cache_data(ttl=300)
def load_rabaty() -> pd.DataFrame:
    return query("""
        SELECT r.id, r.kod, r.typ, r.wartosc, r.targi, r.produkt,
               r.akt, r.limit, r.wykorzystano,
               COUNT(rw.id) AS uzycia,
               SUM(CAST(rw.kwota_rabatu AS DECIMAL(10,2))) AS suma_rabatu
        FROM rabaty r
        LEFT JOIN rabaty_wykorzystanie rw ON r.id = rw.kod_id
        GROUP BY r.id
    """)


@st.cache_data(ttl=300)
def load_uslugi_zamowione() -> pd.DataFrame:
    return query("""
        SELECT uz.id, uz.idtargi, uz.idklienta, uz.nazwa,
               uz.cena_netto, uz.status, uz.typ,
               e.symbol AS symbol_targi, e.miasto, e.data AS data_targi
        FROM uslugi_zamowione uz
        LEFT JOIN events e ON uz.idtargi = e.id
    """)


@st.cache_data(ttl=300)
def load_places() -> pd.DataFrame:
    return query("""
        SELECT p.id, p.idtargi, p.symbol_targi, p.nr_boxu,
               p.powierzchnia, p.status, p.idzamowienia, p.idklienta, p.branza
        FROM places p
    """)
