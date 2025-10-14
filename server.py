# server.py
from flask import Flask, request, jsonify
from flask_cors import CORS
from geopy.distance import geodesic
import pandas as pd
import requests
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import traceback

app = Flask(__name__)
CORS(app)

# Load bars data with error handling
try:
    bars_df = pd.read_excel("bars.xlsx")
    print("✅ bars.xlsx loaded successfully")
except Exception as e:
    print(f"❌ Error loading bars.xlsx: {e}")
    # Create empty dataframe as fallback
    bars_df = pd.DataFrame(columns=["Nom", "Adresse", "Prix", "latitude", "longitude", "Happy Hour"])

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

# VERCEL-SPECIFIC DATABASE CONNECTION
def get_connection():
    DATABASE_URL = os.getenv('DATABASE_URL')
    
    if not DATABASE_URL:
        raise Exception("DATABASE_URL environment variable is not set")
    
    try:
        # Vercel provides DATABASE_URL in standard format
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        print("✅ Database connection successful")
        return conn
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        raise e

# Initialize database tables
def init_db():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS participants (
                id SERIAL PRIMARY KEY,
                session_id VARCHAR(255) NOT NULL,
                name VARCHAR(255),
                address TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        cur.close()
        conn.close()
        print("✅ Database table initialized")
    except Exception as e:
        print(f"❌ Database initialization error: {e}")

# Initialize database when app starts
init_db()

@app.route("/")
def home():
    return "Backend Boire Facile OK - Vercel"

@app.route("/test")
def test():
    return jsonify({"status": "OK", "message": "Vercel deployment working!"})

@app.route("/debug-db")
def debug_db():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT version();")
        version = cur.fetchone()
        
        # Check if participants table exists and has data
        cur.execute("SELECT COUNT(*) as count FROM participants")
        count = cur.fetchone()["count"]
        
        cur.close()
        conn.close()
        return jsonify({
            "status": "connected", 
            "postgres_version": version["version"],
            "participants_count": count
        })
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500

@app.route("/health")
def health():
    return jsonify({"status": "healthy", "service": "Boire Facile Backend"})

# KEEP ALL YOUR EXISTING ROUTES (directions, closest_bars, etc.)
@app.route("/directions", methods=["POST"])
def get_directions():
    data = request.get_json()
    origin = data.get("origin")
    destination = data.get("destination")

    if not origin or not destination:
        return jsonify({"error": "Coordonnées manquantes"}), 400

    try:
        url = (
            "https://maps.googleapis.com/maps/api/directions/json"
            f"?origin={origin}&destination={destination}"
            "&mode=transit&language=fr&region=fr"
            f"&key={GOOGLE_API_KEY}"
        )
        response = requests.get(url)
        directions = response.json()

        if directions["status"] != "OK":
            return jsonify({"error": "API Directions échouée"}), 500

        steps = []
        total_duration = directions["routes"][0]["legs"][0]["duration"]["text"]

        for step in directions["routes"][0]["legs"][0]["steps"]:
            html_instr = step.get("html_instructions", "")
            line_info = ""
            if step.get("transit_details"):
                transit = step["transit_details"]
                line = transit["line"]
                vehicle_name = line["vehicle"]["name"]
                line_name = line.get("short_name", line.get("name", ""))
                departure_stop = transit["departure_stop"]["name"]
                arrival_stop = transit["arrival_stop"]["name"]
                line_info = f" (🚌 {vehicle_name} {line_name} de {departure_stop} à {arrival_stop})"
            steps.append(f"{html_instr}{line_info}")

        return jsonify({"steps": steps, "duration": total_duration})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/closest_bars", methods=["POST"])
def get_closest_bars():
    data = request.get_json()
    try:
        lat = float(data.get("lat"))
        lon = float(data.get("lon"))
    except (TypeError, ValueError):
        return jsonify({"error": "Coordonnées invalides"}), 400

    try:
        def compute_distance(row):
            return geodesic((lat, lon), (row["latitude"], row["longitude"])).meters

        bars_df["distance"] = bars_df.apply(compute_distance, axis=1)
        closest = bars_df.sort_values("distance").head(3)

        results = []
        for _, row in closest.iterrows():
            results.append({
                "nom": row["Nom"],
                "adresse": row["Adresse"],
                "prix": row["Prix"],
                "happy_hour": row.get("Happy Hour", "Non renseigné"),
                "latitude": row["latitude"],
                "longitude": row["longitude"],
                "distance_m": round(row["distance"])
            })

        return jsonify({"bars": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/all_bars", methods=["GET"])
def get_all_bars():
    try:
        bars = []
        for _, row in bars_df.iterrows():
            bars.append({
                "nom": row["Nom"],
                "adresse": row["Adresse"],
                "prix": row["Prix"],
                "latitude": row["latitude"],
                "longitude": row["longitude"],
                "happy_hour": row.get("Happy Hour", "Non renseigné")
            })
        return jsonify({"bars": bars})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/save_participants", methods=["POST"])
def save_participants():
    try:
        data = request.get_json()
        print(f"📦 Received data: {data}")
        
        if not data:
            return jsonify({"error": "No JSON data received"}), 400
            
        session_id = data.get("sessionId")
        participants = data.get("participants", [])
        
        print(f"💾 Saving session: {session_id}, participants: {len(participants)}")

        conn = get_connection()
        cur = conn.cursor()
        
        cur.execute("DELETE FROM participants WHERE session_id = %s", (session_id,))
        print(f"🗑️ Deleted existing participants for session: {session_id}")
        
        for p in participants:
            cur.execute(
                "INSERT INTO participants (session_id, name, address) VALUES (%s, %s, %s)",
                (session_id, p.get("name"), p.get("address"))
            )
            print(f"✅ Saved participant: {p.get('name')}")
            
        conn.commit()
        cur.close()
        conn.close()
        
        print("💾 Save completed successfully")
        return jsonify({"status": "saved"})
        
    except Exception as e:
        print(f"❌ Save participants error: {e}")
        print(f"📋 Traceback: {traceback.format_exc()}")
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500

@app.route("/get_participants")
def get_participants():
    session_id = request.args.get("id")
    print(f"📥 Fetching participants for session: {session_id}")
    
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT name, address FROM participants WHERE session_id = %s", (session_id,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        print(f"✅ Found {len(rows)} participants for session: {session_id}")
        return jsonify({"participants": rows})
        
    except Exception as e:
        print(f"❌ Get participants error: {e}")
        print(f"📋 Traceback: {traceback.format_exc()}")
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500

# Vercel requires this - don't use app.run()
if __name__ == '__main__':
    app.run(debug=False)
