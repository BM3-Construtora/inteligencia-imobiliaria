// Espelho de src/regulatory_geo.py WATER_COURSES — cursos d'água principais de
// Marília para overlay de APP (Área de Preservação Permanente, Lei 12.651/2012).
// Coordenadas [lat, lng]. Mantenha em sincronia com o backend.

export interface WaterCourse {
  nome: string
  tipo: string
  appBufferM: number
  coords: [number, number][]
}

export const WATER_COURSES: WaterCourse[] = [
  {
    nome: "Córrego do Cascata",
    tipo: "corrego",
    appBufferM: 30,
    coords: [
      [-22.1995, -49.9612],
      [-22.2042, -49.9587],
      [-22.2095, -49.9551],
      [-22.2148, -49.951],
      [-22.2201, -49.9468],
      [-22.2254, -49.9421],
    ],
  },
  {
    nome: "Ribeirão Lajeado",
    tipo: "ribeirao",
    appBufferM: 50,
    coords: [
      [-22.185, -49.932],
      [-22.1902, -49.9395],
      [-22.1968, -49.9462],
      [-22.2035, -49.9521],
      [-22.211, -49.958],
      [-22.2188, -49.9635],
    ],
  },
  {
    nome: "Córrego do Barbosa",
    tipo: "corrego",
    appBufferM: 30,
    coords: [
      [-22.2305, -49.971],
      [-22.2268, -49.9655],
      [-22.2231, -49.9602],
      [-22.2195, -49.9548],
      [-22.2158, -49.9495],
    ],
  },
]
