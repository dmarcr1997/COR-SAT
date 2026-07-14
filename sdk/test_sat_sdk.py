from sat_sdk import SatClient

sat = SatClient()

print(sat.health())
print(sat.system.status())
print(sat.camera.capture())
