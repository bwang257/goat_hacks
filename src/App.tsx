import { useState, useEffect, useRef, useCallback } from 'react'
import { MapContainer, TileLayer, useMapEvents, CircleMarker, Popup } from 'react-leaflet'
import MarkerClusterGroup from 'react-leaflet-markercluster'
import type { LatLngBounds } from 'leaflet'
import 'leaflet/dist/leaflet.css'
import 'react-leaflet-markercluster/styles'
import './App.css'

interface MBTAStop {
  id: string
  name: string
  latitude: number
  longitude: number
}

interface Point {
  lat: number
  lng: number
  stopName?: string
}

function MapEvents({
  onMapMove,
  onMapClick,
  onMapReady,
}: {
  onMapMove: (bounds: LatLngBounds) => void
  onMapClick: (e: any) => void
  onMapReady: (map: any) => void
}) {
  const map = useMapEvents({
    moveend: () => {
      onMapMove(map.getBounds())
    },
    zoomend: () => {
      onMapMove(map.getBounds())
    },
    click: onMapClick,
  })

  // Store map reference and trigger initial fetch on first render
  const mapReadyRef = useRef(false)
  if (!mapReadyRef.current) {
    mapReadyRef.current = true
    onMapReady(map)
  }

  return null
}

function App() {
  const [stops, setStops] = useState<MBTAStop[]>([])
  const [pointA, setPointA] = useState<Point | null>(null)
  const [pointB, setPointB] = useState<Point | null>(null)
  const [walkingTime, setWalkingTime] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const abortControllerRef = useRef<AbortController | null>(null)
  const debounceTimerRef = useRef<number | null>(null)
  const cacheRef = useRef<Map<string, MBTAStop[]>>(new Map())

  const fetchStops = useCallback(async (bounds: LatLngBounds) => {
    const apiKey = import.meta.env.VITE_MBTA_API_KEY
    if (!apiKey) {
      setError('MBTA API key not found. Please set VITE_MBTA_API_KEY in .env file.')
      return
    }

    const southWest = bounds.getSouthWest()
    const northEast = bounds.getNorthEast()
    const cacheKey = `${southWest.lat.toFixed(4)},${southWest.lng.toFixed(4)}_${northEast.lat.toFixed(4)},${northEast.lng.toFixed(4)}`

    if (cacheRef.current.has(cacheKey)) {
      setStops(cacheRef.current.get(cacheKey)!)
      return
    }

    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }

    abortControllerRef.current = new AbortController()

    try {
      setLoading(true)
      setError(null)

      const url = `https://api-v3.mbta.com/stops?filter[latitude]=${southWest.lat},${northEast.lat}&filter[longitude]=${southWest.lng},${northEast.lng}`
      const response = await fetch(url, {
        headers: {
          'x-api-key': apiKey,
        },
        signal: abortControllerRef.current.signal,
      })

      if (!response.ok) {
        throw new Error(`MBTA API error: ${response.status}`)
      }

      const data = await response.json()
      const stopsData: MBTAStop[] = data.data
        .filter((stop: any) => stop.attributes.latitude && stop.attributes.longitude)
        .map((stop: any) => ({
          id: stop.id,
          name: stop.attributes.name || 'Unnamed Stop',
          latitude: stop.attributes.latitude,
          longitude: stop.attributes.longitude,
        }))

      cacheRef.current.set(cacheKey, stopsData)
      setStops(stopsData)
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        setError(`Failed to fetch stops: ${err.message}`)
      }
    } finally {
      setLoading(false)
    }
  }, [])

  const handleMapMove = useCallback(
    (bounds: LatLngBounds) => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current)
      }

      debounceTimerRef.current = window.setTimeout(() => {
        fetchStops(bounds)
      }, 300)
    },
    [fetchStops]
  )

  const calculateWalkingTime = useCallback(async (a: Point, b: Point) => {
    try {
      setError(null)
      const response = await fetch('http://localhost:8000/api/walking-time', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          lat1: a.lat,
          lng1: a.lng,
          lat2: b.lat,
          lng2: b.lng,
        }),
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Request failed' }))
        throw new Error(errorData.detail || 'Walking time calculation failed')
      }

      const data = await response.json()
      setWalkingTime(data.duration_minutes)
    } catch (err: any) {
      setError(`Failed to calculate walking time: ${err.message}`)
      setWalkingTime(null)
    }
  }, [])

  const handleMapClick = useCallback((e: any) => {
    const { lat, lng } = e.latlng

    if (!pointA) {
      setPointA({ lat, lng })
      setPointB(null)
      setWalkingTime(null)
    } else if (!pointB) {
      setPointB({ lat, lng })
      calculateWalkingTime(pointA, { lat, lng })
    } else {
      setPointA({ lat, lng })
      setPointB(null)
      setWalkingTime(null)
    }
  }, [pointA, calculateWalkingTime])

  const handleStopClick = useCallback((stop: MBTAStop) => {
    const point: Point = {
      lat: stop.latitude,
      lng: stop.longitude,
      stopName: stop.name,
    }

    if (!pointA) {
      setPointA(point)
      setPointB(null)
      setWalkingTime(null)
    } else if (!pointB) {
      setPointB(point)
      calculateWalkingTime(pointA, point)
    } else {
      setPointA(point)
      setPointB(null)
      setWalkingTime(null)
    }
  }, [pointA, calculateWalkingTime])

  const mapRef = useRef<any>(null)

  useEffect(() => {
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current)
      }
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
    }
  }, [])

  const handleMapReady = useCallback(() => {
    if (mapRef.current) {
      setTimeout(() => {
        const bounds = mapRef.current.getBounds()
        fetchStops(bounds)
      }, 100)
    }
  }, [fetchStops])

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      <MapContainer
        center={[42.3601, -71.0589]}
        zoom={13}
        style={{ height: '100%', width: '100%' }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <MapEvents onMapMove={handleMapMove} onMapClick={handleMapClick} onMapReady={handleMapReady} />
        <MarkerClusterGroup>
          {stops.map((stop) => (
            <CircleMarker
              key={stop.id}
              center={[stop.latitude, stop.longitude]}
              radius={5}
              pathOptions={{ color: 'blue', fillColor: 'blue', fillOpacity: 0.6 }}
              eventHandlers={{
                click: () => handleStopClick(stop),
              }}
            >
              <Popup>{stop.name}</Popup>
            </CircleMarker>
          ))}
        </MarkerClusterGroup>
      </MapContainer>

      <div className="info-panel">
        <div>Stops displayed: {stops.length}</div>
        <div>
          Point A: {pointA ? `${pointA.lat.toFixed(4)}, ${pointA.lng.toFixed(4)}${pointA.stopName ? ` (${pointA.stopName})` : ''}` : 'Not selected'}
        </div>
        <div>
          Point B: {pointB ? `${pointB.lat.toFixed(4)}, ${pointB.lng.toFixed(4)}${pointB.stopName ? ` (${pointB.stopName})` : ''}` : 'Not selected'}
        </div>
        <div>
          {walkingTime !== null
            ? `Walking time: ${walkingTime} minutes`
            : pointA && pointB
            ? 'Calculating...'
            : 'Select two points to calculate walking time'}
        </div>
        {error && <div style={{ color: 'red', marginTop: '8px' }}>{error}</div>}
        {loading && <div style={{ marginTop: '8px' }}>Loading stops...</div>}
      </div>
    </div>
  )
}

export default App
