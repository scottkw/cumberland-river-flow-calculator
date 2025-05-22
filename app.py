import streamlit as st
import requests
from bs4 import BeautifulSoup

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

    st.success(f"Nearest Mile Marker: {nearest_marker} (Lat: {nearest_lat:.5f}, Lon: {nearest_lon:.5f})")
    cfm_at_user = int(flow_cfm_initial * ((1 - loss_rate) ** nearest_marker))
    st.info(f"Estimated Flow Rate at Your Location: {cfm_at_user:,} CFM")

    # Plot with folium for better OSM visualization
    m = folium.Map(location=[marker_lats[0], marker_lons[0]], zoom_start=11, tiles="OpenStreetMap")
    folium.PolyLine(list(zip(marker_lats, marker_lons)), color="blue", weight=3, tooltip="Cumberland River").add_to(m)
    for idx, (lat, lon, mile) in enumerate(zip(marker_lats, marker_lons, marker_miles)):
        if mile in mile_markers:
            cfm_at_mile = int(flow_cfm_initial * ((1 - loss_rate) ** mile))
            folium.CircleMarker(
                location=[lat, lon],
                radius=6,
                color="green",
                fill=True,
                fill_color="green",
                fill_opacity=0.8,
                tooltip=f"Mile {mile}\nLat: {lat:.5f}\nLon: {lon:.5f}\nCFM: {cfm_at_mile:,}"
            ).add_to(m)
    # Calculate flow at user's location (nearest mile marker)
    cfm_at_user = int(flow_cfm_initial * ((1 - loss_rate) ** nearest_marker))
    folium.CircleMarker(
        location=[nearest_lat, nearest_lon],
        radius=8,
        color="red",
        fill=True,
        fill_color="red",
        fill_opacity=0.9,
        tooltip=f"Old Hickory Dam\nLat: {nearest_lat:.5f}\nLon: {nearest_lon:.5f}",
        popup=f"Old Hickory Dam<br>Lat: {nearest_lat:.5f}<br>Lon: {nearest_lon:.5f}"
    ).add_to(m)
    st.subheader("Map of Cumberland River, Mile Markers, Dam, and Your Location")
    st_folium(m, width=700, height=500)
    st.caption("River path, markers, and dam from OpenStreetMap and Wikipedia. For high-precision work, use official TVA or GIS data.")
else:
    st.warning("Flow data unavailable; cannot compute CFM at mile markers.")
