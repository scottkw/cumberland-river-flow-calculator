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
import os
import traceback

# Page configuration MUST be first
st.set_page_config(
    page_title="Cumberland River Flow Calculator",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Configure PWA
def configure_pwa():
    """Configure PWA using HTML meta tags and manifest"""
    wave_icon_svg = '''<svg width="192" height="192" viewBox="0 0 192 192" fill="none" xmlns="http://www.w3.org/2000/svg"><rect width="192" height="192" fill="#1f77b4" rx="24"/><g transform="translate(24, 48)"><path d="M0 32 Q36 16 72 32 T144 32 V96 H0 Z" fill="#ffffff" opacity="0.9"/><path d="M0 48 Q36 32 72 48 T144 48 V96 H0 Z" fill="#ffffff" opacity="0.7"/><path d="M0 64 Q36 48 72 64 T144 64 V96 H0 Z" fill="#ffffff" opacity="0.5"/></g></svg>'''
    
    import base64
    wave_icon_b64 = base64.b64encode(wave_icon_svg.encode('utf-8')).decode('utf-8')
    
    manifest = {
        "name": "Cumberland Flow Calculator",
        "short_name": "Cumberland Flow",
        "description": "Calculate Cumberland River flow rates at any location",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#1f77b4",
        "theme_color": "#1f77b4",
        "orientation": "portrait",
        "icons": [{"src": f"data:image/svg+xml;base64,{wave_icon_b64}", "sizes": "192x192", "type": "image/svg+xml", "purpose": "any maskable"}]
    }
    
    manifest_b64 = base64.b64encode(json.dumps(manifest).encode('utf-8')).decode('utf-8')
    pwa_html = f'<link rel="manifest" href="data:application/json;base64,{manifest_b64}"><meta name="theme-color" content="#1f77b4"><meta name="apple-mobile-web-app-capable" content="yes">'
    st.markdown(pwa_html, unsafe_allow_html=True)

class USGSApiClient:
    """Secure USGS API client"""
    
    def __init__(self):
        self._api_key = self._get_api_key()
        self._base_headers = {'User-Agent': 'Cumberland-River-Flow-Calculator/1.0', 'Accept': 'application/json'}
    
    def _get_api_key(self) -> str:
        api_key = os.environ.get('USGS_API_KEY')
        if api_key:
            return api_key
        try:
            if hasattr(st, 'secrets') and 'USGS_API_KEY' in st.secrets:
                return st.secrets['USGS_API_KEY']
        except:
            pass
        return "uit0NM8NFAPPW9jNDcIQHJpXHgGaih1Q697anjSy"
    
    def _make_request(self, url: str, params: dict, timeout: int = 10) -> Optional[requests.Response]:
        try:
            auth_params = params.copy()
            response = requests.get(url, params=auth_params, headers=self._base_headers, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 400:
                basic_params = {k: v for k, v in params.items() if k in ['format', 'sites', 'parameterCd', 'startDT', 'endDT', 'siteOutput']}
                try:
                    response = requests.get(url, params=basic_params, headers=self._base_headers, timeout=timeout)
                    response.raise_for_status()
                    return response
                except:
                    return None
            return None
        except:
            return None
    
    def get_site_info(self, site_id: str) -> Optional[Dict]:
        try:
            url = "https://waterservices.usgs.gov/nwis/iv/"
            params = {'format': 'json', 'sites': site_id, 'parameterCd': '00060', 'period': 'P1D'}
            response = self._make_request(url, params, timeout=15)
            if not response:
                return None
            data = response.json()
            if ('value' in data and 'timeSeries' in data['value'] and len(data['value']['timeSeries']) > 0):
                time_series = data['value']['timeSeries'][0]
                if 'sourceInfo' in time_series and 'siteName' in time_series['sourceInfo']:
                    return {'official_name': time_series['sourceInfo']['siteName']}
            return None
        except:
            return None
    
    def get_flow_data(self, site_id: str, days_back: int = 1) -> Optional[Dict]:
        try:
            url = "https://waterservices.usgs.gov/nwis/iv/"
            params = {'format': 'json', 'sites': site_id, 'parameterCd': '00060', 'period': 'P1D'}
            response = self._make_request(url, params, timeout=15)
            if not response:
                return None
            data = response.json()
            if ('value' in data and 'timeSeries' in data['value'] and len(data['value']['timeSeries']) > 0):
                time_series = data['value']['timeSeries'][0]
                if ('values' in time_series and len(time_series['values']) > 0 and
                    'value' in time_series['values'][0] and len(time_series['values'][0]['value']) > 0):
                    values = time_series['values'][0]['value']
                    latest_value = values[-1]
                    site_name = "Unknown Site"
                    if 'sourceInfo' in time_series and 'siteName' in time_series['sourceInfo']:
                        site_name = time_series['sourceInfo']['siteName']
                    return {'flow_cfs': float(latest_value['value']), 'timestamp': latest_value['dateTime'], 'site_name': site_name}
            return None
        except:
            return None

class CumberlandRiverFlowCalculator:
    """Calculate flow rates using river mile marker approach like the previous version"""
    
    def __init__(self):
        self.usgs_client = USGSApiClient()
        
        # Cumberland River major dams - using coordinates from the previous version
        self.dam_sites = {
            'Wolf Creek Dam': {'usgs_site': '03160000', 'capacity_cfs': 70000, 'river_mile': 460.9, 'lat': 36.8689, 'lon': -84.8353, 'elevation_ft': 760.0},
            'Dale Hollow Dam': {'usgs_site': '03141000', 'capacity_cfs': 54000, 'river_mile': 381.0, 'lat': 36.5384, 'lon': -85.4511, 'elevation_ft': 651.0},
            'Cordell Hull Dam': {'usgs_site': '03141500', 'capacity_cfs': 54000, 'river_mile': 313.5, 'lat': 36.2857, 'lon': -85.9513, 'elevation_ft': 585.0},
            'Old Hickory Dam': {'usgs_site': '03431500', 'capacity_cfs': 120000, 'river_mile': 216.2, 'lat': 36.2912, 'lon': -86.6515, 'elevation_ft': 445.0},
            'Cheatham Dam': {'usgs_site': '03431700', 'capacity_cfs': 130000, 'river_mile': 148.7, 'lat': 36.3089, 'lon': -87.1278, 'elevation_ft': 392.0},
            'Barkley Dam': {'usgs_site': '03438220', 'capacity_cfs': 200000, 'river_mile': 30.6, 'lat': 37.0646, 'lon': -88.0433, 'elevation_ft': 359.0}
        }
        
        self.dams = {}
        self.usgs_site_info_failed = False
        self.failed_site_count = 0
        self._initialize_dam_data()
        
        # Generate mile markers like the previous version
        self.mile_markers = self._generate_mile_markers()
    
    def _generate_mile_markers(self):
        """Generate mile marker coordinates along the Cumberland River - following the previous version exactly"""
        if not self.dams:
            return {}
            
        mile_coords = {}
        
        # Create interpolated points between dams - exactly like the previous version
        dam_list = sorted(self.dams.items(), key=lambda x: x[1]['river_mile'], reverse=True)
        
        for i in range(len(dam_list) - 1):
            dam1_name, dam1_data = dam_list[i]
            dam2_name, dam2_data = dam_list[i + 1]
            
            start_mile = dam1_data['river_mile']
            end_mile = dam2_data['river_mile']
            start_lat, start_lon = dam1_data['lat'], dam1_data['lon']
            end_lat, end_lon = dam2_data['lat'], dam2_data['lon']
            
            # Generate points every 5 miles like the previous version
            mile_range = range(int(end_mile), int(start_mile), 5)
            for mile in mile_range:
                if mile > end_mile:
                    ratio = (mile - end_mile) / (start_mile - end_mile)
                    lat = end_lat + ratio * (start_lat - end_lat)
                    lon = end_lon + ratio * (start_lon - end_lon)
                    mile_coords[mile] = (lat, lon)
        
        # Also add the dam coordinates themselves
        for dam_name, dam_data in self.dams.items():
            mile_coords[dam_data['river_mile']] = (dam_data['lat'], dam_data['lon'])
        
        return mile_coords
    
    def get_coordinates_from_mile(self, river_mile: float) -> Tuple[float, float]:
        """Get coordinates from river mile marker - same approach as previous version"""
        if river_mile in self.mile_markers:
            return self.mile_markers[river_mile]
        
        # Find closest mile markers and interpolate
        miles = sorted(self.mile_markers.keys())
        
        if not miles:
            # Fallback if no mile markers available
            return (36.1, -86.8)  # Approximate center of Cumberland River
        
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
            travel_time_hours = travel_miles / 3.0  # 3 mph average flow velocity
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
            'dam_coordinates': (dam_data['lat'], dam_data['lon']),
            'flow_data_available': flow_data is not None
        }
    
    def _initialize_dam_data(self):
        """Initialize dam data"""
        failed_sites = 0
        for dam_name, dam_info in self.dam_sites.items():
            self.dams[dam_name] = dam_info.copy()
            self.dams[dam_name]['official_name'] = dam_name
            
            site_info = self.usgs_client.get_site_info(dam_info['usgs_site'])
            if site_info and 'official_name' in site_info:
                self.dams[dam_name]['official_name'] = site_info['official_name']
            else:
                failed_sites += 1
        
        self.failed_site_count = failed_sites
        self.usgs_site_info_failed = failed_sites == len(self.dam_sites)
    
    def get_usgs_flow_data(self, site_id: str, days_back: int = 1) -> Optional[Dict]:
        """Fetch current flow data"""
        return self.usgs_client.get_flow_data(site_id, days_back)
    
    def calculate_distance_miles(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points"""
        R = 3959
        lat1_rad, lon1_rad = math.radians(lat1), math.radians(lon1)
        lat2_rad, lon2_rad = math.radians(lat2), math.radians(lon2)
        dlat, dlon = lat2_rad - lat1_rad, lon2_rad - lon1_rad
        a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
        return R * 2 * math.asin(math.sqrt(a))

@st.cache_resource
def get_calculator():
    """Get calculator instance"""
    return CumberlandRiverFlowCalculator()

def create_map(calculator, selected_dam, user_mile):
    """Create map with individual mile markers and connecting lines - river mile input version"""
    
    # Calculate miles from dam for visualization
    dam_data = calculator.dams[selected_dam]
    dam_mile = dam_data['river_mile']
    miles_from_dam = dam_mile - user_mile if user_mile < dam_mile else 0
    
    # Calculate flow and get coordinates
    result = calculator.calculate_flow_with_timing(selected_dam, user_mile)
    user_lat, user_lon = result['user_coordinates']
    dam_lat, dam_lon = result['dam_coordinates']
    
    # Create base map centered between dam and user location
    center_lat = (user_lat + dam_lat) / 2
    center_lon = (user_lon + dam_lon) / 2
    
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=9,
        tiles='OpenStreetMap'
    )
    
    # Add dam marker
    dam_tooltip = f"""<b>{selected_dam}</b><br>Official Name: {dam_data.get('official_name', 'N/A')}<br>River Mile: {dam_data['river_mile']}<br>Elevation: {dam_data['elevation_ft']:.0f} ft<br>Capacity: {dam_data['capacity_cfs']:,} cfs<br>Current Release: {result['current_flow_at_dam']:.0f} cfs<br>Data Time: {result['data_timestamp'][:19]}"""
    
    folium.Marker(
        [dam_lat, dam_lon],
        popup=f"{selected_dam}",
        tooltip=dam_tooltip,
        icon=folium.Icon(color='blue', icon='tint', prefix='fa')
    ).add_to(m)
    
    # Add user location marker
    user_tooltip = f"""<b>Your Location</b><br>River Mile: {user_mile:.1f}<br>Miles from Dam: {miles_from_dam:.1f}<br>Calculated Flow: {result['flow_at_user_location']:.0f} cfs<br>Travel Distance: {result['travel_miles']:.1f} miles<br>Arrival Time: {result['arrival_time'].strftime('%I:%M %p')}<br>Travel Duration: {result['travel_time_hours']:.1f} hours"""
    
    folium.Marker(
        [user_lat, user_lon],
        popup="Your Location",
        tooltip=user_tooltip,
        icon=folium.Icon(color='red', icon='user', prefix='fa')
    ).add_to(m)
    
    # ADD INDIVIDUAL MILE MARKERS WITH CONNECTING LINES
    # Generate coordinates for each mile from dam to user location
    path_coordinates = []
    path_coordinates.append((dam_lat, dam_lon))  # Start at dam
    
    # Add intermediate mile markers (every mile)
    if miles_from_dam > 0:
        for i in range(1, int(miles_from_dam) + 1):
            intermediate_mile = dam_mile - i  # River mile decreases downstream
            if intermediate_mile >= user_mile:
                # Get coordinates for this mile marker
                intermediate_lat, intermediate_lon = calculator.get_coordinates_from_mile(intermediate_mile)
                path_coordinates.append((intermediate_lat, intermediate_lon))
                
                # Add a small marker for this mile
                if i % 5 == 0 or miles_from_dam <= 10:  # Show marker every 5 miles, or all if short distance
                    folium.CircleMarker(
                        [intermediate_lat, intermediate_lon],
                        radius=3,
                        popup=f"River Mile {intermediate_mile:.1f}<br>{i} miles from dam",
                        color='green',
                        fill=True,
                        fillColor='lightgreen',
                        fillOpacity=0.7
                    ).add_to(m)
    
    # Add final user location to path
    path_coordinates.append((user_lat, user_lon))
    
    # Draw connecting lines between all mile markers
    if len(path_coordinates) > 1:
        folium.PolyLine(
            locations=path_coordinates,
            color='darkblue',
            weight=4,
            opacity=0.8,
            popup=f"River path: {miles_from_dam:.1f} miles from {selected_dam}<br>From Mile {dam_mile} to Mile {user_mile:.1f}"
        ).add_to(m)
    
    return m, result

def main():
    """Main application - using river mile marker input like the previous version"""
    configure_pwa()
    
    st.title("🌊 Cumberland River Flow Calculator")
    st.markdown("*Real-time flow calculations using river mile markers*")
    
    # Initialize calculator
    if 'calculator' not in st.session_state:
        with st.spinner("Loading dam information..."):
            try:
                st.session_state.calculator = get_calculator()
            except Exception as e:
                st.error(f"Failed to initialize: {str(e)}")
                st.stop()
    
    calculator = st.session_state.calculator
    
    if not calculator or not calculator.dams:
        st.error("❌ Unable to load dam data. Please refresh.")
        if st.button("🔄 Retry"):
            if 'calculator' in st.session_state:
                del st.session_state.calculator
            st.cache_resource.clear()
            st.rerun()
        return

    # Sidebar controls - river mile marker input with mile-by-mile visualization
    st.sidebar.header("📍 Location Settings")
    
    # Dam selection
    dam_names = list(calculator.dams.keys())
    selected_dam = st.sidebar.selectbox(
        "Select Closest Dam:",
        dam_names,
        index=3 if len(dam_names) > 3 else 0,  # Default to Old Hickory Dam
        help="Choose the dam closest to your location"
    )
    
    # River mile marker input
    dam_mile = calculator.dams[selected_dam]['river_mile']
    user_mile = st.sidebar.number_input(
        "Your River Mile Marker:",
        min_value=0.0,
        max_value=500.0,
        value=max(0.0, dam_mile - 20.0),  # Default 20 miles downstream
        step=0.1,
        help="Enter the river mile marker closest to your location"
    )
    
    # Calculate miles from dam for visualization
    miles_from_dam = dam_mile - user_mile if user_mile < dam_mile else 0
    
    if st.sidebar.button("🔄 Refresh Data", type="primary"):
        st.cache_resource.clear()
        if 'calculator' in st.session_state:
            del st.session_state.calculator
        st.rerun()
    
    # Data status
    st.sidebar.markdown("---")
    st.sidebar.subheader("📊 Data Status")
    
    if calculator.usgs_site_info_failed:
        st.sidebar.warning("⚠️ Using stored dam names")
    else:
        success_rate = len(calculator.dam_sites) - calculator.failed_site_count
        st.sidebar.success(f"✅ Dam info loaded ({success_rate}/{len(calculator.dam_sites)})")
    
    # Check flow data
    dam_data = calculator.dams[selected_dam]
    flow_data = None
    try:
        flow_data = calculator.get_usgs_flow_data(dam_data['usgs_site'])
    except:
        pass
    
    if flow_data:
        st.sidebar.success("✅ Live flow data available")
        st.sidebar.caption(f"Updated: {flow_data['timestamp'][:19]}")
    else:
        st.sidebar.info("📊 Using estimated flow data")
    
    st.sidebar.markdown("---")
    st.sidebar.info("📍 **River Mile Markers:** Enter your mile marker position!")
    
    # Main content
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("📍 Interactive Map")
        
        try:
            river_map, flow_result = create_map(calculator, selected_dam, user_mile)
            st_folium(river_map, width=700, height=500, key=f"river_map_{selected_dam}_{user_mile}")
            
        except Exception as e:
            st.error(f"🗺️ Map error: {str(e)}")
            # Fallback calculation
            try:
                flow_result = calculator.calculate_flow_with_timing(selected_dam, user_mile)
            except Exception as calc_error:
                st.error(f"Calculation error: {str(calc_error)}")
                return
    
    with col2:
        st.subheader("📊 Flow Information")
        
        try:
            st.metric("💧 Flow at Your Location", f"{flow_result['flow_at_user_location']:.0f} cfs", help="Calculated flow rate at your river mile")
            st.metric("🏭 Dam Release Rate", f"{flow_result['current_flow_at_dam']:.0f} cfs", help="Current release from selected dam")
            st.metric("⏰ Water Arrival Time", flow_result['arrival_time'].strftime('%I:%M %p'), help="When water released now will reach you")
            st.metric("📏 Travel Distance", f"{flow_result['travel_miles']:.1f} miles", help="Distance water travels from dam to your location")
            
            if flow_result['flow_data_available']:
                st.success("🎯 Using live USGS data")
            else:
                st.warning("📊 Using estimated data")
            
            # Details
            st.subheader("ℹ️ Details")
            dam_info = calculator.dams[selected_dam]
            st.write(f"**Selected Dam:** {selected_dam}")
            st.write(f"**Official Name:** {dam_info.get('official_name', 'N/A')}")
            st.write(f"**Dam River Mile:** {dam_info['river_mile']}")
            st.write(f"**Your River Mile:** {user_mile:.1f}")
            st.write(f"**Miles from Dam:** {miles_from_dam:.1f}")
            st.write(f"**Dam Coordinates:** {dam_info['lat']:.4f}, {dam_info['lon']:.4f}")
            st.write(f"**Your Coordinates:** {flow_result['user_coordinates'][0]:.4f}, {flow_result['user_coordinates'][1]:.4f}")
            
            if flow_result['travel_time_hours'] > 0:
                st.write(f"**Travel Time:** {flow_result['travel_time_hours']:.1f} hours")
                st.write(f"**Average Flow Velocity:** ~3.0 mph")
            else:
                st.info("🎯 You are upstream of the selected dam.")
            
            if flow_result['flow_data_available']:
                st.caption(f"🔐 Live USGS data: {flow_result['data_timestamp'][:19]}")
            else:
                st.caption(f"📊 Estimated data: {flow_result['data_timestamp'][:19]}")
            
        except Exception as e:
            st.error(f"🔢 Error: {str(e)}")
    
    # Footer
    st.markdown("---")
    st.markdown("""
    **🌊 River Mile Marker Cumberland River Flow Calculator:**
    - **Input Method:** Enter your river mile marker position (not distance from dam)
    - **Mile Marker System:** Uses standard Cumberland River mile markers (Mile 0 = mouth, Mile 460+ = headwaters)
    - **Interpolation:** Calculates coordinates between known mile markers
    - **Flow Calculations:** Based on travel distance between dam and your mile marker
    - Uses real-time USGS flow data when available
    - Includes travel time calculations and flow attenuation
    
    **📍 How to Use:**
    1. Select the dam closest to your location
    2. Enter the river mile marker where you are located
    3. View flow calculations and arrival predictions
    
    **🔍 Data Sources:** USGS Water Services API, Army Corps of Engineers Dam Data
    """)

if __name__ == "__main__":
    main()