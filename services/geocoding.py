import requests


def reverse_geocode(lat, lng):
    """
    Convert lat/lng to a human-readable address using OpenStreetMap Nominatim.
    Always returns a Google Maps link as fallback even if geocoding fails.
    """
    try:
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {"lat": lat, "lon": lng, "format": "json"}
        headers = {"User-Agent": "HeartAttackAlertSystem/1.0"}

        response = requests.get(url, params=params, headers=headers, timeout=5)
        data = response.json()

        address = data.get("display_name", "Address unavailable")
        maps_link = f"https://www.google.com/maps?q={lat},{lng}"

        return {
            "address": address,
            "maps_link": maps_link,
            "lat": lat,
            "lng": lng
        }

    except Exception:
        # Even if Nominatim fails, the Maps link always works in an emergency
        return {
            "address": "Location lookup failed",
            "maps_link": f"https://www.google.com/maps?q={lat},{lng}",
            "lat": lat,
            "lng": lng
        }