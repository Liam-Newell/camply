import requests
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
headers = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}

params = {
    "mapId": -2147483648, "resourceLocationId": -2147483648, "bookingCategoryId": 0,
    "startDate": "2026-06-15", "endDate": "2026-06-22", "isReserving": True,
    "getDailyAvailability": False, "partySize": 1, "numEquipment": 1,
    "equipmentCategoryId": -32768,
}
r = requests.get("https://longpoint.goingtocamp.com/api/availability/map", headers=headers, params=params, timeout=15)
print("MAPDATA:", r.status_code)
mapdata = r.json()
rids = list(mapdata["resourceAvailabilities"].keys())
print(f"  found {len(rids)} resource ids, first 3:", rids[:3])

resource_id = rids[0]
for path in [
    f"/api/resource/details?resourceId={resource_id}",
    f"/api/resource/{resource_id}",
    f"/api/v1/resource/details?resourceId={resource_id}",
    f"/api/resourceDetails?resourceId={resource_id}",
]:
    url = f"https://longpoint.goingtocamp.com{path}"
    r = requests.get(url, headers=headers, timeout=15)
    print(f"  {r.status_code}  {path}  body: {r.text[:120]}")
