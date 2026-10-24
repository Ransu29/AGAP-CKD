import { describe, it, expect } from 'vitest';
import { cleanTownName, metricScale, metricValue, type MapArea } from '../components/LagunaMap';
import geojson from '../data/laguna-municipalities.json';

describe('Laguna Map', () => {
  it('correctly cleans city prefixes from municipality names', () => {
    expect(cleanTownName('City of Calamba')).toBe('Calamba');
    expect(cleanTownName('Biñan City')).toBe('Biñan');
    expect(cleanTownName('Santa Rosa')).toBe('Santa Rosa');
  });

  it('validates GeoJSON contains 30 valid features with non-empty polygon coordinates', () => {
    expect(geojson.type).toBe('FeatureCollection');
    expect(geojson.features.length).toBe(30);
    geojson.features.forEach((f: any) => {
      expect(f.geometry.type).toMatch(/Polygon|MultiPolygon/);
      expect(f.geometry.coordinates.length).toBeGreaterThan(0);
      expect(f.properties.shapeName).toBeDefined();
    });
  });

  const area = (overrides: Partial<MapArea>): MapArea => ({
    name: 'Calamba', checks: 600, hidden: false, faded: false, medium_high_share: 70, range_low: 66,
    range_high: 74, coverage_pct: 0.16, awareness_gap: 18, ...overrides,
  });

  it('withholds every metric for areas hidden by the privacy rule', () => {
    const hidden = area({ checks: 4, hidden: true, medium_high_share: null, coverage_pct: null, awareness_gap: null });
    expect(metricValue(hidden, 'share')).toBeNull();
    expect(metricValue(hidden, 'coverage')).toBeNull();
    expect(metricValue(undefined, 'awareness')).toBeNull();
    expect(metricValue(area({}), 'coverage')).toBe(0.16);
  });

  it('builds the colour scale from full-colour areas only', () => {
    const scale = metricScale(
      { A: area({ medium_high_share: 60 }), B: area({ medium_high_share: 80 }), C: area({ faded: true, medium_high_share: 95 }) },
      'share'
    );
    expect(scale.min).toBe(60);
    expect(scale.max).toBe(80);
    expect(scale.color(95)).toBe(scale.colors[scale.colors.length - 1]);
    expect(scale.color(60)).toBe(scale.colors[0]);
  });
});
