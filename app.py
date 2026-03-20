from flask import Flask, request, jsonify
import requests
import icalendar
import os 
from icalendar import Calendar
app = Flask(__name__)

@app.route('/', methods=['GET'])
def home():
    return "Python API is running!"

@app.route('/parse', methods=['POST'])
def parse_ical():
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({"error": "No URL provided"}), 400
        
    url = data['url']
    all_events = []
    
    try:
        response = requests.get(url)
        cal = icalendar.Calendar.from_ical(response.content)
        
        for component in cal.walk():
            if component.name == "VEVENT":
                raw_start = component.get('dtstart').dt
                raw_end = component.get('dtend').dt
                

                duration_delta = raw_end - raw_start
                duration_mins = int(duration_delta.total_seconds() / 60)

                start = raw_start.strftime('%Y-%m-%d %H:%M:%S')


                raw_description = str(component.get('description', ''))
                event_details = {}
                
                for line in raw_description.splitlines():
                    if not line.strip():
                        continue
                    if ':' in line:
                        key, value = line.split(':', 1)
                        event_details[key.strip()] = value.strip()

                event_data = {
                    'event_type': event_details.get('Event type', 'Unknown'),
                    'description': event_details.get('Description', 'Unknown'),
                    'location': event_details.get('Location', 'Unknown'),
                    'staff': event_details.get('Staff Member', 'Unknown'),
                    'unit_code': event_details.get('Unit Code', 'Unknown'),
                    'directions': event_details.get('Directions', 'Unknown'),
                    'duration': duration_mins,
                    'start': start
                }
                all_events.append(event_data)
                

        return jsonify(all_events)

    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route('/get_commute', methods=['POST'])
def get_commute():
    data = request.get_json()
    
    home_postcode = data.get('home_postcode')
    event_location = data.get('event_location')
    transport_mode = data.get('transport_mode', 'foot-walking') 
    
    ors_key = os.environ.get("ORS_API_KEY")

    if not ors_key:
        return jsonify({"error": "Missing ORS Key"}), 500

    #Convert text to GPS coordinates
    # Helper function: Convert text to GPS coordinates
    def get_coords(location_text):
        # 1. Force it to look in Manchester
        search_query = f"{location_text}, Manchester"
        
        # 2. STRICT RULE: boundary.country=GB means it literally cannot search outside the UK
        url = f"https://api.openrouteservice.org/geocode/search?api_key={ors_key}&text={search_query}&boundary.country=GB"
        
        res = requests.get(url)
        if res.status_code == 200 and len(res.json().get('features', [])) > 0:
            return res.json()['features'][0]['geometry']['coordinates'] # Returns [Longitude, Latitude]
        return None

    home_coords = get_coords(home_postcode)
    event_coords = get_coords(event_location)

    if not home_coords or not event_coords:
        return jsonify({"error": f"Could not find coordinates. Home: {home_coords}, Event: {event_coords}"}), 404

    # The Math Hack Route (Public Transport)
    if transport_mode == 'public_transport':
        start_str = f"{home_coords[0]},{home_coords[1]}"
        end_str = f"{event_coords[0]},{event_coords[1]}"
        
        route_url = f"https://api.openrouteservice.org/v2/directions/driving-car?api_key={ors_key}&start={start_str}&end={end_str}"
        
        route_res = requests.get(route_url)
        if route_res.status_code == 200:
            duration_seconds = route_res.json()['features'][0]['properties']['summary']['duration']
            car_minutes = duration_seconds / 60
            bus_minutes = round((car_minutes * 1.5) + 5)
            
            return jsonify({
                "success": True, 
                "commute_minutes": bus_minutes, 
                "mode": "public_transport"
            }), 200
        else:
            # THIS IS THE NEW FIX: Print the exact ORS error!
            return jsonify({"error": f"ORS Driving Route Error: {route_res.text}"}), 500

    # The Standard Route
    else:
        start_str = f"{home_coords[0]},{home_coords[1]}"
        end_str = f"{event_coords[0]},{event_coords[1]}"
        
        route_url = f"https://api.openrouteservice.org/v2/directions/{transport_mode}?api_key={ors_key}&start={start_str}&end={end_str}"
        
        route_res = requests.get(route_url)
        if route_res.status_code == 200:
            duration_seconds = route_res.json()['features'][0]['properties']['summary']['duration']
            duration_minutes = round(duration_seconds / 60)
            
            return jsonify({
                "success": True, 
                "commute_minutes": duration_minutes, 
                "mode": transport_mode
            }), 200
        else:
            # THIS IS THE NEW FIX: Print the exact ORS error!
            return jsonify({"error": f"ORS Standard Route Error: {route_res.text}"}), 500


@app.route('/parse_canvas', methods=['POST'])
def parse_canvas():
    data = request.get_json()
    canvas_url = data.get('canvas_url')

    if not canvas_url:
        return jsonify({"error": "No Canvas URL provided"}), 400

    try:
        response = requests.get(canvas_url)
        if response.status_code != 200:
            return jsonify({"error": "Failed to download Canvas calendar"}), 400

        cal = Calendar.from_ical(response.content)
        deadlines = []

        for component in cal.walk('vevent'):
            # Safely grab the title
            title = str(component.get('summary', 'Unknown Assignment'))
            
            # THE FIX: Safely try to get the End Date. If it's missing, grab the Start Date.
            date_item = component.get('dtend') or component.get('dtstart')
            
            # If this weird event literally has no date attached to it at all, skip it entirely!
            if not date_item or not hasattr(date_item, 'dt'):
                continue
                
            due_date = date_item.dt
            
            # THE SECOND FIX: Canvas sometimes sends "All Day" events as pure Dates, 
            # instead of DateTimes. We need to format them perfectly for your SQL database.
            if type(due_date).__name__ == 'date':
                formatted_date = due_date.strftime('%Y-%m-%d 23:59:59') # Assume 11:59 PM
            else:
                formatted_date = due_date.strftime('%Y-%m-%d %H:%M:%S')

            deadlines.append({
                "title": title,
                "due_date": formatted_date,
                "status": "pending"
            })

        return jsonify({
            "success": True, 
            "total_deadlines": len(deadlines),
            "deadlines": deadlines
        }), 200

    except Exception as e:
        print(f"🛑 CANVAS PARSE ERROR: {str(e)}")
        return jsonify({"error": f"Failed to parse Canvas feed: {str(e)}"}), 500
    
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)