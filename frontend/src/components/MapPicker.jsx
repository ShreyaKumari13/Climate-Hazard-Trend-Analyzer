import { MapContainer, TileLayer, Marker, useMapEvents } from "react-leaflet";
import { useEffect } from "react";
import L from "leaflet";

// Fix default marker icons (Leaflet + bundlers don't resolve these by default).
import markerIcon2x from "leaflet/dist/images/marker-icon-2x.png";
import markerIcon from "leaflet/dist/images/marker-icon.png";
import markerShadow from "leaflet/dist/images/marker-shadow.png";

L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
});

function ClickHandler({ onPick }) {
  useMapEvents({
    click(e) {
      onPick({
        lat: parseFloat(e.latlng.lat.toFixed(4)),
        lon: parseFloat(e.latlng.lng.toFixed(4)),
        region_name: null,
      });
    },
  });
  return null;
}

function Recenter({ lat, lon }) {
  const map = useMapEvents({});
  useEffect(() => {
    if (Number.isFinite(lat) && Number.isFinite(lon)) {
      map.setView([lat, lon], map.getZoom());
    }
  }, [lat, lon, map]);
  return null;
}

export default function MapPicker({ value, onChange }) {
  const lat = Number.isFinite(value.lat) ? value.lat : 20;
  const lon = Number.isFinite(value.lon) ? value.lon : 0;

  return (
    <div className="map-wrap">
      <MapContainer center={[lat, lon]} zoom={4} scrollWheelZoom className="map">
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <ClickHandler onPick={onChange} />
        <Recenter lat={lat} lon={lon} />
        {Number.isFinite(value.lat) && Number.isFinite(value.lon) && (
          <Marker position={[value.lat, value.lon]} />
        )}
      </MapContainer>
      <p className="map-hint">Click the map to pick a location.</p>
    </div>
  );
}
