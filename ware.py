import streamlit as st
import sqlite3
from pyzbar.pyzbar import decode
from PIL import Image
import numpy as np
import os
import pandas as pd
import altair as alt

# Per geocodifica e mappa (opzionale)
# pip install geopy folium
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
    "X001UISBQ9": {"name": "SONOFF TRV", "purchase_price": 37.00},
  
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
    # Crea tabella transactions se non esiste
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            barcode TEXT,
            quantity INTEGER,
            type TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    # Verifica ed eventualmente aggiunge le colonne se non esistono
    cursor.execute("PRAGMA table_info(transactions)")
    columns_info = cursor.fetchall()
    existing_columns = [col[1] for col in columns_info]

    if "customer_name" not in existing_columns:
        cursor.execute("ALTER TABLE transactions ADD COLUMN customer_name TEXT")
    if "project_name" not in existing_columns:
        cursor.execute("ALTER TABLE transactions ADD COLUMN project_name TEXT")
    if "location" not in existing_columns:
        cursor.execute("ALTER TABLE transactions ADD COLUMN location TEXT")

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
        INSERT INTO transactions (barcode, quantity, type, customer_name, project_name, location) VALUES (?, ?, 'in', NULL, NULL, NULL)
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


def delete_product(barcode):
    conn = sqlite3.connect("warehouse.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM inventory WHERE barcode = ?", (barcode,))
    conn.commit()
    conn.close()


def get_inventory():
    conn = sqlite3.connect("warehouse.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT product_name, barcode, quantity, purchase_price, image_path FROM inventory
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


def read_barcode_from_image(image):
    decoded_objects = decode(image)
    for obj in decoded_objects:
        return obj.data.decode("utf-8")
    return None


def get_installations():
    # Ritorna tutte le transazioni di tipo 'out' con i dettagli
    conn = sqlite3.connect("warehouse.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT barcode, quantity, customer_name, project_name, location, timestamp 
        FROM transactions WHERE type='out'
    """)
    results = cursor.fetchall()
    conn.close()
    return results

#/////////

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

#//////


initialize_database()

if menu == "Carica a Magazzino":
    st.header("Carica a Magazzino")
    st.write("Puoi scansionare il codice a barre usando la fotocamera oppure inserire manualmente il codice.")
    uploaded_image = st.camera_input("Scansiona il codice a barre")
    manual_barcode = st.text_input("Oppure inserisci manualmente il Codice a Barre:", value="")

    barcode = None
    if uploaded_image:
        image = Image.open(uploaded_image)
        image_np = np.array(image)
        barcode_detected = read_barcode_from_image(image_np)
        if barcode_detected:
            barcode = barcode_detected
            st.success(f"Codice a barre rilevato: **{barcode}**")
        else:
            st.error("Impossibile leggere il codice a barre dall'immagine.")
    elif manual_barcode.strip():
        barcode = manual_barcode.strip()
        st.info(f"Codice a barre inserito manualmente: **{barcode}**")

    quantity = st.number_input("Quantità", min_value=1, step=1)
    image_file = st.file_uploader("Carica un'immagine del prodotto (facoltativo)", type=["jpg", "png", "jpeg"])

    if st.button("Carica Prodotto"):
        if not barcode:
            st.error("Nessun codice a barre valido fornito. Non è possibile caricare il prodotto.")
        elif barcode not in PRODUCTS:
            st.error("Codice a barre non presente nel dizionario prodotti. Impossibile caricare questo prodotto.")
        elif quantity <= 0:
            st.error("La quantità deve essere maggiore di zero.")
        else:
            image_path = None
            if image_file:
                image_path = f"images/{barcode}.png"
                os.makedirs("images", exist_ok=True)
                with open(image_path, "wb") as f:
                    f.write(image_file.getbuffer())
            success = add_product(barcode, quantity, image_path)
            if success:
                st.success("Prodotto caricato con successo!")

elif menu == "Scarica da Magazzino":
    st.header("Scarica da Magazzino")
    uploaded_image = st.camera_input("Scansiona il codice a barre")

    barcode_input = st.text_input("Codice a Barre", value="")
    barcode = barcode_input.strip()

    if uploaded_image:
        image = Image.open(uploaded_image)
        image_np = np.array(image)
        scanned_barcode = read_barcode_from_image(image_np)
        if scanned_barcode:
            st.success(f"Codice a barre rilevato: **{scanned_barcode}**")
            barcode = scanned_barcode
        else:
            st.error("Impossibile leggere il codice a barre dall'immagine.")

    quantity = st.number_input("Quantità da scaricare", min_value=1, step=1)

    customer_name = st.text_input("Nome Cliente/Struttura")
    project_name = st.text_input("Nome Progetto")
    location = st.text_input("Location (Città, Indirizzo)")

    if st.button("Scarica Prodotto"):
        if not barcode:
            st.error("Inserisci o scansiona un codice a barre valido.")
        elif quantity <= 0:
            st.error("La quantità deve essere maggiore di zero.")
        elif not customer_name or not project_name or not location:
            st.error("Compila tutti i campi: Cliente, Progetto, Location.")
        else:
            success = remove_product(barcode, quantity, customer_name, project_name, location)
            if success:
                st.success("Prodotto scaricato con successo!")
                st.info(f"Scaricato per: {customer_name}, Progetto: {project_name}, Location: {location}")

elif menu == "Visualizza Magazzino":
    st.header("Magazzino")

    filter_text = st.text_input("Filtra per nome prodotto o codice a barre:", value="")

    inventory = get_inventory()

    if inventory:
        inventory_data = []
        for product in inventory:
            product_name, barcode, quantity, purchase_price, image_path = product
            sale_price = purchase_price * 2
            total_value = purchase_price * quantity
            inventory_data.append({
                "Nome Prodotto": product_name,
                "Codice a Barre": barcode,
                "Quantità": quantity,
                "Prezzo Acquisto (€)": purchase_price,
                "Prezzo Vendita (€)": sale_price,
                "Valore Totale (€)": total_value,
            })

        df = pd.DataFrame(inventory_data)

        if filter_text:
            df = df[df["Nome Prodotto"].str.contains(filter_text, case=False, na=False) |
                    df["Codice a Barre"].str.contains(filter_text, case=False, na=False)]

        st.dataframe(df.style.format({
            "Prezzo Acquisto (€)": "€{:.2f}",
            "Prezzo Vendita (€)": "€{:.2f}",
            "Valore Totale (€)": "€{:.2f}",
        }))

        total_value_sum = df["Valore Totale (€)"].sum()
        st.subheader(f"Valore complessivo del magazzino: €{total_value_sum:.2f}")

        st.subheader("Andamento Mensile Entrate/Uscite")
        monthly_df = get_monthly_transactions()
        if not monthly_df.empty:
            monthly_melted = monthly_df.melt("month", var_name="type", value_name="quantity")

            chart = alt.Chart(monthly_melted).mark_line(point=True).encode(
                x='month:T',
                y='quantity:Q',
                color='type:N',
                tooltip=['month', 'type', 'quantity']
            ).properties(
                width=700,
                height=400
            )
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("Non sono ancora presenti transazioni nel database.")

    else:
        st.write("Nessun prodotto in magazzino.")

elif menu == "Visualizza Installazioni":
    st.header("Installazioni (Uscite)")

    installations = get_installations()

    if installations:
        # installations contiene: barcode, quantity, customer_name, project_name, location, timestamp
        inst_data = []
        for row in installations:
            barcode, quantity, customer_name, project_name, location, timestamp = row
            product_name = PRODUCTS.get(barcode, {}).get("name", "Sconosciuto")
            inst_data.append({
                "Barcode": barcode,
                "Prodotto": product_name,
                "Quantità": quantity,
                "Cliente": customer_name,
                "Progetto": project_name,
                "Indirizzo": location,
                "Data": timestamp
            })

        df_inst = pd.DataFrame(inst_data)
        st.dataframe(df_inst)

        # Opzionale: Mostriamo una mappa con i marker delle location
        # ATTENZIONE: Questo funzionerà solo se i luoghi sono interpretabili da Nominatim
        if st.checkbox("Mostra Mappa con Installazioni"):
            geolocator = Nominatim(user_agent="warehouse_app")
            m = folium.Map(location=[41.9028, 12.4964], zoom_start=5)  # Centro approssimativo su Italia

            for idx, row in df_inst.iterrows():
                address = row["Indirizzo"]
                # Geocodifica l'indirizzo
                try:
                    location = geolocator.geocode(address)
                    if location:
                        folium.Marker(
                            [location.latitude, location.longitude],
                            popup=f"{row['Prodotto']} - {row['Cliente']} - {row['Progetto']}",
                            tooltip=row["Indirizzo"]
                        ).add_to(m)
                except:
                    pass

            st_folium(m, width=700, height=500)
    else:
        st.info("Non sono presenti installazioni registrate.")

elif menu == "Aggiorna Prezzo Acquisto":
    st.header("Aggiorna Prezzo d'Acquisto")
    inventory = get_inventory()

    if inventory:
        options = {f"{prod[0]} (Barcode: {prod[1]})": prod[1] for prod in inventory}
        selected = st.selectbox("Seleziona Prodotto", options.keys())
        selected_barcode = options[selected]

        new_price = st.number_input("Nuovo Prezzo d'Acquisto (€)", min_value=0.0, step=0.01)
        if st.button("Aggiorna Prezzo"):
            if new_price > 0:
                conn = sqlite3.connect("warehouse.db")
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE inventory
                    SET purchase_price = ?
                    WHERE barcode = ?
                """, (new_price, selected_barcode))
                conn.commit()
                conn.close()
                st.success(f"Prezzo per '{selected}' aggiornato a €{new_price:.2f}!")
            else:
                st.error("Inserire un prezzo valido!")
    else:
        st.warning("Nessun prodotto in magazzino.")


elif menu == "Aggiungi Nuovo Prodotto":
    add_new_product()
