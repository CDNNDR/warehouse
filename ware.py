import streamlit as st
import sqlite3
from pyzbar.pyzbar import decode
import av
from streamlit_webrtc import webrtc_streamer, VideoTransformerBase
from PIL import Image
import cv2
import numpy as np
import os

# Dizionario dei prodotti con codice a barre e nome
PRODUCTS = {
    "3800235261576": "Shelly 1 Mini Gen3",
    "3800235268018": "Shelly Pro 1PM",
    "3800235268032": "Shelly Pro 2PM",
    "3800235268001": "Shelly Pro 1",
    "3800235261590": "Shelly 1PM Mini Gen3",
    "3800235268100": "Shelly Pro 3EM",
    "3800235268117": "Shelly Pro 3EM-400",
    "3800235268148": "Shelly Pro EM-50",
}

# Configura il database
def initialize_database():
    conn = sqlite3.connect("warehouse.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT,
            barcode TEXT UNIQUE,
            quantity INTEGER,
            image_path TEXT
        )
    """)
    conn.commit()
    conn.close()

# Aggiungi prodotto
def add_product(barcode, quantity, image_path):
    product_name = PRODUCTS.get(barcode, "Sconosciuto")
    conn = sqlite3.connect("warehouse.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO inventory (barcode, product_name, quantity, image_path)
        VALUES (?, ?, ?, ?)
    """, (barcode, product_name, quantity, image_path))
    cursor.execute("""
        UPDATE inventory SET quantity = quantity + ?
        WHERE barcode = ?
    """, (quantity, barcode))
    conn.commit()
    conn.close()

# Scarica prodotto
def remove_product(barcode, quantity):
    conn = sqlite3.connect("warehouse.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT quantity FROM inventory WHERE barcode = ?
    """, (barcode,))
    result = cursor.fetchone()
    if result and result[0] >= quantity:
        cursor.execute("""
            UPDATE inventory SET quantity = quantity - ?
            WHERE barcode = ?
        """, (quantity, barcode))
        conn.commit()
    conn.close()

# Visualizza magazzino
def get_inventory():
    conn = sqlite3.connect("warehouse.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT product_name, barcode, quantity, image_path FROM inventory
    """)
    results = cursor.fetchall()
    conn.close()
    return results

# Barcode scanner con OpenCV
class BarcodeScanner(VideoTransformerBase):
    def __init__(self):
        self.barcode = None

    def transform(self, frame):
        img = frame.to_ndarray(format="bgr24")
        decoded_objects = decode(img)

        for obj in decoded_objects:
            self.barcode = obj.data.decode("utf-8")
            # Disegna il rettangolo intorno al codice a barre
            (x, y, w, h) = obj.rect
            cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(img, self.barcode, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            break

        return av.VideoFrame.from_ndarray(img, format="bgr24")

# Configurazione iniziale del database
initialize_database()

# Interfaccia Streamlit
st.title("Gestione Magazzino")

# Menu di navigazione
menu = st.sidebar.radio("Navigazione", ["Carica a Magazzino", "Scarica da Magazzino", "Visualizza Magazzino"])

if menu == "Carica a Magazzino":
    st.header("Carica a Magazzino")

    # Webcam per la scansione del codice a barre
    st.subheader("Scansiona il codice a barre con la fotocamera")
    barcode_scanner = webrtc_streamer(key="barcode-scanner", video_transformer_factory=BarcodeScanner)

    barcode = None
    if barcode_scanner and barcode_scanner.video_transformer:
        barcode = barcode_scanner.video_transformer.barcode
        if barcode:
            st.success(f"Codice a barre rilevato: **{barcode}**")
            if barcode in PRODUCTS:
                st.write(f"Prodotto rilevato: **{PRODUCTS[barcode]}**")
            else:
                st.warning("Codice a barre non riconosciuto.")

    quantity = st.number_input("Quantità", min_value=1, step=1)
    image = st.file_uploader("Carica un'immagine del prodotto (facoltativo)", type=["jpg", "png", "jpeg"])

    if st.button("Carica Prodotto"):
        if barcode and quantity > 0:
            image_path = None
            if image:
                image_path = f"images/{barcode}.png"
                os.makedirs("images", exist_ok=True)
                with open(image_path, "wb") as f:
                    f.write(image.getbuffer())
            add_product(barcode, quantity, image_path)
            st.success("Prodotto caricato con successo!")
        else:
            st.error("Inserisci tutti i dati richiesti!")

elif menu == "Scarica da Magazzino":
    st.header("Scarica da Magazzino")
    barcode = st.text_input("Codice a Barre")
    quantity = st.number_input("Quantità da scaricare", min_value=1, step=1)

    if barcode in PRODUCTS:
        st.write(f"Prodotto rilevato: **{PRODUCTS[barcode]}**")
    else:
        st.warning("Codice a barre non riconosciuto.")

    if st.button("Scarica Prodotto"):
        if barcode and quantity > 0:
            remove_product(barcode, quantity)
            st.success("Prodotto scaricato con successo!")
        else:
            st.error("Inserisci tutti i dati richiesti!")

elif menu == "Visualizza Magazzino":
    st.header("Magazzino")
    inventory = get_inventory()
    for product in inventory:
        product_name, barcode, quantity, image_path = product
        st.subheader(f"Nome Prodotto: {product_name}")
        st.write(f"Codice a Barre: {barcode}")
        st.write(f"Quantità: {quantity}")
        if image_path and os.path.exists(image_path):
            image = Image.open(image_path)
            st.image(image, caption=product_name, use_column_width=True)
