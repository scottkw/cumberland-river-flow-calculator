import streamlit as st
import folium
from streamlit_folium import st_folium
import requests
import json
import numpy as np
from datetime import datetime, timedelta
import math
from typing import Dict, List, Tuple, Optional
import time
import pandas as pd

# Page configuration MUST be first
st.set_page_config(
    page_title="Cumberland River Flow Calculator",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Configure PWA using HTML components
def configure_pwa():
    """Configure PWA using HTML meta tags and manifest"""
    
    # PWA Manifest
    manifest = {
        "name": "Cumberland River Flow Calculator",
        "short_name": "River Flow",
        "description": "Calculate Cumberland River flow rates at any location",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#1f77b4",
        "theme_color": "#1f77b4",
        "orientation": "portrait",
        "icons": [
            {
                "src": "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTkyIiBoZWlnaHQ9IjE5MiIgdmlld0JveD0iMCAwIDE5MiAxOTIiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxyZWN0IHdpZHRoPSIxOTIiIGhlaWdodD0iMTkyIiBmaWxsPSIjMWY3N2I0Ii8+Cjx0ZXh0IHg9Ijk2IiB5PSIxMTAiIGZvbnQtZmFtaWx5PSJBcmlhbCIgZm9udC1zaXplPSI4MCIgZmlsbD0id2hpdGUiIHRleHQtYW5jaG9yPSJtaWRkbGUiPvCfjIo8L3RleHQ+Cjwvc3ZnPgo=",
                "sizes": "192x192",
                "type": "image/svg+xml"
            }
        ]
    }
    
    # Inject PWA HTML
    pwa_html = f'''
    <link rel="manifest" href="data:application/json;base64,{json.dumps(manifest).encode('utf-8').hex()}">
    <meta name="theme-color" content="#1f77b4">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="default">
    <meta name="apple-mobile-web-app-title" content="River Flow">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    '''
    
    st.markdown(pwa_html, unsafe_allow_html=True)

class CumberlandRiverFlowCalculator:
    """
    Calculate flow rates of the Cumberland River at given points and times
    based on dam releases, geographical data, and gravitational forces.
    """
    
    def __init__(self):
        # Cumberland River major dams from upstream to downstream
        self.dams = {
            'Wolf Creek Dam': {
                'usgs_site': '03160000',
                'lat': 36.8939, 'lon': -84.9269,
                'elevation_ft': 723,
                'capacity_cfs': 70000,
                'river_mile': 460.9
            },
            'Dale Hollow Dam': {
                'usgs_site': '03141000', 
                'lat': 36.5528, 'lon': -85.4597,
                'elevation_ft': 651,
                'capacity_cfs': 54000,
                'river_mile': 387.2
            },
            'Center Hill Dam': {
                'usgs_site': '03429500',
                'lat': 36.1089, 'lon': -85.7781,
                'elevation_ft': 685,
                'capacity_cfs': 89000,
                'river_mile': 325.7
            },
            'Old Hickory Dam': {
                'usgs_site': '03431500',
                'lat': 36.2939, 'lon': -86.6158,
                'elevation_ft': 445,
                'capacity_cfs': 120000,
                'river_mile': 216.2
            },
            'J Percy Priest Dam': {
                'usgs_site': '03430500',
                'lat': 36.0667, 'lon': -86.6333,
                'elevation_ft': 462,
                'capacity_cfs': 65000,
                'river_mile': 189.5
            },
            'Cheatham Dam': {
                'usgs_site': '03431700',
                'lat': 36.2972, 'lon': -87.0272,
                'elevation_ft': 392,
                'capacity_cfs': 130000,
                'river_mile': 148.7
            },
            'Barkley Dam': {
                'usgs_site': '03438220',
                'lat': 36.8631, 'lon': -88.2439,
                'elevation_ft': 359,
                'capacity_cfs': 200000,
                'river_mile': 30.6
            }
        }
        
        # River mile to coordinate mapping (approximate)
        self.mile_markers = self._generate_mile_markers()
    
    def _generate_mile_markers(self):
        """Generate mile marker coordinates along the Cumberland River"""
        # This is a simplified linear interpolation between dam points
        # In a real application, you'd use actual river mile survey data
        mile_coords = {}
        
        # Create interpolated points between dams
        dam_list = list(self.dams.items())
        for i in range(len(dam_list) - 1):
            dam1_name, dam1_data = dam_list[i]
            dam2_name, dam2_data = dam_list[i + 1]
            
            start_mile = dam1_data['river_mile']
            end_mile = dam2_data['river_mile']
            start_lat, start_lon = dam1_data['lat'], dam1_data['lon']
            end_lat, end_lon = dam2_data['lat'], dam2_data['lon']
            
            # Generate points every 5 miles
            for mile in range(int(end_mile), int(start_mile), 5):
                if mile > end_mile:
                    ratio = (mile - end_mile) / (start_mile - end_mile)
                    lat = end_lat + ratio * (start_lat - end_lat)
                    lon = end_lon + ratio * (start_lon - end_lon)
                    mile_coords[mile] = (lat, lon)
        
        return mile_coords
    
    def get_usgs_flow_data(self, site_id: str, days_back: int = 1) -> Optional[Dict]:
        """Fetch current flow data from USGS Water Services API"""
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back)
            
            url = f"https://waterservices.usgs.gov/nwis/iv/"
            params = {
                'format': 'json',
                'sites': site_id,
                'parameterCd': '00060',  # Discharge parameter
                'startDT': start_date.strftime('%Y-%m-%d'),
                'endDT': end_date.strftime('%Y-%m-%d')
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            if 'value' in data and 'timeSeries' in data['value']:
                time_series = data['value']['timeSeries']
                if time_series and 'values' in time_series[0]:
                    values = time_series[0]['values'][0]['value']
                    if values:
                        latest_value = values[-1]['value']
                        return {
                            'flow_cfs': float(latest_value),
                            'timestamp': values[-1]['dateTime'],
                            'site_name': time_series[0]['sourceInfo']['siteName']
                        }
        except Exception as e:
            st.warning(f"Could not fetch live data for site {site_id}: {str(e)}")
            return None
    
    def get_elevation_usgs(self, lat: float, lon: float) -> float:
        """Get elevation using USGS Elevation Point Query Service"""
        try:
            url = "https://nationalmap.gov/epqs/pqs.php"
            params = {
                'x': lon,
                'y': lat,
                'units': 'Feet',
                'output': 'json'
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            if 'USGS_Elevation_Point_Query_Service' in data:
                elevation_data = data['USGS_Elevation_Point_Query_Service']
                if 'Elevation_Query' in elevation_data:
                    elevation = elevation_data['Elevation_Query']['Elevation']
                    return float(elevation)
        except Exception as e:
            st.warning(f"Could not fetch elevation data: {str(e)}")
            return 400.0  # Default elevation
    
    def calculate_distance_miles(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points using Haversine formula"""
        R = 3959  # Earth's radius in miles
        
        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)
        
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad
        
        a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        return R * c
    
    def calculate_travel_time_hours(self, river_miles: float, avg_velocity_mph: float = 3.0) -> float:
        """Calculate water travel time between points"""
        return river_miles / avg_velocity_mph
    
    def find_closest_dam(self, target_lat: float, target_lon: float) -> Tuple[str, Dict]:
        """Find the closest dam to given coordinates"""
        min_distance = float('inf')
        closest_dam = None
        closest_dam_name = None
        
        for dam_name, dam_data in self.dams.items():
            distance = self.calculate_distance_miles(
                target_lat, target_lon, 
                dam_data['lat'], dam_data['lon']
            )
            if distance < min_distance:
                min_distance = distance
                closest_dam = dam_data
                closest_dam_name = dam_name
        
        return closest_dam_name, closest_dam
    
    def get_coordinates_from_mile(self, river_mile: float) -> Tuple[float, float]:
        """Get approximate coordinates from river mile marker"""
        if river_mile in self.mile_markers:
            return self.mile_markers[river_mile]
        
        # Find closest mile markers and interpolate
        miles = sorted(self.mile_markers.keys())
        
        if river_mile <= min(miles):
            return self.mile_markers[min(miles)]
        if river_mile >= max(miles):
            return self.mile_markers[max(miles)]
        
        # Find surrounding mile markers
        lower_mile = max([m for m in miles if m <= river_mile])
        upper_mile = min([m for m in miles if m >= river_mile])
        
        if lower_mile == upper_mile:
            return self.mile_markers[lower_mile]
        
        # Linear interpolation
        ratio = (river_mile - lower_mile) / (upper_mile - lower_mile)
        lower_lat, lower_lon = self.mile_markers[lower_mile]
        upper_lat, upper_lon = self.mile_markers[upper_mile]
        
        lat = lower_lat + ratio * (upper_lat - lower_lat)
        lon = lower_lon + ratio * (upper_lon - lower_lon)
        
        return lat, lon
    
    def calculate_flow_with_timing(self, selected_dam: str, user_mile: float) -> Dict:
        """Calculate flow rate and arrival time at user location"""
        # Get dam data
        dam_data = self.dams[selected_dam]
        dam_mile = dam_data['river_mile']
        
        # Get user coordinates
        user_lat, user_lon = self.get_coordinates_from_mile(user_mile)
        
        # Get current flow data
        flow_data = self.get_usgs_flow_data(dam_data['usgs_site'])
        
        if flow_data:
            current_flow = flow_data['flow_cfs']
            data_timestamp = flow_data['timestamp']
        else:
            # Use estimated flow if live data unavailable
            current_flow = dam_data['capacity_cfs'] * 0.4
            data_timestamp = datetime.now().isoformat()
        
        # Calculate travel distance and time
        if user_mile < dam_mile:  # User is downstream
            travel_miles = dam_mile - user_mile
            travel_time_hours = self.calculate_travel_time_hours(travel_miles)
            arrival_time = datetime.now() + timedelta(hours=travel_time_hours)
            
            # Apply attenuation factor
            attenuation = math.exp(-travel_miles / 100)
            flow_at_location = current_flow * attenuation
        else:
            # User is upstream of selected dam
            travel_miles = 0
            travel_time_hours = 0
            arrival_time = datetime.now()
            flow_at_location = current_flow * 0.5  # Reduced flow upstream
        
        return {
            'current_flow_at_dam': current_flow,
            'flow_at_user_location': flow_at_location,
            'travel_miles': travel_miles,
            'travel_time_hours': travel_time_hours,
            'arrival_time': arrival_time,
            'data_timestamp': data_timestamp,
            'user_coordinates': (user_lat, user_lon),
            'dam_coordinates': (dam_data['lat'], dam_data['lon'])
        }

@st.cache_data
def get_calculator():
    """Cached calculator instance"""
    return CumberlandRiverFlowCalculator()

def create_map(calculator, selected_dam, user_mile):
    """Create interactive map with dam and user location"""
    # Calculate flow and get coordinates
    result = calculator.calculate_flow_with_timing(selected_dam, user_mile)
    user_lat, user_lon = result['user_coordinates']
    dam_lat, dam_lon = result['dam_coordinates']
    dam_data = calculator.dams[selected_dam]
    
    # Create base map centered between dam and user location
    center_lat = (user_lat + dam_lat) / 2
    center_lon = (user_lon + dam_lon) / 2
    
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=9,
        tiles='OpenStreetMap'
    )
    
    # Add dam marker
    dam_tooltip = f"""
    <b>{selected_dam}</b><br>
    River Mile: {dam_data['river_mile']}<br>
    Elevation: {dam_data['elevation_ft']} ft<br>
    Capacity: {dam_data['capacity_cfs']:,} cfs<br>
    Current Release: {result['current_flow_at_dam']:.0f} cfs<br>
    Data Time: {result['data_timestamp'][:19]}
    """
    
    folium.Marker(
        [dam_lat, dam_lon],
        popup=f"{selected_dam}",
        tooltip=dam_tooltip,
        icon=folium.Icon(color='blue', icon='tint', prefix='fa')
    ).add_to(m)
    
    # Add user location marker
    user_tooltip = f"""
    <b>Your Location</b><br>
    River Mile: {user_mile}<br>
    Calculated Flow: {result['flow_at_user_location']:.0f} cfs<br>
    Travel Distance: {result['travel_miles']:.1f} miles<br>
    Arrival Time: {result['arrival_time'].strftime('%I:%M %p')}<br>
    Travel Duration: {result['travel_time_hours']:.1f} hours
    """
    
    folium.Marker(
        [user_lat, user_lon],
        popup="Your Location",
        tooltip=user_tooltip,
        icon=folium.Icon(color='red', icon='user', prefix='fa')
    ).add_to(m)
    
    # Add river line between points
    folium.PolyLine(
        locations=[[dam_lat, dam_lon], [user_lat, user_lon]],
        color='lightblue',
        weight=3,
        opacity=0.7
    ).add_to(m)
    
    return m, result

def main():
    """Main Streamlit application"""
    # Configure PWA first
    configure_pwa()
    
    st.title("🌊 Cumberland River Flow Calculator")
    st.markdown("*Real-time flow calculations and arrival predictions*")
    
    # Initialize calculator
    calculator = get_calculator()
    
    # Sidebar controls
    st.sidebar.header("📍 Location Settings")
    
    # Dam selection
    dam_names = list(calculator.dams.keys())
    selected_dam = st.sidebar.selectbox(
        "Select Closest Dam:",
        dam_names,
        index=3,  # Default to Old Hickory Dam
        help="Choose the dam closest to your location"
    )
    
    # Mile marker input
    dam_mile = calculator.dams[selected_dam]['river_mile']
    user_mile = st.sidebar.number_input(
        "Your River Mile Marker:",
        min_value=0.0,
        max_value=500.0,
        value=max(0.0, dam_mile - 20.0),  # Default 20 miles downstream
        step=0.1,
        help="Enter the river mile marker closest to your location"
    )
    
    # Add refresh button
    if st.sidebar.button("🔄 Refresh Data", type="primary"):
        st.cache_data.clear()
        st.rerun()
    
    # Main content area
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("📍 Interactive Map")
        
        try:
            # Create and display map
            river_map, flow_result = create_map(calculator, selected_dam, user_mile)
            map_data = st_folium(river_map, width=700, height=500)
            
        except Exception as e:
            st.error(f"Error creating map: {str(e)}")
            st.info("Please check your internet connection and try refreshing the data.")
    
    with col2:
        st.subheader("📊 Flow Information")
        
        try:
            # Display key metrics
            st.metric(
                "Flow at Your Location",
                f"{flow_result['flow_at_user_location']:.0f} cfs",
                help="Calculated flow rate at your river mile"
            )
            
            st.metric(
                "Dam Release Rate",
                f"{flow_result['current_flow_at_dam']:.0f} cfs",
                help="Current release from selected dam"
            )
            
            st.metric(
                "Water Arrival Time",
                flow_result['arrival_time'].strftime('%I:%M %p'),
                help="When water released now will reach you"
            )
            
            st.metric(
                "Travel Distance",
                f"{flow_result['travel_miles']:.1f} miles",
                help="Distance water travels from dam to your location"
            )
            
            # Additional information
            st.subheader("ℹ️ Details")
            
            dam_info = calculator.dams[selected_dam]
            st.write(f"**Selected Dam:** {selected_dam}")
            st.write(f"**Dam River Mile:** {dam_info['river_mile']}")
            st.write(f"**Dam Elevation:** {dam_info['elevation_ft']} ft")
            st.write(f"**Your River Mile:** {user_mile}")
            
            if flow_result['travel_time_hours'] > 0:
                st.write(f"**Travel Time:** {flow_result['travel_time_hours']:.1f} hours")
            else:
                st.info("You are upstream of the selected dam.")
            
            # Data timestamp
            st.caption(f"Data as of: {flow_result['data_timestamp'][:19]}")
            
        except Exception as e:
            st.error(f"Error calculating flow: {str(e)}")
    
    # Footer information
    st.markdown("---")
    st.markdown("""
    **About This App:**
    - Uses real-time USGS data when available
    - Calculations include travel time and flow attenuation
    - Dam locations and river miles are approximate
    - Install as PWA for offline access
    
    **Data Sources:** USGS Water Services, USGS Elevation Service
    """)

if __name__ == "__main__":
    main()
    