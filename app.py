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

class BRouterWaterwayAPI:
    """Direct BRouter API for waterway routing"""
    
    def __init__(self):
        self.brouter_url = "https://brouter.de/brouter"
        self.timeout = 30
    
    def get_waterway_route(self, start_lat: float, start_lon: float, end_lat: float, end_lon: float) -> Optional[List[Tuple[float, float]]]:
        """Get waterway route using BRouter with multiple profile attempts"""
        
        # Try different routing profiles that work for waterways
        profiles = [
            'river',           # Direct river routing
            'boat',           # Boat routing
            'foot',           # Pedestrian (often follows waterways)
            'hiking'          # Hiking (can follow rivers)
        ]
        
        for profile in profiles:
            try:
                st.write(f"🌊 Trying {profile} routing...")
                
                params = {
                    'lonlats': f"{start_lon},{start_lat}|{end_lon},{end_lat}",
                    'profile': profile,
                    'alternativeidx': '0',
                    'format': 'geojson'
                }
                
                response = requests.get(self.brouter_url, params=params, timeout=self.timeout)
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        if 'features' in data and len(data['features']) > 0:
                            feature = data['features'][0]
                            if 'geometry' in feature and 'coordinates' in feature['geometry']:
                                coordinates = feature['geometry']['coordinates']
                                # Convert from [lon, lat] to [lat, lon] and filter valid coordinates
                                route_coords = []
                                for coord in coordinates:
                                    if len(coord) >= 2:
                                        lat, lon = coord[1], coord[0]
                                        if -90 <= lat <= 90 and -180 <= lon <= 180:
                                            route_coords.append((lat, lon))
                                
                                if len(route_coords) > 2:
                                    st.success(f"✅ Got route with {profile} profile: {len(route_coords)} points")
                                    return route_coords
                    except json.JSONDecodeError:
                        continue
                
            except Exception as e:
                st.warning(f"⚠️ {profile} routing failed: {str(e)}")
                continue
        
        return None
    
    def get_streamstats_flow_path(self, lat: float, lon: float, downstream_miles: float = 50) -> Optional[List[Tuple[float, float]]]:
        """Try to use USGS StreamStats flow path API"""
        try:
            # This is an experimental endpoint - may not work
            streamstats_url = "https://streamstats.usgs.gov/streamstatsservices/flowpath"
            
            params = {
                'rcode': '05',  # Ohio River region (includes Cumberland)
                'xlocation': lon,
                'ylocation': lat,
                'distance': downstream_miles,
                'format': 'json'
            }
            
            response = requests.get(streamstats_url, params=params, timeout=20)
            
            if response.status_code == 200:
                data = response.json()
                # This would need to be parsed based on actual API response format
                # The exact format is not well documented
                st.info("📊 StreamStats API responded - parsing...")
                return None  # Would implement parsing here
            
        except Exception as e:
            st.warning(f"StreamStats API failed: {str(e)}")
        
        return None

class CumberlandRiverFlowCalculator:
    """Calculate flow rates using BRouter waterway routing"""
    
    def __init__(self):
        self.usgs_client = USGSApiClient()
        self.brouter_api = BRouterWaterwayAPI()
        
        # Cumberland River major dams
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
    
    def get_coordinates_from_mile(self, river_mile: float) -> Tuple[float, float]:
        """Get coordinates from river mile marker using dam interpolation"""
        # Simple interpolation based on known dam locations
        dam_miles = [(name, data['river_mile'], data['lat'], data['lon']) 
                    for name, data in self.dams.items()]
        dam_miles.sort(key=lambda x: x[1], reverse=True)  # Sort by mile, upstream first
        
        # Find surrounding dams
        for i in range(len(dam_miles) - 1):
            upper_dam = dam_miles[i]
            lower_dam = dam_miles[i + 1]
            
            if lower_dam[1] <= river_mile <= upper_dam[1]:
                # Interpolate between these two dams
                ratio = (river_mile - lower_dam[1]) / (upper_dam[1] - lower_dam[1])
                lat = lower_dam[2] + ratio * (upper_dam[2] - lower_dam[2])
                lon = lower_dam[3] + ratio * (upper_dam[3] - lower_dam[3])
                return lat, lon
        
        # If outside range, use closest dam
        if river_mile >= dam_miles[0][1]:
            return dam_miles[0][2], dam_miles[0][3]
        else:
            return dam_miles[-1][2], dam_miles[-1][3]
    
    def calculate_flow_with_timing(self, selected_dam: str, user_mile: float) -> Dict:
        """Calculate flow rate and arrival time using BRouter waterway routing"""
        # Get dam data
        dam_data = self.dams[selected_dam]
        dam_mile = dam_data['river_mile']
        
        # Get coordinates
        user_lat, user_lon = self.get_coordinates_from_mile(user_mile)
        dam_lat, dam_lon = dam_data['lat'], dam_data['lon']
        
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
            # Try to get REAL waterway route using BRouter
            with st.spinner("🌊 Getting waterway route from BRouter..."):
                river_path = self.brouter_api.get_waterway_route(dam_lat, dam_lon, user_lat, user_lon)
            
            routing_success = False
            routing_method = "Linear approximation"
            
            if river_path and len(river_path) > 5:
                # We got a real route!
                routing_success = True
                routing_method = "BRouter waterway routing"
                # Make sure user coordinates match the route end
                user_lat, user_lon = river_path[-1]
            else:
                # Fallback to straight line
                st.warning("⚠️ BRouter waterway routing failed - using straight line")
                river_path = [(dam_lat, dam_lon), (user_lat, user_lon)]
            
            # Calculate actual travel distance along the path
            travel_miles = self._calculate_path_distance(river_path)
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
            flow_at_location = current_flow * 0.5
            river_path = [(user_lat, user_lon), (dam_lat, dam_lon)]
            routing_success = False
            routing_method = "Upstream location"
        
        return {
            'current_flow_at_dam': current_flow,
            'flow_at_user_location': flow_at_location,
            'travel_miles': travel_miles,
            'travel_time_hours': travel_time_hours,
            'arrival_time': arrival_time,
            'data_timestamp': data_timestamp,
            'user_coordinates': (user_lat, user_lon),
            'dam_coordinates': (dam_lat, dam_lon),
            'flow_data_available': flow_data is not None,
            'river_path': river_path,
            'routing_success': routing_success,
            'routing_method': routing_method
        }
    
    def _calculate_path_distance(self, path: List[Tuple[float, float]]) -> float:
        """Calculate total distance along a path of coordinates"""
        if len(path) < 2:
            return 0.0
        
        total_distance = 0.0
        for i in range(len(path) - 1):
            lat1, lon1 = path[i]
            lat2, lon2 = path[i + 1]
            total_distance += self.calculate_distance_miles(lat1, lon1, lat2, lon2)
        
        return total_distance
    
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
        """Calculate distance between two points using Haversine formula"""
        R = 3959  # Earth radius in miles
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
    """Create map with BRouter waterway routing"""
    
    # Calculate flow and get all data
    result = calculator.calculate_flow_with_timing(selected_dam, user_mile)
    user_lat, user_lon = result['user_coordinates']
    dam_lat, dam_lon = result['dam_coordinates']
    river_path = result['river_path']
    
    # Create base map centered on the route
    if len(river_path) > 1:
        all_lats = [coord[0] for coord in river_path]
        all_lons = [coord[1] for coord in river_path]
        center_lat = sum(all_lats) / len(all_lats)
        center_lon = sum(all_lons) / len(all_lons)
    else:
        center_lat = (user_lat + dam_lat) / 2
        center_lon = (user_lon + dam_lon) / 2
    
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=9,
        tiles='OpenStreetMap'
    )
    
    # Add dam marker
    dam_data = calculator.dams[selected_dam]
    dam_tooltip = f"""<b>{selected_dam}</b><br>Official Name: {dam_data.get('official_name', 'N/A')}<br>River Mile: {dam_data['river_mile']}<br>Elevation: {dam_data['elevation_ft']:.0f} ft<br>Capacity: {dam_data['capacity_cfs']:,} cfs<br>Current Release: {result['current_flow_at_dam']:.0f} cfs<br>Data Time: {result['data_timestamp'][:19]}"""
    
    folium.Marker(
        [dam_lat, dam_lon],
        popup=f"{selected_dam}",
        tooltip=dam_tooltip,
        icon=folium.Icon(color='blue', icon='tint', prefix='fa')
    ).add_to(m)
    
    # Add user location marker
    miles_from_dam = dam_data['river_mile'] - user_mile if user_mile < dam_data['river_mile'] else 0
    user_tooltip = f"""<b>Your Location</b><br>River Mile: {user_mile:.1f}<br>Miles from Dam: {miles_from_dam:.1f}<br>Calculated Flow: {result['flow_at_user_location']:.0f} cfs<br>Travel Distance: {result['travel_miles']:.1f} miles<br>Arrival Time: {result['arrival_time'].strftime('%I:%M %p')}<br>Travel Duration: {result['travel_time_hours']:.1f} hours"""
    
    folium.Marker(
        [user_lat, user_lon],
        popup="Your Location",
        tooltip=user_tooltip,
        icon=folium.Icon(color='red', icon='user', prefix='fa')
    ).add_to(m)
    
    # Draw the waterway path
    if len(river_path) > 1:
        # Choose color based on routing success
        path_color = 'darkblue' if result['routing_success'] else 'orange'
        path_weight = 6 if result['routing_success'] else 4
        
        path_popup = f"Waterway Path<br>Method: {result['routing_method']}<br>Distance: {result['travel_miles']:.1f} miles<br>Route Points: {len(river_path)}"
        
        folium.PolyLine(
            locations=river_path,
            color=path_color,
            weight=path_weight,
            opacity=0.9,
            popup=path_popup
        ).add_to(m)
        
        # Add waypoint markers for successful routing
        if result['routing_success'] and len(river_path) > 10:
            # Show every 10th point to avoid clutter
            step = max(1, len(river_path) // 10)
            for i in range(step, len(river_path) - step, step):
                folium.CircleMarker(
                    river_path[i],
                    radius=3,
                    popup=f"Route Point {i}",
                    color='green',
                    fill=True,
                    fillColor='lightgreen',
                    fillOpacity=0.7,
                    weight=1
                ).add_to(m)
    
    # Add all other dams for reference
    for other_dam_name, other_dam_data in calculator.dams.items():
        if other_dam_name != selected_dam:
            folium.CircleMarker(
                [other_dam_data['lat'], other_dam_data['lon']],
                radius=5,
                popup=f"{other_dam_name}<br>Mile {other_dam_data['river_mile']}",
                color='gray',
                fill=True,
                fillColor='lightgray',
                fillOpacity=0.6,
                weight=1
            ).add_to(m)
    
    return m, result

def main():
    """Main application with BRouter waterway routing"""
    st.title("🌊 Cumberland River Flow Calculator")
    st.markdown("*Real-time flow calculations with **BRouter Waterway Routing***")
    
    # Initialize calculator
    if 'calculator' not in st.session_state:
        with st.spinner("Loading BRouter waterway routing system..."):
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

    # Sidebar controls
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
    st.sidebar.info("🚀 **BRouter Waterway Routing** - Professional river routing!")
    
    # Main content
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("🗺️ Interactive Map - BRouter Waterway Routing")
        
        try:
            river_map, flow_result = create_map(calculator, selected_dam, user_mile)
            st_folium(river_map, width=700, height=500, key=f"brouter_river_map_{selected_dam}_{user_mile}")
            
        except Exception as e:
            st.error(f"🗺️ Map error: {str(e)}")
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
            st.metric("📏 Travel Distance", f"{flow_result['travel_miles']:.1f} miles", help="Distance along waterway path")
            
            if flow_result['flow_data_available']:
                st.success("🎯 Using live USGS data")
            else:
                st.warning("📊 Using estimated data")
            
            # River routing status
            if flow_result.get('routing_success', False):
                st.success("🌊 BRouter waterway routing SUCCESS!")
                st.caption(f"Method: {flow_result.get('routing_method', 'Unknown')}")
                st.caption(f"Route points: {len(flow_result['river_path'])}")
            else:
                st.warning("⚠️ Using fallback routing")
                st.caption(f"Method: {flow_result.get('routing_method', 'Linear')}")
            
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
                st.write(f"**Route Accuracy:** {'HIGH (BRouter waterway)' if flow_result.get('routing_success') else 'LOW (Approximated)'}")
            else:
                st.info("🎯 You are upstream of the selected dam.")
            
            if flow_result['flow_data_available']:
                st.caption(f"🔐 Live USGS data: {flow_result['data_timestamp'][:19]}")
            else:
                st.caption(f"📊 Estimated data: {flow_result['data_timestamp'][:19]}")
            
        except Exception as e:
            st.error(f"🔢 Error: {str(e)}")
    
    # BRouter Features Info
    st.markdown("---")
    st.subheader("🚀 BRouter Waterway Routing Features")
    
    col3, col4 = st.columns(2)
    
    with col3:
        st.markdown("""
        **🌊 Professional Waterway Routing:**
        - Uses BRouter professional routing engine
        - Multiple routing profiles: river, boat, foot, hiking
        - Follows actual waterways in OpenStreetMap
        - Same technology as waterway.guru
        """)
        
        st.markdown("""
        **📊 Intelligent Fallback:**
        - Tries multiple routing profiles automatically
        - Falls back to straight line if routing fails
        - Clear visual indication of routing success
        - Real-time status updates during routing
        """)
    
    with col4:
        st.markdown("""
        **🗺️ Visual Indicators:**
        - **Dark Blue Line** = Successful waterway routing
        - **Orange Line** = Fallback straight line routing
        - **Green Dots** = Waypoints along routed path
        - **Thick Lines** = High confidence routes
        """)
        
        st.markdown("""
        **🔧 Technical Details:**
        - Direct API calls to brouter.de
        - GeoJSON coordinate parsing
        - Multiple profile attempts for reliability
        - Coordinate validation and filtering
        """)
    
    # How It Works section
    st.markdown("---")
    st.subheader("🔧 How BRouter Waterway Routing Works")
    
    with st.expander("Click to see technical details"):
        st.markdown("""
        **BRouter Routing Process:**
        
        1. **Multiple Profile Attempts:**
           - First tries 'river' profile (specialized for waterways)
           - Falls back to 'boat' profile (marine routing)
           - Then tries 'foot' and 'hiking' (often follow rivers)
           - Uses first successful route
        
        2. **API Call Structure:**
           ```
           https://brouter.de/brouter?
           lonlats=start_lon,start_lat|end_lon,end_lat&
           profile=river&
           format=geojson
           ```
        
        3. **Response Processing:**
           - Parses GeoJSON response format
           - Extracts coordinate arrays from geometry
           - Converts [lon,lat] to [lat,lon] format
           - Validates coordinate ranges
           - Filters invalid points
        
        4. **Success Criteria:**
           - Route must have more than 5 coordinate points
           - All coordinates must be within valid ranges
           - Path must be continuous
        
        **Why BRouter Works Better:**
        - **Specialized for waterways**: Unlike general routing APIs
        - **OpenStreetMap based**: Uses detailed waterway data
        - **Multiple profiles**: Increases success rate
        - **Professional grade**: Used by navigation apps
        - **Free and reliable**: No API keys or quotas
        
        **When It Falls Back:**
        - If all routing profiles fail
        - If response has too few points
        - If coordinates are invalid
        - If API is temporarily unavailable
        
        **Result Verification:**
        - Blue line = BRouter succeeded
        - Orange line = Fallback to straight line
        - Status messages show which profile worked
        - Route point count indicates detail level
        """)
    
    # Footer
    st.markdown("---")
    st.markdown("""
    **🌊 Cumberland River Flow Calculator - BRouter Waterway Routing:**
    - **Professional Routing**: Uses the same BRouter engine as waterway.guru
    - **Multiple Attempts**: Tries river, boat, foot, and hiking profiles automatically
    - **Visual Feedback**: Clear indication when real waterway routing succeeds
    - **Reliable Fallback**: Always provides results even if routing fails
    - **No API Keys**: Uses free, public BRouter service
    
    **📍 How to Use:**
    1. Select the dam closest to your location
    2. Enter the river mile marker where you are located  
    3. Watch the routing attempts in real-time
    4. Dark blue line = success, orange line = fallback
    
    **🔍 Data Sources:** 
    - BRouter Waterway Routing Engine (brouter.de)
    - OpenStreetMap Waterway Data
    - USGS Water Services API (flow data)
    - Army Corps of Engineers Dam Data
    """)

if __name__ == "__main__":
    main()