import React, { useMemo, useState } from 'react';
import * as d3 from 'd3';
import lagunaGeoDataRaw from '../data/laguna-municipalities.json';

export type MapMetric = 'share' | 'coverage' | 'awareness';

// One municipality as served by /api/analyst/overview. Values are null when the area is hidden.
export interface MapArea {
  name: string;
  checks: number;
  hidden: boolean;
  faded: boolean;
  medium_high_share: number | null;
  range_low: number | null;
  range_high: number | null;
  coverage_pct: number | null;
  awareness_gap: number | null;
}

export const cleanTownName = (name: string): string => {
  return name.normalize('NFC').replace('City of ', '').replace(' City', '').trim();
};

export const METRIC_LABELS: Record<MapMetric, string> = {
  share: 'Medium/High share',
  coverage: 'Coverage',
  awareness: 'Awareness gap',
};

const PALETTES: Record<MapMetric, string[]> = {
  share: ['#DDF1E4', '#9FDDB6', '#5CC487', '#22A75A', '#17573A'],
  coverage: ['#E9F0FA', '#C7D8EE', '#A9C4E4', '#5F8BC0', '#24405F'],
  awareness: ['#FBF3D5', '#FBEBB5', '#F7DE8A', '#E8B92E', '#B98B12'],
};
const NO_DATA = '#E3E8E4';

// White diagonal stripes laid over a faded area's colour.
export const FadedHatch: React.FC<{ id: string }> = ({ id }) => (
  <pattern id={id} patternUnits="userSpaceOnUse" width={6} height={6} patternTransform="rotate(45)">
    <rect width={3} height={6} fill="#FFFFFF" fillOpacity={0.7} />
  </pattern>
);

export const metricValue = (area: MapArea | undefined, metric: MapMetric): number | null => {
  if (!area || area.hidden) return null;
  if (metric === 'coverage') return area.coverage_pct;
  if (metric === 'awareness') return area.awareness_gap;
  return area.medium_high_share;
};

export const formatMetric = (value: number, metric: MapMetric): string =>
  metric === 'coverage' ? `${value.toFixed(2)}%` : `${value.toFixed(0)}%`;

// Five equal-width bins spanning the full-colour areas' values, so each metric gets its own legend.
// Faded areas (few checks) are coloured on the same scale, clamped to its ends.
export const metricScale = (areas: Record<string, MapArea>, metric: MapMetric) => {
  const values = Object.values(areas)
    .filter((a) => !a.faded)
    .map((a) => metricValue(a, metric))
    .filter((v): v is number => v !== null);
  const min = values.length ? Math.min(...values) : 0;
  const max = values.length ? Math.max(...values) : 1;
  const colors = PALETTES[metric];
  const color = (v: number) => {
    if (max === min) return colors[2];
    const bin = Math.max(0, Math.min(colors.length - 1, Math.floor(((v - min) / (max - min)) * colors.length)));
    return colors[bin];
  };
  return { min, max, colors, color, darkFrom: 3 };
};

interface LagunaMapProps {
  selectedTown: string | null;
  onSelectTown: (townName: string) => void;
  metric: MapMetric;
  areas: Record<string, MapArea>;
}

export const LagunaMap: React.FC<LagunaMapProps> = ({ selectedTown, onSelectTown, metric, areas }) => {
  const [hoveredTown, setHoveredTown] = useState<string | null>(null);
  const [tooltip, setTooltip] = useState<{ visible: boolean; x: number; y: number; town: string }>({
    visible: false,
    x: 0,
    y: 0,
    town: '',
  });

  // Map canvas geometry (matches 1440 layout from AGAP-Analyst-Dashboard.dc.html)
  const width = 760;
  const height = 580;

  // Ensure all polygon features are correctly wound for D3 spherical projection
  const geoData = useMemo(() => {
    const raw = JSON.parse(JSON.stringify(lagunaGeoDataRaw));
    raw.features.forEach((f: any) => {
      if (d3.geoArea(f) > 2 * Math.PI) {
        if (f.geometry.type === 'Polygon') {
          f.geometry.coordinates = f.geometry.coordinates.map((ring: any) => ring.slice().reverse());
        } else if (f.geometry.type === 'MultiPolygon') {
          f.geometry.coordinates = f.geometry.coordinates.map((poly: any) =>
            poly.map((ring: any) => ring.slice().reverse())
          );
        }
      }
    });
    return raw;
  }, []);

  // Mercator projection fitted cleanly with padding inside viewBox
  const { projectedFeatures, lakeCoord } = useMemo(() => {
    const projection = d3.geoMercator().fitExtent(
      [
        [16, 16],
        [width - 16, height - 16],
      ],
      geoData as any
    );
    const pathGen = d3.geoPath().projection(projection);
    const features = geoData.features.map((feature: any) => {
      const name = cleanTownName(feature.properties.shapeName || '');
      return { name, d: pathGen(feature) || '', centroid: pathGen.centroid(feature) };
    });
    // Center of Laguna de Bay water body
    const lake = projection([121.26, 14.34]) || [335, 235];
    return { projectedFeatures: features, lakeCoord: lake };
  }, [geoData]);

  const scale = useMemo(() => metricScale(areas, metric), [areas, metric]);
  const selectedClean = selectedTown ? cleanTownName(selectedTown) : null;

  const fillFor = (name: string) => {
    const v = metricValue(areas[name], metric);
    return v === null ? NO_DATA : scale.color(v);
  };
  const isDark = (name: string) => {
    const v = metricValue(areas[name], metric);
    return v !== null && scale.colors.indexOf(scale.color(v)) >= scale.darkFrom;
  };

  // Label municipalities with 50+ checks (with their number of checks) to prevent crowding
  const labelledTowns = projectedFeatures
    .filter((p: any) => areas[p.name] && !areas[p.name].hidden && !areas[p.name].faded)
    .sort((a: any, b: any) => areas[b.name].checks - areas[a.name].checks);

  const hovered = tooltip.visible ? areas[tooltip.town] : undefined;
  const hoveredValue = metricValue(hovered, metric);

  return (
    <div className="relative w-full aspect-[760/580] min-h-[360px] max-h-[580px] bg-white select-none overflow-hidden rounded-[20px]">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-full block" preserveAspectRatio="xMidYMid meet">
        <defs>
          <FadedHatch id="faded-hatch" />
        </defs>
        {/* Laguna de Bay Lake Label */}
        <text
          x={lakeCoord[0]}
          y={lakeCoord[1]}
          textAnchor="middle"
          fill="#7FA08C"
          fontSize={15}
          fontWeight={700}
          letterSpacing=".08em"
          fontFamily="'Nunito', sans-serif"
          className="pointer-events-none select-none"
        >
          Laguna de Bay
        </text>

        {/* Municipality Polygons */}
        <g>
          {projectedFeatures.map((item: any) => {
            const isSelected = item.name === selectedClean;
            const isHovered = item.name === hoveredTown;
            return (
              <path
                key={item.name}
                d={item.d}
                fill={fillFor(item.name)}
                stroke={isSelected || isHovered ? '#1B2A22' : '#FFFFFF'}
                strokeWidth={isSelected ? 3.5 : isHovered ? 2.5 : 1.5}
                className="cursor-pointer transition-all duration-150"
                onMouseEnter={() => setHoveredTown(item.name)}
                onMouseMove={(e) => {
                  const rect = e.currentTarget.ownerSVGElement?.getBoundingClientRect();
                  if (rect) {
                    const mouseX = e.clientX - rect.left;
                    const mouseY = e.clientY - rect.top;
                    // Flip tooltip to the left if near right edge, flip up if near bottom edge
                    const tooltipX = mouseX > rect.width - 230 ? mouseX - 210 : mouseX + 16;
                    const tooltipY = mouseY > rect.height - 110 ? mouseY - 90 : mouseY + 16;
                    setTooltip({
                      visible: true,
                      x: Math.max(12, tooltipX),
                      y: Math.max(12, tooltipY),
                      town: item.name,
                    });
                  }
                }}
                onMouseLeave={() => {
                  setHoveredTown(null);
                  setTooltip((t) => ({ ...t, visible: false }));
                }}
                onClick={() => onSelectTown(item.name)}
              />
            );
          })}
        </g>

        {/* Faded areas (10-49 checks) keep their colour under a hatch, so they never look like hidden ones */}
        <g className="pointer-events-none">
          {projectedFeatures
            .filter((item: any) => areas[item.name]?.faded && !areas[item.name]?.hidden)
            .map((item: any) => (
              <path key={`hatch-${item.name}`} d={item.d} fill="url(#faded-hatch)" />
            ))}
        </g>

        {/* Labels with the number of checks, for areas with 50+ checks */}
        <g className="pointer-events-none">
          {labelledTowns.map((item: any) => {
            const [cx, cy] = item.centroid;
            const fill = isDark(item.name) ? '#FFFFFF' : '#17573A';
            return (
              <text
                key={`lbl-${item.name}`}
                x={cx}
                y={cy + 3}
                textAnchor="middle"
                fontSize={11}
                fontWeight={800}
                fill={fill}
                fontFamily="'Nunito', sans-serif"
                className="select-none"
              >
                {item.name}
                <tspan fontWeight={600}> · {areas[item.name].checks}</tspan>
              </text>
            );
          })}
        </g>
      </svg>

      {/* Floating Tooltip */}
      {tooltip.visible && (
        <div
          className="absolute z-30 pointer-events-none bg-[#1B2A22] text-white rounded-[16px] px-3.5 py-3 text-xs leading-snug shadow-2xl transition-opacity duration-150 min-w-[190px]"
          style={{
            left: `${tooltip.x}px`,
            top: `${tooltip.y}px`,
          }}
        >
          <div className="font-extrabold text-[15px] mb-0.5">{tooltip.town}</div>
          {!hovered ? (
            <div className="text-[#B9D9C6] text-xs">No data</div>
          ) : hovered.hidden || hoveredValue === null ? (
            <div className="text-[#B9D9C6] text-xs">Too few checks to show</div>
          ) : (
            <>
              <div className="text-white text-xs font-semibold">
                {METRIC_LABELS[metric]}: {formatMetric(hoveredValue, metric)}
                {metric === 'share' && hovered.range_low !== null && hovered.range_high !== null && (
                  <span className="text-[#B9D9C6]">
                    {' '}
                    (range {hovered.range_low.toFixed(0)}–{hovered.range_high.toFixed(0)}%)
                  </span>
                )}
              </div>
              <div className="text-[#B9D9C6] text-xs mt-0.5">{hovered.checks.toLocaleString()} checks</div>
              {hovered.faded && (
                <div className="text-[#F7DE8A] text-[11px] mt-1 font-bold">Under 50 checks: shown faded</div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
};
