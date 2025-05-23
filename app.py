import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re

st.set_page_config(page_title="Old Hickory Dam Flow Rates", layout="centered")
st.title("Old Hickory Dam - Downstream Flow Calculator")

st.markdown("""
**Instructions:**
- Retrieve the "Average Hourly Discharge" (in CFS) from the [TVA Old Hickory Dam lake levels page](https://www.tva.com/environment/lake-levels/Old-Hickory).
- Enter it below to calculate the flow rates at each mile marker downstream.
""")

# User input: Average Hourly Discharge (CFS)
flow_cfs = st.number_input(
    "Average Hourly Discharge (CFS - Cubic Feet per Second):",
    min_value=0,
    value=0,
    step=1,
    format="%d"
)
if flow_cfs == 0:
    st.warning("Please enter a valid discharge value to proceed.")


# User input: max mile marker
max_mile_marker = st.number_input(
    "Enter the maximum mile marker downstream from the dam:",
    min_value=1,
    value=30,
    step=1,
    format="%d"
)
mile_markers = list(range(0, max_mile_marker + 1))

import pandas as pd
import numpy as np
import requests
import shapely.geometry
import geopandas as gpd
import folium
from shapely.geometry import LineString, Point
from streamlit_folium import st_folium

if flow_cfs and flow_cfs > 0:
    # User input: estimated flow loss per mile
    loss_percent = st.number_input(
        "Estimated flow loss per mile (%)",
        min_value=0.0,
        max_value=100.0,
        value=0.5,
        step=0.1,
        format="%.2f"
    )
    loss_rate = loss_percent / 100.0
    flow_cfm_initial = flow_cfs * 60
    # Fetch Cumberland River path from OSM Overpass API
    st.info("Loading real Cumberland River path from OpenStreetMap...")
    overpass_url = "https://overpass-api.de/api/interpreter"
    # The OSM 'way' for the Cumberland River below Old Hickory Dam, bounding box for ~30 miles downstream
    bbox = [36.05, -86.8, 36.32, -86.6]  # south, west, north, east
    query = f"""
    [out:json][timeout:25];
    (
      way["waterway"="river"]["name"="Cumberland River"]({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
    );
    (._;>;);
    out body;
    """
    try:
        resp = requests.post(overpass_url, data={'data': query})
        resp.raise_for_status()
        data_osm = resp.json()
        nodes = {n['id']: (n['lat'], n['lon']) for n in data_osm['elements'] if n['type'] == 'node'}
        river_lines = []
        for el in data_osm['elements']:
            if el['type'] == 'way':
                coords = [nodes[nid] for nid in el['nodes'] if nid in nodes]
                if len(coords) > 1:
                    river_lines.append(LineString([(lon, lat) for lat, lon in coords]))
        # Merge all river segments into one line
        if len(river_lines) == 0:
            raise Exception("No river lines found in OSM response.")
        river_line = river_lines[0]
        for l in river_lines[1:]:
            river_line = river_line.union(l)
        if river_line.geom_type == 'MultiLineString':
            river_line = max(river_line.geoms, key=lambda g: g.length)
    except Exception as e:
        st.error(f"Error loading river geometry from OSM: {e}")
        st.stop()

    # Interpolate mile markers along river path
    river_length_m = river_line.length * 111139  # degrees to meters (approx, latitude)
    river_length_miles = river_length_m / 1609.34
    n_markers = max(mile_markers)
    distances = np.linspace(0, river_line.length, n_markers+1)
    marker_points = [river_line.interpolate(d) for d in distances]
    marker_lats = [p.y for p in marker_points]
    marker_lons = [p.x for p in marker_points]
    marker_miles = list(range(n_markers+1))
    map_df = pd.DataFrame({"lat": marker_lats, "lon": marker_lons, "Mile Marker": marker_miles})

    st.subheader("Enter Your Location (Latitude and Longitude)")
    user_lat = st.number_input("Your Latitude", value=marker_lats[0], format="%.6f")
    user_lon = st.number_input("Your Longitude", value=marker_lons[0], format="%.6f")

    # Find nearest point on river and river mile
    user_point = Point(user_lon, user_lat)
    dists = [user_point.distance(Point(lon, lat)) for lon, lat in zip(marker_lons, marker_lats)]
    min_idx = int(np.argmin(dists))
    nearest_marker = marker_miles[min_idx]
    nearest_lat = marker_lats[min_idx]
    nearest_lon = marker_lons[min_idx]

# --- Load dams from static JSON file ---
import json
with open("cumberland_dams.json", "r") as f:
    dams = json.load(f)
if not dams:
    st.error("Could not load dam data from cumberland_dams.json.")
    st.stop()
# Sort dams from upstream to downstream by river mile (descending)
dams.sort(key=lambda d: -d["river_mile"])

# --- Dam selection UI ---
dam_names = [d["name"] for d in dams]
default_index = 0
selected_dam_name = st.selectbox("Choose starting dam:", dam_names, index=default_index)
selected_dam_idx = dam_names.index(selected_dam_name)
selected_dam = dams[selected_dam_idx]

# Limit max mile marker to next dam downstream (if any), using river mile
if selected_dam_idx < len(dams) - 1:
    next_dam = dams[selected_dam_idx + 1]
    max_mile_allowed = selected_dam["river_mile"] - next_dam["river_mile"]
else:
    max_mile_allowed = selected_dam["river_mile"]  # allow up to river mouth

st.success(f"Nearest Mile Marker: {nearest_marker} (Lat: {nearest_lat:.5f}, Lon: {nearest_lon:.5f})")
cfm_at_user = int(flow_cfm_initial * ((1 - loss_rate) ** nearest_marker))
st.info(f"Estimated Flow Rate at Your Location: {cfm_at_user:,} CFM")

# Plot with folium for better OSM visualization
m = folium.Map(location=[marker_lats[0], marker_lons[0]], zoom_start=11, tiles="OpenStreetMap")
folium.PolyLine(list(zip(marker_lats, marker_lons)), color="blue", weight=3, tooltip="Cumberland River").add_to(m)
import datetime
river_velocity_mph = 2.5  # Assumed average river velocity
now = datetime.datetime.strptime("2025-05-22 13:50:43", "%Y-%m-%d %H:%M:%S")
# Use selected dam as starting point for calculations
dam_lat = selected_dam["lat"]
dam_lon = selected_dam["lon"]
for idx, (lat, lon, mile) in enumerate(zip(marker_lats, marker_lons, marker_miles)):
    if mile in mile_markers and mile <= max_mile_allowed:
        travel_time_hr = mile / river_velocity_mph
        arrival_time = now + datetime.timedelta(hours=travel_time_hr)
        cfm_at_mile = int(flow_cfm_initial * ((1 - loss_rate) ** mile))
        popup_content = (
            f"<pre style='white-space: pre; font-family: monospace; min-width: 220px; width: 340px;'>"
            f"Mile {mile}<br>Lat: {lat:.5f}<br>Lon: {lon:.5f}<br>Arrival: {arrival_time.strftime('%Y-%m-%d %H:%M:%S')}<br>CFM: {cfm_at_mile:,}"
            f"</pre>"
        )
        folium.CircleMarker(
            location=[lat, lon],
            radius=6,
            color="green",
            fill=True,
            fill_color="green",
            fill_opacity=0.8,
            tooltip=folium.Tooltip(popup_content, sticky=True, direction='right', permanent=False, max_width=340),
            popup=folium.Popup(popup_content, max_width=340)
        ).add_to(m)
# Calculate flow at user's location (nearest mile marker)
cfm_at_user = int(flow_cfm_initial * ((1 - loss_rate) ** nearest_marker))
dam_popup_content = (
    f"<pre style='white-space: pre; font-family: monospace; min-width: 220px; width: 340px;'>"
    f"{selected_dam['name']}<br>Lat: {dam_lat:.5f}<br>Lon: {dam_lon:.5f}<br>Time: {now.strftime('%Y-%m-%d %H:%M:%S')}"
    f"</pre>"
)
folium.CircleMarker(
    location=[dam_lat, dam_lon],
    radius=8,
    color="red",
    fill=True,
    fill_color="red",
    fill_opacity=0.9,
    tooltip=folium.Tooltip(dam_popup_content, sticky=True, direction='right', permanent=False, max_width=340),
    popup=folium.Popup(dam_popup_content, max_width=340)
).add_to(m)
st.subheader("Map of Cumberland River, Mile Markers, and Dam Location")
st_folium(m, width=700, height=700)
st.caption("River path, markers, and dam from OpenStreetMap and Wikipedia. For high-precision work, use official TVA or GIS data.")
