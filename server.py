# server.py
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from geopy.distance import geodesic
import pandas as pd
import requests
import os

app = Flask(__name__)
CORS(app)

bars_df = pd.read_excel("bars.xlsx")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

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

@app.route("/")
def home():
    return "Backend Boire Facile OK"

@app.route("/closest_bars", methods=["POST"])
def get_closest_bars():
    data = request.get_json()
    try:
        lat = float(data.get("lat"))
        lon = float(data.get("lon"))
    except (TypeError, ValueError):
        return jsonify({"error": "Coordonnées invalides"}), 400

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
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "distance_m": round(row["distance"])
        })

    return jsonify({"bars": results})

@app.route("/all_bars", methods=["GET"])
def get_all_bars():
    bars = []
    for _, row in bars_df.iterrows():
        bars.append({
            "nom": row["Nom"],
            "adresse": row["Adresse"],
            "prix": row["Prix"],
            "latitude": row["latitude"],
            "longitude": row["longitude"]
        })
    return jsonify({"bars": bars})


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
