from flask import Flask, request, jsonify
import requests
import icalendar

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)