import streamlit as st
import sqlite3
from pyzbar.pyzbar import decode
from PIL import Image
import numpy as np
import os
import pandas as pd
import altair as alt
from geopy.geocoders import Nominatim
import folium
from streamlit_folium import st_folium

st.set_page_config(layout="wide")

logo_url = "sin.png"
st.sidebar.image(logo_url, use_column_width=False, width=200)
st.sidebar.title("Gestione Magazzino")

menu = st.sidebar.radio("Navigazione", ["Visualizza Magazzino", "Carica a Magazzino", "Scarica da Magazzino",
                                        "Visualizza Installazioni", "Aggiorna Prezzo Acquisto", "Aggiungi Nuovo Prodotto"])

PRODUCTS = {
    "3800235261576": {"name": "Shelly 1 Mini Gen3", "purchase_price": 10.00},
    "3800235268018": {"name": "Shelly Pro 1PM", "purchase_price": 25.00},
    "3800235268032": {"name": "Shelly Pro 2PM", "purchase_price": 30.00},
    "3800235268001": {"name": "Shelly Pro 1", "purchase_price": 20.00},
    "3800235261590": {"name": "Shelly 1PM Mini Gen3", "purchase_price": 12.50},
    "3800235268100": {"name": "Shelly Pro 3EM", "purchase_price": 50.00},
    "3800235268117": {"name": "Shelly Pro 3EM-400", "purchase_price": 55.00},
    "3800235268148": {"name": "Shelly Pro EM-50", "purchase_price": 35.00},
}

def initialize_database():
    conn = sqlite3.connect("warehouse.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT,
            barcode TEXT UNIQUE,
            quantity INTEGER,
            purchase_price REAL,
            image_path TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            barcode TEXT,
            quantity INTEGER,
            type TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            customer_name TEXT,
            project_name TEXT,
            location TEXT
        )
    """)
    conn.commit()
    conn.close()

def add_product(barcode, quantity, image_path):
    if quantity <= 0:
        st.error("Quantità non valida (deve essere maggiore di 0).")
        return False

    product = PRODUCTS.get(barcode)
    if not product:
        st.error("Codice a barre non riconosciuto. Impossibile aggiungere il prodotto.")
        return False

    product_name = product["name"]
    purchase_price = product["purchase_price"]

    conn = sqlite3.connect("warehouse.db")
    cursor = conn.cursor()

    cursor.execute("SELECT quantity FROM inventory WHERE barcode = ?", (barcode,))
    existing = cursor.fetchone()

    if existing:
        cursor.execute("""
            UPDATE inventory
            SET quantity = quantity + ?
            WHERE barcode = ?
        """, (quantity, barcode))
    else:
        cursor.execute("""
            INSERT INTO inventory (barcode, product_name, quantity, purchase_price, image_path)
            VALUES (?, ?, ?, ?, ?)
        """, (barcode, product_name, quantity, purchase_price, image_path))

    cursor.execute("""
        INSERT INTO transactions (barcode, quantity, type, customer_name, project_name, location)
        VALUES (?, ?, 'in', NULL, NULL, NULL)
    """, (barcode, quantity))

    conn.commit()
    conn.close()
    return True

def remove_product(barcode, quantity, customer_name, project_name, location):
    if quantity <= 0:
        st.error("Quantità non valida (deve essere maggiore di 0).")
        return False

    if not customer_name or not project_name or not location:
        st.error("Compila tutti i campi: Cliente, Progetto, Location.")
        return False

    conn = sqlite3.connect("warehouse.db")
    cursor = conn.cursor()
    cursor.execute("SELECT quantity FROM inventory WHERE barcode = ?", (barcode,))
    result = cursor.fetchone()

    if not result:
        st.error("Prodotto non trovato in magazzino.")
        conn.close()
        return False

    if result[0] < quantity:
        st.error("Quantità non disponibile in magazzino per questa richiesta.")
        conn.close()
        return False

    cursor.execute("""
        UPDATE inventory SET quantity = quantity - ?
        WHERE barcode = ?
    """, (quantity, barcode))

    cursor.execute("""
        INSERT INTO transactions (barcode, quantity, type, customer_name, project_name, location)
        VALUES (?, ?, 'out', ?, ?, ?)
    """, (barcode, quantity, customer_name, project_name, location))

    conn.commit()
    conn.close()
    return True

def get_inventory():
    conn = sqlite3.connect("warehouse.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT product_name, barcode, quantity, purchase_price, image_path FROM inventory
    """)
    results = cursor.fetchall()
    conn.close()
    return results

def get_installations():
    conn = sqlite3.connect("warehouse.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT barcode, quantity, customer_name, project_name, location, timestamp
        FROM transactions WHERE type = 'out'
    """)
    results = cursor.fetchall()
    conn.close()
    return results

def get_monthly_transactions():
    conn = sqlite3.connect("warehouse.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT strftime('%Y-%m', timestamp) as month,
               SUM(CASE WHEN type='in' THEN quantity ELSE 0 END) as total_in,
               SUM(CASE WHEN type='out' THEN quantity ELSE 0 END) as total_out
        FROM transactions
        GROUP BY strftime('%Y-%m', timestamp)
        ORDER BY month
    """)
    results = cursor.fetchall()
    conn.close()
    df = pd.DataFrame(results, columns=["month", "total_in", "total_out"])
    return df

def add_new_product():
    st.header("Aggiungi Nuovo Prodotto")
    new_barcode = st.text_input("Inserisci il Codice a Barre:", value="")
    new_name = st.text_input("Inserisci il Nome del Prodotto:")
    new_price = st.number_input("Inserisci il Prezzo d'Acquisto (€):", min_value=0.0, step=0.01)
    image_file = st.file_uploader("Carica un'immagine del prodotto (facoltativo)", type=["jpg", "png", "jpeg"])

    if st.button("Aggiungi Prodotto"):
        if not new_barcode or not new_name or new_price <= 0:
            st.error("Inserisci tutti i dettagli richiesti e un prezzo valido.")
            return
        
        if new_barcode in PRODUCTS:
            st.error("Il codice a barre esiste già. Non è possibile aggiungere un prodotto duplicato.")
            return

        # Salva immagine, se fornita
        image_path = None
        if image_file:
            image_path = f"images/{new_barcode}.png"
            os.makedirs("images", exist_ok=True)
            with open(image_path, "wb") as f:
                f.write(image_file.getbuffer())
        
        # Aggiungi al dizionario
        PRODUCTS[new_barcode] = {
            "name": new_name,
            "purchase_price": new_price,
        }

        # Aggiungi al database
        conn = sqlite3.connect("warehouse.db")
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO inventory (barcode, product_name, quantity, purchase_price, image_path)
            VALUES (?, ?, ?, ?, ?)
        """, (new_barcode, new_name, 0, new_price, image_path))
        conn.commit()
        conn.close()

        st.success(f"Prodotto '{new_name}' aggiunto con successo!")

initialize_database()

if menu == "Visualizza Magazzino":
    st.header("Magazzino")
    inventory = get_inventory()
    if inventory:
        st.write("Prodotti in magazzino:")
        df = pd.DataFrame(inventory, columns=["Nome", "Codice a Barre", "Quantità", "Prezzo Acquisto", "Immagine"])
        st.dataframe(df)
    else:
        st.info("Magazzino vuoto.")

elif menu == "Carica a Magazzino":
    st.header("Carica a Magazzino")
    # Funzione di caricamento

elif menu == "Scarica da Magazzino":
    st.header("Scarica da Magazzino")
    # Funzione di scarico

elif menu == "Visualizza Installazioni":
    st.header("Installazioni")
    installations = get_installations()
    # Mostra le installazioni

elif menu == "Aggiorna Prezzo Acquisto":
    st.header("Aggiorna Prezzo Acquisto")
    # Funzione per aggiornare il prezzo

elif menu == "Aggiungi Nuovo Prodotto":
    add_new_product()
