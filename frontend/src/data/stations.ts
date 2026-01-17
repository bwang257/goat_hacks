import type { Station as StationType } from '../types';

export interface Station extends StationType {
  isTransferHub: boolean;
}

export const STATIONS: Station[] = [
  {
    id: 'place-pktrm',
    name: 'Park Street',
    lat: 42.3565,
    lon: -71.0624,
    routes: ['Red', 'Green'],
    isTransferHub: true,
  },
  {
    id: 'place-dwnxg',
    name: 'Downtown Crossing',
    lat: 42.3555,
    lon: -71.0603,
    routes: ['Red', 'Orange'],
    isTransferHub: true,
  },
  {
    id: 'place-state',
    name: 'State',
    lat: 42.3588,
    lon: -71.0573,
    routes: ['Orange', 'Blue'],
    isTransferHub: true,
  },
  {
    id: 'place-gover',
    name: 'Government Center',
    lat: 42.3594,
    lon: -71.0593,
    routes: ['Green', 'Blue'],
    isTransferHub: true,
  },
  {
    id: 'place-north',
    name: 'North Station',
    lat: 42.3654,
    lon: -71.0615,
    routes: ['Orange', 'Green'],
    isTransferHub: true,
  },
  {
    id: 'place-harsq',
    name: 'Harvard',
    lat: 42.3736,
    lon: -71.1190,
    routes: ['Red'],
    isTransferHub: false,
  },
  {
    id: 'place-alfcl',
    name: 'Alewife',
    lat: 42.3956,
    lon: -71.1424,
    routes: ['Red'],
    isTransferHub: false,
  },
  {
    id: 'place-jfk',
    name: 'JFK/UMass',
    lat: 42.3204,
    lon: -71.0519,
    routes: ['Red'],
    isTransferHub: true,
  },
  {
    id: 'place-forhl',
    name: 'Forest Hills',
    lat: 42.3005,
    lon: -71.1139,
    routes: ['Orange'],
    isTransferHub: false,
  },
  {
    id: 'place-ogmnl',
    name: 'Oak Grove',
    lat: 42.4368,
    lon: -71.0712,
    routes: ['Orange'],
    isTransferHub: false,
  },
  {
    id: 'place-wondl',
    name: 'Wonderland',
    lat: 42.4134,
    lon: -70.9916,
    routes: ['Blue'],
    isTransferHub: false,
  },
  {
    id: 'place-lech',
    name: 'Lechmere',
    lat: 42.3704,
    lon: -71.0769,
    routes: ['Green'],
    isTransferHub: false,
  },
];
