import React, { useState, useEffect, useMemo } from 'react';
import { ChevronDown } from 'lucide-react';
import {
  LagunaMap,
  FadedHatch,
  cleanTownName,
  metricScale,
  formatMetric,
  METRIC_LABELS,
  type MapArea,
  type MapMetric,
} from '../components/LagunaMap';

// Shapes served by /api/analyst/* (built by `make analyst`; see src/agap/analyst.py).
interface Factor {
  label: string;
  share: number;
  difference_pts: number;
}

interface Municipality extends MapArea {
  municipality: string;
  adults: number;
  channel_split: { app: number; field: number; sms: number } | null;
  factors: Factor[] | null;
  done_replies: number | null;
  last_synced: string | null;
}

interface Overview {
  province: string;
  period: { start: string; end: string; label: string };
  rules: { hide_below_checks: number; fade_below_checks: number; factors_min_checks: number };
  summary: {
    checks: number;
    adults: number;
    coverage_pct: number;
    medium_high_share: number;
    awareness_gap: number;
    channel_split: { app: number; field: number; sms: number };
    done_replies: number;
    recorded_checks?: { total: number; by_channel: Record<string, number> };
  };
  municipalities: Municipality[];
  sources: Record<string, string>;
  built_with: { config_fingerprint: string; git_commit: string | null; seed: number };
  model_run: { config_fingerprint: string; git_commit: string; seed: number };
}

interface ArmQuality {
  caught_pct: number;
  abnormal_rate_pct: number[];
  referred_pct: number;
  auroc: number;
}

interface ModelQuality {
  run: { config_fingerprint: string; git_commit: string; seed: number; n_test: number; n_validation: number; n_train: number };
  cohort: string;
  thai: ArmQuality;
  agap: ArmQuality;
  agap_alone: ArmQuality;
  cutoffs: { medium: number; high: number; validation_caught_pct: number; validation_high_rate_pct: number; rule: string };
  floor: { changed: number; n: number; changed_pct: number; to_medium: number; to_high: number } | null;
  prevalence_sensitivity: Array<{
    target_prevalence_pct: number;
    cohort_prevalence_pct: number;
    high_rate_pct: number;
    thai_high_rate_pct: number;
    target_rate_pct: number;
    meets_target: boolean;
  }>;
  outcome: string;
  prevalence_source: string;
  effect_sizes: Array<{ item: string; odds_ratio: number; tag: string; evidence: string }>;
}

interface Climate {
  period: { start: string; end: string; label: string };
  hot_day_definition: string;
  source: string;
  note: string;
  heat_index_hot_c: number;
  name: string;
  municipality: string;
  series: Array<{
    month: string;
    label: string;
    hot_days: number | null;
    peak_heat_index_c: number | null;
    rain_mm: number | null;
    mean_tmax_c: number | null;
  }>;
}

const MONTHS_TL = ['Ene', 'Peb', 'Mar', 'Abr', 'May', 'Hun', 'Hul', 'Ago', 'Set', 'Okt', 'Nob', 'Dis'];

const formatSynced = (iso: string) => {
  const d = new Date(iso);
  const hours = d.getHours() % 12 || 12;
  const minutes = String(d.getMinutes()).padStart(2, '0');
  return `${d.getDate()} ${MONTHS_TL[d.getMonth()]}, ${hours}:${minutes} ${d.getHours() < 12 ? 'AM' : 'PM'}`;
};

const signedPts = (pts: number) => `${pts > 0 ? '+' : pts < 0 ? '−' : '±'}${Math.abs(pts).toFixed(1)} pts`;

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `${res.status} ${res.statusText}`);
  return body as T;
}

const Tag: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <span className="text-[11px] font-bold text-[#17573A] bg-[#DDF1E4] rounded-full px-2 py-0.5 whitespace-nowrap">
    {children}
  </span>
);

const ChannelBar: React.FC<{ split: { app: number; field: number; sms: number } }> = ({ split }) => (
  <>
    <div className="flex h-3.5 rounded-full overflow-hidden gap-0.5">
      <div style={{ width: `${split.field}%` }} className="bg-[#9FDDB6]" />
      <div style={{ width: `${split.app}%` }} className="bg-[#22A75A]" />
      <div style={{ width: `${split.sms}%` }} className="bg-[#1B2A22]" />
    </div>
    <div className="flex gap-3.5 text-[12px] font-bold text-[#3E5046]">
      <span>Field {split.field.toFixed(0)}%</span>
      <span>App {split.app.toFixed(0)}%</span>
      <span>SMS {split.sms.toFixed(0)}%</span>
    </div>
  </>
);

const METRIC_TEXT: Record<MapMetric, { title: React.ReactNode; note: string }> = {
  share: {
    title: (
      <>
        Share at <span className="font-extrabold">Medium or High</span>
      </>
    ),
    note: "Age-standardised, among people checked. Includes people who don't know their BP or sugar status.",
  },
  coverage: {
    title: <span className="font-extrabold">Coverage</span>,
    note: 'Checks ÷ adults (PSA 2024 Census), last 12 months.',
  },
  awareness: {
    title: <span className="font-extrabold">Awareness gap</span>,
    note: 'Share answering "I don\'t know" to diabetes or high BP, among people checked.',
  },
};

export const AnalystView: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'risk' | 'climate' | 'model'>('risk');
  const [metric, setMetric] = useState<MapMetric>('share');
  const [selectedTown, setSelectedTown] = useState<string | null>('Calamba');
  const [climateTown, setClimateTown] = useState<string>('Calamba');

  const [overview, setOverview] = useState<Overview | null>(null);
  const [quality, setQuality] = useState<ModelQuality | null>(null);
  const [climate, setClimate] = useState<Climate | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [climateError, setClimateError] = useState<string | null>(null);

  useEffect(() => {
    getJson<Overview>('/api/analyst/overview')
      .then(setOverview)
      .catch((err) => setError(err.message));
    getJson<ModelQuality>('/api/analyst/model-quality')
      .then(setQuality)
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    setClimateError(null);
    getJson<Climate>(`/api/analyst/climate/${encodeURIComponent(climateTown)}`)
      .then(setClimate)
      .catch((err) => {
        setClimate(null);
        setClimateError(err.message);
      });
  }, [climateTown]);

  const areas = useMemo(() => {
    const dict: Record<string, Municipality> = {};
    overview?.municipalities.forEach((m) => {
      dict[cleanTownName(m.name)] = m;
    });
    return dict;
  }, [overview]);

  const townNames = useMemo(() => Object.keys(areas).sort((a, b) => a.localeCompare(b)), [areas]);
  const scale = useMemo(() => metricScale(areas, metric), [areas, metric]);
  const selected = selectedTown ? areas[cleanTownName(selectedTown)] : undefined;

  const selectTown = (town: string) => {
    setSelectedTown(town);
    setClimateTown(town);
  };

  const tabButton = (tab: 'risk' | 'climate' | 'model', label: string) => (
    <button
      onClick={() => setActiveTab(tab)}
      className={`px-4 sm:px-5 py-2 rounded-full text-sm font-bold transition ${
        activeTab === tab ? 'bg-[#1B2A22] text-white shadow-sm' : 'text-[#3E5046] hover:text-[#1B2A22]'
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="flex flex-col items-center py-6 px-4 font-['Nunito',sans-serif] text-[#1B2A22]">
      <div className="w-full max-w-[1440px] flex flex-col gap-4 sm:gap-5">
        <div className="w-full bg-[#F3F8F4] rounded-[24px] overflow-hidden shadow-[0_2px_10px_rgba(23,87,58,0.08)] flex flex-col border border-[#DCE7DF]/60">
          {/* Every analyst screen carries the simulated-data banner (PRD v3) */}
          <div className="bg-[#FBEBB5] text-[#6B4E00] text-sm font-extrabold px-6 lg:px-8 py-2.5 flex items-center gap-2.5 border-b border-[#F7DE8A]">
            <span className="w-2.5 h-2.5 rounded-full bg-[#E8B92E] shrink-0" />
            <span>Simulated data · Among people checked, last 12 months</span>
          </div>

          {/* Navigation Header */}
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center px-6 lg:px-8 py-4 sm:py-5 gap-4">
            <div className="flex flex-wrap items-center gap-4 sm:gap-7">
              <div className="text-[20px] font-extrabold text-[#1B2A22]">
                AGAP Kidney Check <span className="font-medium text-[#5C6E63]">· Laguna</span>
              </div>
              <div className="flex gap-1 bg-white rounded-full p-1 shadow-sm border border-[#DCE7DF]">
                {tabButton('risk', 'Risk map')}
                {tabButton('climate', 'Climate context')}
                {tabButton('model', 'Model quality')}
              </div>
            </div>
            <div className="text-[13px] text-[#5C6E63] font-semibold">
              {activeTab === 'climate' ? climate?.period.label : overview?.period.label}
            </div>
          </div>

          {error && (
            <div className="mx-8 mb-8 bg-white rounded-[28px] p-6 shadow-sm">
              <div className="text-[16px] font-extrabold">Analyst data is not available</div>
              <div className="text-[13px] text-[#5C6E63] mt-1">{error}</div>
            </div>
          )}

          {/* TAB 1: RISK MAP (A1 province map + A2 municipality detail) */}
          {activeTab === 'risk' && overview && (
            <div className="flex flex-col gap-5 px-4 sm:px-6 lg:px-8 pb-6 lg:pb-8">
              <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_420px] gap-5 items-start">
                <div className="bg-white rounded-[28px] p-5 sm:p-7 flex flex-col gap-5 shadow-sm border border-[#DCE7DF]/60">
                  <div className="flex flex-col sm:flex-row justify-between items-start gap-4">
                    <div className="flex flex-col gap-1.5">
                      <div className="text-[26px] sm:text-[30px] leading-tight font-normal text-[#1B2A22]">{METRIC_TEXT[metric].title}</div>
                      <div className="text-[14px] text-[#5C6E63]">{METRIC_TEXT[metric].note}</div>
                    </div>
                    <div className="flex gap-1 bg-[#F3F8F4] rounded-full p-1 shrink-0 border border-[#DCE7DF]">
                      {(['share', 'coverage', 'awareness'] as MapMetric[]).map((m) => (
                        <button
                          key={m}
                          onClick={() => setMetric(m)}
                          className={`px-3.5 py-2 rounded-full text-[13px] font-bold transition ${
                            metric === m ? 'bg-[#22A75A] text-white shadow-sm' : 'text-[#3E5046] hover:text-[#1B2A22]'
                          }`}
                        >
                          {METRIC_LABELS[m]}
                        </button>
                      ))}
                    </div>
                  </div>

                  <LagunaMap selectedTown={selectedTown} onSelectTown={selectTown} metric={metric} areas={areas} />

                  {/* Legend: this metric's range, then the privacy display rules */}
                  <div className="flex flex-wrap justify-between items-center gap-5 border-t border-[#E6EEE8] pt-4 text-[12px] font-bold text-[#5C6E63]">
                    <div className="flex items-center gap-2.5">
                      <span>{formatMetric(scale.min, metric)}</span>
                      <div className="flex gap-1">
                        {scale.colors.map((c) => (
                          <div key={c} className="w-9 h-3.5 rounded-full" style={{ background: c }} />
                        ))}
                      </div>
                      <span>{formatMetric(scale.max, metric)}</span>
                    </div>
                    <div className="flex flex-wrap items-center gap-[18px] text-[12px]">
                      <span className="flex items-center gap-1.5">
                        <span className="w-3.5 h-3.5 rounded-full" style={{ background: scale.colors[3] }} />
                        <span>{overview.rules.fade_below_checks}+ checks</span>
                      </span>
                      <span className="flex items-center gap-1.5">
                        <svg className="w-3.5 h-3.5" viewBox="0 0 14 14" aria-hidden="true">
                          <defs>
                            <FadedHatch id="legend-hatch" />
                          </defs>
                          <circle cx={7} cy={7} r={7} fill={scale.colors[3]} />
                          <circle cx={7} cy={7} r={7} fill="url(#legend-hatch)" />
                        </svg>
                        <span>
                          {overview.rules.hide_below_checks}–{overview.rules.fade_below_checks - 1}, faded
                        </span>
                      </span>
                      <span className="flex items-center gap-1.5">
                        <span className="w-3.5 h-3.5 rounded-full bg-[#E3E8E4]" />
                        <span>Under {overview.rules.hide_below_checks}: too few checks</span>
                      </span>
                    </div>
                  </div>
                </div>

                {/* A2: municipality detail */}
                <div className="flex flex-col gap-3">
                  {!selected ? (
                    <div className="bg-white rounded-[28px] p-6 shadow-sm text-[14px] text-[#5C6E63]">
                      Select a municipality on the map to see its detail.
                    </div>
                  ) : (
                    <>
                      <div className="bg-white rounded-[28px] p-[22px] flex flex-col gap-3.5 shadow-sm">
                        <div className="flex justify-between items-center">
                          <div className="text-[24px] font-extrabold text-[#1B2A22]">{selected.name}</div>
                          <button
                            onClick={() => setSelectedTown(null)}
                            title="Close"
                            aria-label="Close municipality detail"
                            className="w-9 h-9 rounded-full bg-[#F3F8F4] hover:bg-[#E6EEE8] flex items-center justify-center text-[15px] font-bold text-[#1B2A22] transition"
                          >
                            ✕
                          </button>
                        </div>

                        {selected.hidden ? (
                          <div className="text-[14px] text-[#5C6E63]">
                            {selected.checks} checks: too few to show (under {overview.rules.hide_below_checks}).
                          </div>
                        ) : (
                          <>
                            {selected.faded && (
                              <div className="text-[12px] font-bold text-[#6B4E00] bg-[#FBEBB5] rounded-[12px] px-3 py-1.5">
                                Under {overview.rules.fade_below_checks} checks: read with care
                              </div>
                            )}
                            <div className="grid grid-cols-2 gap-2.5">
                              <div className="bg-[#DDF1E4] rounded-[20px] p-3.5 flex flex-col gap-0.5">
                                <div className="text-[12px] font-bold text-[#17573A]">Medium/High share</div>
                                <div className="text-[34px] font-extrabold text-[#17573A] leading-tight">
                                  {selected.medium_high_share?.toFixed(0)}%
                                </div>
                                <div className="text-[12px] text-[#17573A]">
                                  range {selected.range_low?.toFixed(0)}–{selected.range_high?.toFixed(0)}% ·{' '}
                                  {selected.checks.toLocaleString()} checks
                                </div>
                              </div>
                              <div className="bg-[#F3F8F4] rounded-[20px] p-3.5 flex flex-col gap-0.5">
                                <div className="text-[12px] font-bold text-[#5C6E63]">Coverage</div>
                                <div className="text-[34px] font-extrabold text-[#1B2A22] leading-tight">
                                  {selected.coverage_pct?.toFixed(2)}%
                                </div>
                                <div className="text-[12px] text-[#5C6E63]">
                                  checks ÷ {selected.adults.toLocaleString()} adults (PSA 2024 Census)
                                </div>
                              </div>
                            </div>

                            <div className="flex flex-col gap-2 border-t border-[#E6EEE8] pt-3.5">
                              <div className="flex justify-between items-baseline">
                                <div className="text-[14px] font-extrabold text-[#1B2A22]">Awareness gap</div>
                                <div className="text-[20px] font-extrabold text-[#1B2A22]">
                                  {selected.awareness_gap?.toFixed(0)}%
                                </div>
                              </div>
                              <div className="h-2.5 rounded-full bg-[#F3F8F4] overflow-hidden">
                                <div
                                  className="h-full bg-[#E8B92E] rounded-full transition-all duration-300"
                                  style={{ width: `${selected.awareness_gap ?? 0}%` }}
                                />
                              </div>
                              <div className="text-[12px] text-[#5C6E63]">
                                Answered "I don't know" to diabetes or high BP
                              </div>
                              <div className="text-[13px] font-extrabold text-[#17573A]">
                                Suggestion: a BP/sugar check-up drive
                              </div>
                            </div>

                            {selected.channel_split && (
                              <div className="flex flex-col gap-2 border-t border-[#E6EEE8] pt-3.5">
                                <div className="flex justify-between items-center">
                                  <div className="text-[14px] font-extrabold text-[#1B2A22]">Channel split</div>
                                  <Tag>illustrative</Tag>
                                </div>
                                <ChannelBar split={selected.channel_split} />
                                <div className="text-[12px] text-[#5C6E63]">
                                  {selected.last_synced
                                    ? `Field data last synced ${formatSynced(selected.last_synced)}`
                                    : 'No field checks in this area'}
                                </div>
                              </div>
                            )}
                          </>
                        )}
                      </div>

                      {!selected.hidden && (
                        <div className="bg-white rounded-[28px] p-[22px] flex flex-col gap-3 shadow-sm">
                          <div className="flex justify-between items-center">
                            <div className="text-[14px] font-extrabold text-[#1B2A22]">Over-represented vs province</div>
                            <Tag>illustrative</Tag>
                          </div>
                          {selected.factors ? (
                            <div className="flex flex-col gap-2.5">
                              {selected.factors.map((f) => (
                                <div
                                  key={f.label}
                                  className="grid grid-cols-[150px_minmax(0,1fr)_64px] gap-2.5 items-center text-[13px]"
                                  title={`${f.share.toFixed(1)}% of checks here`}
                                >
                                  <span className="font-bold text-[#1B2A22] truncate">{f.label}</span>
                                  <div className="h-2.5 rounded-full bg-[#F3F8F4] overflow-hidden">
                                    <div className="h-full bg-[#22A75A] rounded-full" style={{ width: `${f.share}%` }} />
                                  </div>
                                  <span className="font-extrabold text-right text-[#1B2A22]">{signedPts(f.difference_pts)}</span>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div className="text-[13px] text-[#5C6E63]">
                              Hidden: fewer than {overview.rules.factors_min_checks} checks.
                            </div>
                          )}
                        </div>
                      )}

                      {!selected.hidden && (
                        <div className="bg-white rounded-[22px] px-5 py-4 flex justify-between items-center shadow-sm">
                          <div className="flex flex-col">
                            <div className="text-[14px] font-extrabold text-[#1B2A22]">"Got tested" DONE replies</div>
                            <div className="text-[12px] text-[#5C6E63]">self-reported, SMS opt-ins only · illustrative</div>
                          </div>
                          <div className="text-[24px] font-extrabold text-[#1B2A22]">{selected.done_replies}</div>
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>

              {/* A1 P3: province totals */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                <div className="bg-white rounded-[22px] p-[18px] shadow-sm">
                  <div className="text-[12px] font-bold text-[#5C6E63]">Province checks</div>
                  <div className="text-[28px] font-extrabold text-[#1B2A22] mt-0.5">
                    {overview.summary.checks.toLocaleString()}
                  </div>
                  <div className="text-[12px] text-[#5C6E63]">Medium/High {overview.summary.medium_high_share.toFixed(0)}%</div>
                  {overview.summary.recorded_checks && (
                    <div className="text-[12px] text-[#17573A] font-bold">
                      incl. {overview.summary.recorded_checks.total} recorded (app/field)
                    </div>
                  )}
                </div>
                <div className="bg-white rounded-[22px] p-[18px] shadow-sm">
                  <div className="text-[12px] font-bold text-[#5C6E63]">Coverage</div>
                  <div className="text-[28px] font-extrabold text-[#1B2A22] mt-0.5">
                    {overview.summary.coverage_pct.toFixed(2)}%
                  </div>
                  <div className="text-[12px] text-[#5C6E63]">of {overview.summary.adults.toLocaleString()} adults</div>
                </div>
                <div className="bg-white rounded-[22px] p-[18px] shadow-sm">
                  <div className="text-[12px] font-bold text-[#5C6E63]">Awareness gap</div>
                  <div className="text-[28px] font-extrabold text-[#1B2A22] mt-0.5">
                    {overview.summary.awareness_gap.toFixed(0)}%
                  </div>
                </div>
                <div className="bg-white rounded-[22px] p-[18px] flex flex-col gap-2 shadow-sm">
                  <div className="flex justify-between items-center">
                    <div className="text-[12px] font-bold text-[#5C6E63]">Field · App · SMS</div>
                    <Tag>illustrative</Tag>
                  </div>
                  <ChannelBar split={overview.summary.channel_split} />
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: CLIMATE CONTEXT (A3) */}
          {activeTab === 'climate' && !error && (
            <div className="p-8 flex flex-col items-center">
              <div className="w-full max-w-[860px] bg-white rounded-[28px] p-6 flex flex-col gap-4 shadow-sm">
                <div className="flex flex-wrap justify-between items-center gap-3">
                  <div className="text-[26px] font-normal text-[#1B2A22]">
                    Climate · <span className="font-extrabold">{climateTown}</span>
                  </div>
                  <label className="relative">
                    <span className="sr-only">Municipality</span>
                    <select
                      value={climateTown}
                      onChange={(e) => selectTown(e.target.value)}
                      className="appearance-none pl-3.5 pr-8 py-2 rounded-full bg-[#F3F8F4] text-[13px] font-extrabold text-[#1B2A22] cursor-pointer"
                    >
                      {townNames.map((t) => (
                        <option key={t} value={t}>
                          {t}
                        </option>
                      ))}
                    </select>
                    <ChevronDown className="w-3.5 h-3.5 absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                  </label>
                </div>

                <div className="bg-[#E9F0FA] text-[#24405F] rounded-[18px] px-4 py-3 text-[13px] font-bold">
                  Context only: not used in the risk level · community-level estimate
                </div>

                {climateError && <div className="text-[13px] text-[#5C6E63]">{climateError}</div>}
                {climate && <ClimateChart climate={climate} />}
              </div>
            </div>
          )}

          {/* TAB 3: MODEL QUALITY (A4, for judges) */}
          {activeTab === 'model' && quality && <ModelQualityPanel quality={quality} />}
        </div>
      </div>
    </div>
  );
};

const ClimateChart: React.FC<{ climate: Climate }> = ({ climate }) => {
  const value = (v: number | null) => v ?? 0;
  const maxHot = Math.max(1, ...climate.series.map((s) => value(s.hot_days)));
  const maxRain = Math.max(1, ...climate.series.map((s) => value(s.rain_mm)));
  return (
    <>
      <div className="bg-[#F3F8F4] rounded-[24px] p-5 flex flex-col gap-4">
        <div className="flex flex-wrap gap-[18px] text-[12px] font-bold text-[#5C6E63]">
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-[3px] bg-[#F7C948]" /> Hot days (heat index ≥ {climate.heat_index_hot_c}°C;
            max {maxHot.toFixed(1)} days)
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-[3px] bg-[#A9C4E4]" /> Rainfall (mm per month, max {maxRain.toFixed(0)})
          </span>
        </div>
        <div className="grid grid-cols-12 gap-2 items-end h-[200px] pt-4">
          {climate.series.map((c) => (
            <div key={c.month} className="flex gap-1 items-end h-full">
              <div
                className="flex-1 bg-[#F7C948] rounded-t-[6px] min-h-[2px]"
                style={{ height: `${(100 * value(c.hot_days)) / maxHot}%` }}
                title={`${c.label} ${c.month.slice(0, 4)}: ${c.hot_days ?? 'no data'} hot days`}
              />
              <div
                className="flex-1 bg-[#A9C4E4] rounded-t-[6px]"
                style={{ height: `${(100 * value(c.rain_mm)) / maxRain}%` }}
                title={`${c.label} ${c.month.slice(0, 4)}: ${c.rain_mm ?? 'no data'} mm`}
              />
            </div>
          ))}
        </div>
        <div className="grid grid-cols-12 gap-2 text-[11px] font-bold text-[#5C6E63] text-center">
          {climate.series.map((c) => (
            <span key={c.month}>{c.label}</span>
          ))}
        </div>
        <div className="grid grid-cols-12 gap-2 text-[10.5px] text-[#5C6E63] text-center">
          {climate.series.map((c) => (
            <span
              key={c.month}
              title="Highest heat index in the month"
              className={c.peak_heat_index_c !== null && c.peak_heat_index_c >= climate.heat_index_hot_c ? 'font-extrabold text-[#B5552F]' : ''}
            >
              {c.peak_heat_index_c === null ? '–' : `${c.peak_heat_index_c.toFixed(1)}°`}
            </span>
          ))}
        </div>
      </div>
      <div className="text-[12px] leading-relaxed text-[#5C6E63]">
        Hot day: heat index of {climate.heat_index_hot_c}°C or more. Bottom row: the month's highest heat index. Source: ERA5-Land,{' '}
        {climate.period.label}.
      </div>
    </>
  );
};

const ModelQualityPanel: React.FC<{ quality: ModelQuality }> = ({ quality }) => {
  const rates = (a: ArmQuality) => a.abnormal_rate_pct.map((r) => r.toFixed(1)).join(' / ') + '%';
  const rows: Array<[string, string, string]> = [
    ['Abnormal screens caught by Medium/High', `${quality.agap.caught_pct.toFixed(1)}%`, `${quality.thai.caught_pct.toFixed(1)}%`],
    ['Abnormal rate · Low / Medium / High', rates(quality.agap), rates(quality.thai)],
    ['AUC', quality.agap.auroc.toFixed(3), quality.thai.auroc.toFixed(3)],
    ['Share at Medium or High', `${quality.agap.referred_pct.toFixed(1)}%`, `${quality.thai.referred_pct.toFixed(1)}%`],
  ];
  const maxRate = Math.max(...quality.prevalence_sensitivity.flatMap((p) => [p.high_rate_pct, p.target_rate_pct]));
  return (
    <div className="p-8 flex flex-col items-center">
      <div className="w-full max-w-[860px] bg-white rounded-[28px] p-6 flex flex-col gap-4 shadow-sm">
        <div className="flex flex-wrap justify-between items-center gap-2">
          <div className="text-[26px] font-normal text-[#1B2A22]">
            Model <span className="font-extrabold">vs benchmark</span>
          </div>
          <div className="text-[12px] font-bold text-[#5C6E63] font-mono">
            run {quality.run.config_fingerprint} · commit {quality.run.git_commit} · seed {quality.run.seed}
          </div>
        </div>

        <div className="border border-[#E6EEE8] rounded-[24px] px-5 py-2">
          <div className="grid grid-cols-[minmax(0,1fr)_150px_150px] gap-3 py-3 text-[12px] font-extrabold text-[#5C6E63] border-b border-[#E6EEE8]">
            <span>
              Same simulated people · {quality.cohort.toLowerCase()} ({quality.run.n_test.toLocaleString()})
            </span>
            <span className="text-right">AGAP model + floor</span>
            <span className="text-right">Thai simplified</span>
          </div>
          {rows.map(([label, agap, thai], i) => (
            <div
              key={label}
              className={`grid grid-cols-[minmax(0,1fr)_150px_150px] gap-3 py-3 text-[14px] ${
                i < rows.length - 1 ? 'border-b border-[#E6EEE8]' : ''
              }`}
            >
              <span className="font-bold text-[#1B2A22]">{label}</span>
              <span className="text-right font-extrabold text-[#17573A]">{agap}</span>
              <span className="text-right text-[#5C6E63]">{thai}</span>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="bg-[#F3F8F4] rounded-[24px] p-[18px] flex flex-col gap-2">
            <div className="text-[13px] font-extrabold text-[#1B2A22]">Cut-off rules</div>
            <div className="text-[13px] leading-relaxed text-[#3E5046]">{quality.cutoffs.rule}</div>
            <div className="text-[12px] text-[#5C6E63]">
              Medium at a predicted chance of {quality.cutoffs.medium.toFixed(3)} (catches {quality.cutoffs.validation_caught_pct}% on
              validation); High at {quality.cutoffs.high.toFixed(3)} (validation abnormal rate{' '}
              {quality.cutoffs.validation_high_rate_pct}%).
            </div>
            <div className="text-[13px] font-extrabold text-[#1B2A22] mt-1">Guideline floor</div>
            <div className="text-[13px] leading-relaxed text-[#3E5046]">
              {quality.floor
                ? `Changed ${quality.floor.changed} of ${quality.floor.n.toLocaleString()} test levels (${quality.floor.changed_pct}%): ${quality.floor.to_medium} raised to Medium, ${quality.floor.to_high} to High.`
                : 'Floor effect not computed for this build.'}
            </div>
          </div>

          <div className="bg-[#F3F8F4] rounded-[24px] p-[18px] flex flex-col gap-2">
            <div className="text-[13px] font-extrabold text-[#1B2A22]">Prevalence sensitivity · abnormal rate at High</div>
            <div className="flex gap-3 items-end h-[110px] pt-2">
              {quality.prevalence_sensitivity.map((ps) => (
                <div key={ps.target_prevalence_pct} className="flex-1 flex flex-col items-center gap-1 h-full justify-end relative">
                  <span className={`text-[12px] font-extrabold ${ps.meets_target ? 'text-[#1B2A22]' : 'text-[#B5552F]'}`}>
                    {ps.high_rate_pct.toFixed(0)}%
                  </span>
                  <div className="w-full relative" style={{ height: `${(100 * ps.high_rate_pct) / maxRate}%` }}>
                    <div className="absolute inset-0 bg-[#22A75A] rounded-t-[6px]" />
                  </div>
                  <div
                    className="absolute left-0 right-0 border-t-2 border-dashed border-[#1B2A22]"
                    style={{ bottom: `${(100 * ps.target_rate_pct) / maxRate}%` }}
                    title={`2× prevalence target: ${ps.target_rate_pct}%`}
                  />
                </div>
              ))}
            </div>
            <div className="flex gap-3 text-[11px] font-bold text-[#5C6E63] text-center">
              {quality.prevalence_sensitivity.map((ps) => (
                <span key={ps.target_prevalence_pct} className="flex-1">
                  {ps.target_prevalence_pct}%
                </span>
              ))}
            </div>
            <div className="text-[11.5px] text-[#5C6E63]">
              Dashed line: 2× the cohort's abnormal rate.{' '}
              {quality.prevalence_sensitivity.every((p) => p.meets_target)
                ? 'High meets it in every scenario.'
                : `High misses it at ${quality.prevalence_sensitivity
                    .filter((p) => !p.meets_target)
                    .map((p) => `${p.target_prevalence_pct}%`)
                    .join(', ')} prevalence.`}
            </div>
          </div>
        </div>

        <div className="text-[12px] leading-relaxed text-[#5C6E63]">
          Outcome: {quality.outcome} Prevalence: {quality.prevalence_source}
        </div>

        <details className="text-[12px] text-[#3E5046]">
          <summary className="cursor-pointer font-extrabold text-[#1B2A22]">Effect-size tags table</summary>
          <table className="w-full mt-2 border-collapse">
            <thead>
              <tr className="text-left text-[#5C6E63]">
                <th className="py-1 pr-2">Item</th>
                <th className="py-1 pr-2">Odds ratio</th>
                <th className="py-1 pr-2">Tag</th>
                <th className="py-1">Evidence</th>
              </tr>
            </thead>
            <tbody>
              {quality.effect_sizes.map((e) => (
                <tr key={e.item} className="border-t border-[#E6EEE8] align-top">
                  <td className="py-1.5 pr-2 font-bold">{e.item}</td>
                  <td className="py-1.5 pr-2">{e.odds_ratio}</td>
                  <td className="py-1.5 pr-2 whitespace-nowrap">{e.tag}</td>
                  <td className="py-1.5">{e.evidence}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      </div>
    </div>
  );
};
