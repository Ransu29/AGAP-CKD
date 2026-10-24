import React, { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, CheckCircle2, RefreshCw, UserPlus, Check, Info } from 'lucide-react';
import {
  DK,
  EDUCATION_CARDS,
  LEVEL_LINE,
  LEVEL_STYLE,
  NOT_A_DIAGNOSIS,
  REASON_TEXT,
  SAFETY_QUESTION,
  TIP_TEXT,
  YES_NO,
  monthYear,
  pruneBranches,
  questionsFor,
  type Answers,
  type RiskCheckResult,
} from '../riskCheck/content';

// PRD v3 field health worker tablet (F1–F3, docs/AGAP-CKD-Screen-Content-Plan.md). The worker runs the
// same pre-check, questions, model and floor as the app (ADR 0003) through /api/risk-check/evaluate,
// which runs on the device, so a check needs no internet. Only Sync needs a connection; the Online
// toggle simulates it. Checks are kept on the tablet with no names or ID numbers.

interface StoredCheck {
  number: string;
  at: string; // ISO time of the check
  municipality: string;
  barangay: string;
  outcome: 'Low' | 'Medium' | 'High' | 'See doctor' | 'Go to care';
  next_check: string | null;
  next_kidney_test: string | null;
  synced: boolean;
  answers: Answers & { safety: string };
}

interface Town {
  municipality: string;
  name: string;
}

type Screen = 'today' | 'consent' | 'education' | 'safety' | 'question' | 'result';

const CHECKS_KEY = 'agap-field-checks';
const SETTINGS_KEY = 'agap-field-settings';
const REMINDERS_KEY = 'agap-field-reminders';

const read = <T,>(key: string, fallback: T): T => {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
};
const write = (key: string, value: unknown) => {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable: the check still works for this session */
  }
};

const DAYS_TL = ['Linggo', 'Lunes', 'Martes', 'Miyerkules', 'Huwebes', 'Biyernes', 'Sabado'];
const MONTHS_TL = ['Ene', 'Peb', 'Mar', 'Abr', 'May', 'Hun', 'Hul', 'Ago', 'Set', 'Okt', 'Nob', 'Dis'];
const longDate = (d: Date) => `${DAYS_TL[d.getDay()]}, ${d.getDate()} ${MONTHS_TL[d.getMonth()]} ${d.getFullYear()}`;
const shortDate = (d: Date) => `${d.getDate()} ${MONTHS_TL[d.getMonth()]} ${d.getFullYear()}`;
const clock = (d: Date) => d.toLocaleTimeString('en-PH', { hour: 'numeric', minute: '2-digit' });
const thisMonth = () => new Date().toISOString().slice(0, 7);
const shortTown = (m: string) => m.replace('City of ', '').replace(' City', '');

const CONSENT = {
  Tagalog: [
    <>
      Magtatanong ako ng mga <span className="font-extrabold text-[#17573A]">12 maikling tanong</span> tungkol sa kalusugan mo,
      height at weight, at barangay mo.
    </>,
    <>
      Hindi ko itatanong ang pangalan mo. <span className="font-extrabold text-[#17573A]">Totals lang para sa bayan</span> ang
      makikita ng iba.
    </>,
    <>Hindi ito diagnosis. Puwede tayong huminto anumang oras.</>,
  ],
  English: [
    <>
      I will ask about <span className="font-extrabold text-[#17573A]">12 short questions</span> about your health, height and
      weight, and your barangay.
    </>,
    <>
      I will not ask your name. Others will only see <span className="font-extrabold text-[#17573A]">totals for the town</span>.
    </>,
    <>This is not a diagnosis. We can stop at any time.</>,
  ],
};

const OUTCOME_BADGE: Record<StoredCheck['outcome'], string> = {
  Low: 'bg-[#D6F0DF] text-[#17573A]',
  Medium: 'bg-[#FBEBB5] text-[#6B4E00]',
  High: 'bg-[#F9D3C8] text-[#8A2E1A]',
  'See doctor': 'bg-[#EBDCF9] text-[#552382]',
  'Go to care': 'bg-[#E3E8E4] text-[#3E5046]',
};

const bigAnswer =
  'w-full min-h-[76px] px-7 rounded-[26px] font-bold text-2xl text-left flex justify-between items-center transition border-2';
const primary =
  'py-5 px-8 rounded-full bg-[#22A75A] hover:bg-[#1c8c4a] text-white font-extrabold text-xl shadow-[0_10px_24px_rgba(34,167,90,0.3)] transition disabled:opacity-40 disabled:shadow-none';
const secondary = 'py-5 px-8 rounded-full bg-white text-[#1B2A22] font-bold text-xl border-2 border-[#DCE7DF] transition';
const backButton =
  'w-12 h-12 rounded-full bg-white flex items-center justify-center shadow-sm text-[#1B2A22] border border-[#DCE7DF] shrink-0';

export const FieldWorkerView: React.FC = () => {
  const [screen, setScreen] = useState<Screen>('today');
  const [online, setOnline] = useState(false);
  const [checks, setChecks] = useState<StoredCheck[]>(() => read(CHECKS_KEY, []));
  const [settings, setSettings] = useState<{ municipality: string; lastSynced: string | null }>(() =>
    read(SETTINGS_KEY, { municipality: 'City of Calamba', lastSynced: null })
  );
  const [towns, setTowns] = useState<Town[]>([]);
  const [barangays, setBarangays] = useState<string[]>([]);
  const [barangay, setBarangay] = useState('');
  const [language, setLanguage] = useState<'Tagalog' | 'English'>('Tagalog');
  const [agreed, setAgreed] = useState(false);
  const [safety, setSafety] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Answers>({});
  const [index, setIndex] = useState(0);
  const [showWhy, setShowWhy] = useState(false);
  const [result, setResult] = useState<RiskCheckResult | null>(null);
  const [current, setCurrent] = useState<StoredCheck | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [familyNumber, setFamilyNumber] = useState('');
  const [familyAgreed, setFamilyAgreed] = useState(false);

  useEffect(() => write(CHECKS_KEY, checks), [checks]);
  useEffect(() => write(SETTINGS_KEY, settings), [settings]);

  useEffect(() => {
    fetch('/api/risk-check/municipalities')
      .then((r) => (r.ok ? r.json() : []))
      .then(setTowns)
      .catch(() => setTowns([]));
  }, []);

  useEffect(() => {
    fetch(`/api/risk-check/barangays?municipality=${encodeURIComponent(settings.municipality)}`)
      .then((r) => (r.ok ? r.json() : []))
      .then((list: string[]) => {
        setBarangays(list);
        setBarangay((b) => (list.includes(b) ? b : ''));
      })
      .catch(() => setBarangays([]));
  }, [settings.municipality]);

  // The field check knows the town from the worker's area, so the town item is answered, not asked.
  const questions = useMemo(() => questionsFor(answers).filter((q) => q.key !== 'municipality'), [answers]);
  const question = questions[Math.min(index, questions.length - 1)];
  const today = new Date().toDateString();
  const todays = checks.filter((c) => new Date(c.at).toDateString() === today);
  const waiting = checks.filter((c) => !c.synced);
  const rechecksDue = checks.filter((c) => c.next_check === thisMonth()).length;
  const visited = Array.from(new Set(checks.filter((c) => c.municipality === settings.municipality).map((c) => c.barangay)));
  const nextNumber = String(checks.length + 1).padStart(3, '0');

  const startCheck = () => {
    setAgreed(false);
    setSafety(null);
    setAnswers({ municipality: settings.municipality });
    setIndex(0);
    setResult(null);
    setCurrent(null);
    setError(null);
    setFamilyNumber('');
    setFamilyAgreed(false);
    setScreen('consent');
  };

  const score = async (final: Answers, safetyAnswer: string) => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch('/api/risk-check/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          channel: 'field',
          safety: safetyAnswer,
          // A safety "Oo" ends the check before the questions; the service returns no level for it.
          age_group: final.age_group ?? '18-39',
          sex: final.sex ?? 'Female',
          municipality: settings.municipality,
          diabetes: final.diabetes ?? DK,
          high_blood_pressure: final.high_blood_pressure ?? DK,
          medicine: final.medicine ?? null,
          bp_reading: final.bp_reading ?? null,
          heart_disease_stroke: final.heart_disease_stroke ?? DK,
          kidney_stones: final.kidney_stones ?? DK,
          family_history: final.family_history ?? DK,
          height_cm: final.height_cm ?? null,
          weight_kg: final.weight_kg ?? null,
          heavy_outdoor_work: final.heavy_outdoor_work ?? DK,
          kidney_status: final.kidney_status ?? DK,
        }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Hindi ma-score ang check.');
      const outcome: StoredCheck['outcome'] =
        body.route === 'see_doctor' ? 'See doctor' : body.route === 'already_diagnosed' ? 'Go to care' : body.level;
      setResult(body);
      setCurrent({
        number: nextNumber,
        at: new Date().toISOString(),
        municipality: settings.municipality,
        barangay,
        outcome,
        next_check: body.next_step?.next_check ?? null,
        next_kidney_test: body.next_step?.next_kidney_test ?? null,
        synced: false,
        answers: { ...final, safety: safetyAnswer },
      });
      setScreen('result');
    } catch (err: any) {
      setError(err.message || 'Hindi ma-score ang check.');
    } finally {
      setBusy(false);
    }
  };

  const answer = (key: keyof Answers, value: any, extra: Partial<Answers> = {}) => {
    const next = pruneBranches({ ...answers, [key]: value, ...extra });
    setAnswers(next);
    setShowWhy(false);
    const list = questionsFor(next).filter((q) => q.key !== 'municipality');
    const position = list.findIndex((q) => q.key === key);
    if (position >= list.length - 1) score(next, safety ?? 'No');
    else setIndex(position + 1);
  };

  const finish = () => {
    if (current) {
      setChecks((all) => [...all, current]);
      if (familyAgreed && familyNumber.trim()) {
        // PRD v3: a number is kept only with consent, apart from the answers, with the last level only.
        const reminders = read<any[]>(REMINDERS_KEY, []);
        reminders.push({ number: familyNumber.trim(), level: current.outcome, saved_at: current.at });
        write(REMINDERS_KEY, reminders);
      }
    }
    setScreen('today');
  };

  const sync = async () => {
    if (!online || waiting.length === 0) return;
    setBusy(true);
    setNotice(null);
    try {
      const res = await fetch('/api/field/batch-sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          worker_id: 'field-tablet',
          checks: waiting.map(({ synced, ...c }) => ({ ...c, channel: 'field' })),
        }),
      });
      if (!res.ok) throw new Error();
      const now = new Date().toISOString();
      setChecks((all) => all.map((c) => ({ ...c, synced: true })));
      setSettings((s) => ({ ...s, lastSynced: now }));
      setNotice(`Na-sync ang ${waiting.length} check.`);
    } catch {
      setNotice('Hindi nakakonekta sa server. Naka-save pa rin ang mga check sa tablet.');
    } finally {
      setBusy(false);
    }
  };

  const noteLines = (): string[] => {
    if (!result || !current || !result.level) return [];
    const step = result.next_step!;
    const reason = result.reasons?.[0] ? REASON_TEXT[result.reasons[0]]?.(result).en : '';
    const where = result.where.facilities[0];
    const lines = [
      `AGAP Kidney Check · ${shortDate(new Date(current.at))} · Check #${current.number}`,
      `Result: ${result.level} chance of kidney problems. Not a diagnosis.`,
      reason ? `Main reason: ${reason}` : '',
      step.code === 'kidney_test'
        ? `Next: Simple blood and urine test for your kidneys${step.soon ? ' (soon)' : ''}`
        : 'Next: Get your BP and blood sugar checked at your health center first',
      where ? `Where: ${where.name}, ${shortTown(where.municipality)} (call ahead)` : '',
      step.next_kidney_test ? `Next kidney test: ${monthYear(step.next_kidney_test)}` : '',
    ];
    return lines.filter(Boolean);
  };

  return (
    <div className="flex justify-center items-center py-6 px-4">
      {/* 1180 × 820 tablet frame from AGAP-Field-Tablet-and-SMS.dc.html */}
      <div className="w-full max-w-[1180px] min-h-[760px] rounded-[32px] sm:rounded-[40px] border-[8px] sm:border-[12px] lg:border-[14px] border-[#1B2A22] bg-[#F3F8F4] shadow-2xl p-5 sm:p-7 font-['Nunito',sans-serif] text-[#1B2A22] flex flex-col">
        {/* F1 Today */}
        {screen === 'today' && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 flex-1">
            <div className="lg:col-span-8 flex flex-col gap-4">
              <div className="flex justify-between items-center gap-4 flex-wrap">
                <div>
                  <div className="text-sm font-bold text-[#5C6E63]">{longDate(new Date())}</div>
                  <h1 className="text-3xl font-normal leading-tight">
                    Mga check <span className="font-extrabold text-[#17573A]">ngayon</span>
                  </h1>
                </div>
                <button
                  onClick={() => {
                    setOnline(!online);
                    setNotice(null);
                  }}
                  className={`flex items-center gap-2 px-4 py-2 rounded-full font-extrabold text-sm border shadow-sm ${
                    online ? 'bg-[#D6F0DF] text-[#17573A] border-[#9FDDB6]' : 'bg-[#E3E8E4] text-[#3E5046] border-[#DCE7DF]'
                  }`}
                  title="Ginagaya ang internet connection para sa demo"
                >
                  <span className={`w-2.5 h-2.5 rounded-full ${online ? 'bg-[#22A75A]' : 'bg-[#93A199]'}`} />
                  {online ? 'Online' : 'Offline'}
                </button>
              </div>

              {notice && (
                <div className="p-3.5 bg-white border border-[#DCE7DF] rounded-[18px] text-sm font-bold text-[#17573A] flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-[#22A75A] shrink-0" />
                  {notice}
                </div>
              )}

              <div className="bg-white rounded-[28px] p-6 flex-1 flex flex-col border border-[#DCE7DF]/60">
                <div className="grid grid-cols-12 gap-3 pb-3 text-sm font-extrabold text-[#5C6E63] border-b border-[#E6EEE8]">
                  <span className="col-span-2">Check</span>
                  <span className="col-span-3">Oras</span>
                  <span className="col-span-4">Barangay</span>
                  <span className="col-span-3">Risk level</span>
                </div>
                {todays.length === 0 ? (
                  <div className="flex-1 flex items-center justify-center text-[#5C6E63] text-base py-10">
                    Wala pang check ngayon. Pindutin ang "Bagong check".
                  </div>
                ) : (
                  <div className="divide-y divide-[#E6EEE8]">
                    {[...todays].reverse().map((c) => (
                      <div key={c.number} className="grid grid-cols-12 gap-3 py-3.5 items-center text-base">
                        <span className="col-span-2 font-extrabold">#{c.number}</span>
                        <span className="col-span-3 text-[#3E5046]">{clock(new Date(c.at))}</span>
                        <span className="col-span-4">{c.barangay || shortTown(c.municipality)}</span>
                        <span className="col-span-3 flex items-center gap-2">
                          <span className={`px-3 py-1 rounded-full text-sm font-extrabold ${OUTCOME_BADGE[c.outcome]}`}>
                            {c.outcome === 'See doctor' ? 'Doktor' : c.outcome === 'Go to care' ? 'Sa doktor na' : c.outcome}
                          </span>
                          {!c.synced && <span className="w-2 h-2 rounded-full bg-[#E8B92E]" title="Hindi pa naka-sync" />}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="lg:col-span-4 flex flex-col gap-4">
              <div className="bg-[#1B2A22] text-white rounded-[28px] p-6 flex flex-col gap-3">
                <div className="text-sm font-bold text-[#B9D9C6]">Naka-save sa tablet</div>
                <div className="text-lg">
                  <span className="font-extrabold text-4xl">{waiting.length}</span> check{waiting.length === 1 ? '' : 's'} waiting to sync
                </div>
                <button
                  onClick={sync}
                  disabled={!online || waiting.length === 0 || busy}
                  className="py-3.5 rounded-full bg-[#22A75A] text-white font-extrabold flex items-center justify-center gap-2 disabled:bg-[#3E5046] disabled:text-[#B9D9C6]"
                >
                  <RefreshCw className={`w-4 h-4 ${busy ? 'animate-spin' : ''}`} />
                  {online ? 'Sync' : 'Sync · kailangan ng internet'}
                </button>
                <div className="text-xs text-[#B9D9C6]">
                  Huling sync: {settings.lastSynced ? `${shortDate(new Date(settings.lastSynced))}, ${clock(new Date(settings.lastSynced))}` : 'wala pa'}
                </div>
              </div>

              <div className="bg-white rounded-[28px] p-5 border border-[#DCE7DF]/60">
                <div className="text-sm font-bold text-[#5C6E63]">Re-checks due ngayong buwan sa mga area mo</div>
                <div className="text-4xl font-extrabold mt-1">{rechecksDue}</div>
              </div>

              <div className="bg-white rounded-[28px] p-5 border border-[#DCE7DF]/60 space-y-3">
                <label className="block text-sm font-bold text-[#5C6E63]" htmlFor="worker-town">
                  Bayan na pinupuntahan
                </label>
                <select
                  id="worker-town"
                  value={settings.municipality}
                  onChange={(e) => setSettings((s) => ({ ...s, municipality: e.target.value }))}
                  className="w-full p-3 rounded-[16px] bg-[#F3F8F4] border border-[#DCE7DF] font-bold"
                >
                  {towns.map((t) => (
                    <option key={t.municipality} value={t.municipality}>
                      {t.name}
                    </option>
                  ))}
                </select>
                <div className="text-sm font-bold text-[#5C6E63]">Mga barangay mo</div>
                <div className="flex flex-wrap gap-2">
                  {visited.length === 0 ? (
                    <span className="text-sm text-[#5C6E63]">Wala pa</span>
                  ) : (
                    visited.map((b) => (
                      <span key={b} className="px-3 py-1 rounded-full bg-[#DDF1E4] text-[#17573A] text-sm font-bold">
                        {b}
                      </span>
                    ))
                  )}
                </div>
              </div>

              <button onClick={startCheck} className={`${primary} flex items-center justify-center gap-2`}>
                <UserPlus className="w-6 h-6" /> Bagong check
              </button>
              {checks.length > 0 && (
                <button
                  className="text-xs font-bold text-[#5C6E63] underline"
                  onClick={() => {
                    if (window.confirm('Burahin ang lahat ng check sa tablet na ito? (demo)')) {
                      setChecks([]);
                      setSettings((s) => ({ ...s, lastSynced: null }));
                      write(REMINDERS_KEY, []);
                    }
                  }}
                >
                  I-reset ang demo tablet
                </button>
              )}
            </div>
          </div>
        )}

        {/* F2 Consent script */}
        {screen === 'consent' && (
          <div className="flex flex-col gap-6 flex-1 animate-fadeIn">
            <div className="flex justify-between items-center gap-4 flex-wrap">
              <div className="flex items-center gap-3">
                <button onClick={() => setScreen('today')} className={backButton} aria-label="Bumalik">
                  <ArrowLeft className="w-5 h-5" />
                </button>
                <span className="text-lg font-bold text-[#5C6E63]">Check #{nextNumber} · Basahin nang malakas</span>
              </div>
              <div className="flex gap-1 bg-white rounded-full p-1 border border-[#DCE7DF]">
                {(['Tagalog', 'English'] as const).map((l) => (
                  <button
                    key={l}
                    onClick={() => setLanguage(l)}
                    className={`px-4 py-1.5 rounded-full text-sm font-bold ${language === l ? 'bg-[#1B2A22] text-white' : 'text-[#5C6E63]'}`}
                  >
                    {l}
                  </button>
                ))}
              </div>
            </div>

            <div className="bg-white rounded-[32px] p-8 flex-1 border border-[#DCE7DF]/60 space-y-5">
              {CONSENT[language].map((line, i) => (
                <p key={i} className="text-2xl lg:text-3xl leading-relaxed">
                  "{line}"
                </p>
              ))}
              <div className="text-xs text-[#5C6E63] border-t border-[#E6EEE8] pt-3">Draft script · for native-speaker review · RA 10173</div>
            </div>

            <div className="flex gap-4 items-center flex-wrap">
              <label className="flex items-center gap-3 text-lg font-bold">
                Barangay ng check:
                <select
                  value={barangay}
                  onChange={(e) => setBarangay(e.target.value)}
                  className="p-3 rounded-[16px] bg-white border border-[#DCE7DF] font-bold text-base"
                >
                  <option value="">Pumili</option>
                  {barangays.map((b) => (
                    <option key={b} value={b}>
                      {b}
                    </option>
                  ))}
                </select>
                <span className="text-sm text-[#5C6E63]">{shortTown(settings.municipality)}</span>
              </label>
            </div>

            <div className="flex gap-4 items-center flex-wrap">
              <button
                onClick={() => setAgreed(!agreed)}
                aria-pressed={agreed}
                className={`flex-1 min-w-[260px] py-5 px-6 rounded-full border-2 font-extrabold text-xl flex items-center justify-center gap-3 transition ${
                  agreed ? 'bg-[#DDF1E4] border-[#22A75A] text-[#17573A]' : 'bg-white border-[#DCE7DF] text-[#3E5046]'
                }`}
              >
                <span
                  className={`w-8 h-8 rounded-lg flex items-center justify-center ${agreed ? 'bg-[#22A75A] text-white' : 'border-2 border-[#9FB5A6]'}`}
                >
                  {agreed && <Check className="w-5 h-5" />}
                </span>
                Pumayag ang resident
              </button>
              <button onClick={() => setScreen('education')} className={secondary}>
                Hindi pumayag
              </button>
              <button onClick={() => setScreen('safety')} disabled={!agreed || !barangay} className={primary}>
                Ituloy
              </button>
            </div>
            {!barangay && <p className="text-sm text-[#5C6E63] -mt-3">Pumili muna ng barangay.</p>}
          </div>
        )}

        {/* C8 for a resident who declined */}
        {screen === 'education' && (
          <div className="flex flex-col gap-5 flex-1 animate-fadeIn">
            <h2 className="text-3xl font-extrabold">Tungkol sa kidneys</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 flex-1">
              {EDUCATION_CARDS.map((line) => (
                <div key={line} className="p-6 rounded-[28px] bg-white border border-[#DCE7DF] text-2xl leading-snug">
                  {line}
                </div>
              ))}
              <div className="p-6 rounded-[28px] bg-[#DDF1E4] text-2xl leading-snug">
                <div className="font-extrabold mb-1">Sino ang dapat magpa-kidney test?</div>
                Ang may diabetes, may high blood pressure, o edad 60 pataas.
              </div>
            </div>
            <div className="flex gap-4">
              <button onClick={() => setScreen('today')} className={primary}>
                Bumalik sa Today
              </button>
            </div>
          </div>
        )}

        {/* C4 Safety pre-check, large layout */}
        {screen === 'safety' && (
          <div className="flex flex-col gap-6 flex-1 animate-fadeIn">
            <div className="flex items-center gap-3">
              <button onClick={() => setScreen('consent')} className={backButton} aria-label="Bumalik">
                <ArrowLeft className="w-5 h-5" />
              </button>
              <span className="text-lg font-bold text-[#5C6E63]">Safety question · Check #{nextNumber}</span>
            </div>
            <h2 className="text-[40px] leading-[1.2] font-normal max-w-[960px]">{SAFETY_QUESTION}</h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-auto">
              {YES_NO.map((o) => (
                <button
                  key={o.value}
                  disabled={busy}
                  onClick={() => {
                    setSafety(o.value);
                    if (o.value === 'Yes') score(answers, 'Yes');
                    else {
                      setIndex(0);
                      setScreen('question');
                    }
                  }}
                  className={`${bigAnswer} ${o.value === DK ? 'border-dashed border-[#9FB5A6] bg-transparent text-[#3E5046]' : 'bg-white border-[#DCE7DF]'}`}
                >
                  {o.label}
                </button>
              ))}
            </div>
            {error && <p className="text-base text-[#8A2E1A]">{error}</p>}
          </div>
        )}

        {/* F2b Check: same questions as C5, larger */}
        {screen === 'question' && question && (
          <div className="flex flex-col gap-5 flex-1 animate-fadeIn">
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <button
                  onClick={() => (index === 0 ? setScreen('safety') : setIndex(index - 1))}
                  className={backButton}
                  aria-label="Bumalik"
                >
                  <ArrowLeft className="w-5 h-5" />
                </button>
                <span className="text-lg font-bold text-[#5C6E63]">
                  {index + 1} sa {questions.length}
                </span>
              </div>
              <span className="text-lg font-bold text-[#5C6E63]">
                {question.section} · Check #{nextNumber}
              </span>
            </div>
            <div className="h-2 rounded-full bg-[#DCE7DF] overflow-hidden">
              <div className="h-full bg-[#22A75A] transition-all" style={{ width: `${(100 * (index + 1)) / questions.length}%` }} />
            </div>
            {safety === DK && index === 0 && (
              <p className="text-base text-[#6B4E00] bg-[#FBEBB5] rounded-[16px] px-4 py-2 w-fit">
                Kung mapansin ng resident ang mga palatandaang iyon, magpatingin sa doktor.
              </p>
            )}
            <h2 className="text-[40px] leading-[1.18] font-normal max-w-[980px]">
              {question.emphasis ? (
                <>
                  {question.text.split(question.emphasis)[0]}
                  <span className="font-extrabold">{question.emphasis}</span>
                  {question.text.split(question.emphasis)[1]}
                </>
              ) : (
                question.text
              )}
            </h2>
            <button className="text-base font-bold text-[#17573A] flex items-center gap-1.5 w-fit" onClick={() => setShowWhy(!showWhy)}>
              <Info className="w-4 h-4" /> Bakit namin tinatanong{showWhy ? ':' : '?'}
              {showWhy && <span className="font-normal text-[#3E5046]">{question.why}</span>}
            </button>

            <div className="mt-auto">
              {error && <p className="text-base text-[#8A2E1A] mb-3">{error}</p>}
              {question.kind === 'height_weight' ? (
                <HeightWeight onDone={(h, w) => answer('height_cm', h, { weight_kg: w })} />
              ) : (
                <div className={`grid gap-4 ${question.options!.length > 3 ? 'grid-cols-1 md:grid-cols-2' : 'grid-cols-1 md:grid-cols-3'}`}>
                  {question.options!.map((o) => {
                    const chosen = answers[question.key] === o.value;
                    return (
                      <button
                        key={o.value}
                        disabled={busy}
                        onClick={() => answer(question.key, o.value)}
                        className={`${bigAnswer} ${
                          chosen
                            ? 'bg-[#22A75A] border-[#22A75A] text-white'
                            : o.value === DK
                            ? 'border-dashed border-[#9FB5A6] bg-transparent text-[#3E5046]'
                            : 'bg-white border-[#DCE7DF]'
                        }`}
                      >
                        {o.label}
                        {chosen && <Check className="w-6 h-6" />}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        )}

        {/* F3 Result and referral note */}
        {screen === 'result' && result && current && (
          <div className="flex flex-col gap-5 flex-1 animate-fadeIn">
            {result.route !== 'result' ? (
              <div className="bg-white rounded-[32px] p-8 border border-[#DCE7DF] space-y-4 flex-1">
                <h2 className="text-4xl font-extrabold text-[#8A2E1A]">
                  {result.route === 'see_doctor'
                    ? 'Magpatingin sa doktor sa lalong madaling panahon.'
                    : 'Patuloy na magpatingin sa doktor tungkol sa kidneys.'}
                </h2>
                <p className="text-xl text-[#3E5046]">
                  {result.route === 'see_doctor'
                    ? 'Dahil sa sagot sa safety question, hindi na itinuloy ang mga tanong. Kailangan ito ng check ng doktor.'
                    : 'May sinabi nang problema sa kidneys, kaya walang risk level. Ituloy ang pagpapatingin.'}
                </p>
                {result.where.facilities[0] && (
                  <p className="text-2xl font-bold">
                    {result.where.facilities[0].name}, {shortTown(result.where.facilities[0].municipality)}{' '}
                    <span className="text-[#8A6A00] text-lg">(hindi pa verified, tumawag muna)</span>
                  </p>
                )}
              </div>
            ) : (
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 flex-1">
                <div className="lg:col-span-5 flex flex-col gap-4">
                  <div className={`rounded-[32px] p-7 space-y-3 ${LEVEL_STYLE[result.level!].band} ${LEVEL_STYLE[result.level!].text}`}>
                    <div className="inline-flex items-center gap-2 px-5 py-2 rounded-full bg-white font-extrabold text-xl">
                      <span className="w-4 h-4 rounded-full" style={{ backgroundColor: LEVEL_STYLE[result.level!].dot }} />
                      {result.level}
                    </div>
                    <p className="text-2xl leading-snug">{LEVEL_LINE[result.level!]}</p>
                    <p className="text-base font-bold">{NOT_A_DIAGNOSIS}</p>
                  </div>
                  <div className="bg-white rounded-[28px] p-5 border border-[#DCE7DF]">
                    <div className="text-sm font-extrabold text-[#5C6E63] mb-2">Tips</div>
                    <ul className="space-y-1.5 text-lg">
                      {(result.tips || []).slice(0, 3).map((t) => (
                        <li key={t}>· {TIP_TEXT[t]}</li>
                      ))}
                    </ul>
                  </div>
                  <div className="bg-white rounded-[28px] p-5 border border-[#DCE7DF] space-y-2">
                    <div className="text-sm font-extrabold text-[#5C6E63]">Optional · paalala sa kapamilya</div>
                    <input
                      value={familyNumber}
                      onChange={(e) => setFamilyNumber(e.target.value)}
                      inputMode="tel"
                      placeholder="09XX XXX XXXX"
                      className="w-full p-3 rounded-[16px] bg-[#F3F8F4] border border-[#DCE7DF] font-bold text-lg"
                    />
                    <label className="flex items-center gap-2 text-base font-bold">
                      <input type="checkbox" checked={familyAgreed} onChange={(e) => setFamilyAgreed(e.target.checked)} className="w-5 h-5" />
                      Pumayag ang kapamilya
                    </label>
                    <p className="text-xs text-[#5C6E63]">Itinatago lang kung pumayag, hiwalay sa mga sagot. Hindi pa nagpapadala ng SMS ang prototype.</p>
                  </div>
                </div>

                <div className="lg:col-span-7">
                  {result.level === 'Low' ? (
                    <div className="bg-white rounded-[32px] p-8 border-2 border-[#9FDDB6] h-full flex flex-col justify-center gap-3">
                      <div className="text-xl font-bold text-[#5C6E63]">Isulat ng resident:</div>
                      <div className="text-5xl font-extrabold text-[#17573A]">Next check: {monthYear(result.next_step?.next_check)}</div>
                      {result.blood_sugar_prompt && <div className="text-2xl font-bold text-[#6B4E00]">Magpa-check din ng blood sugar.</div>}
                    </div>
                  ) : (
                    <div className="bg-white rounded-[32px] p-8 border-2 border-dashed border-[#1B2A22] h-full space-y-3">
                      <div className="text-sm font-extrabold text-[#5C6E63] uppercase tracking-wider">Referral note · kopyahin sa papel</div>
                      {noteLines().map((line, i) => (
                        <p key={i} className={`${i === 0 ? 'text-lg text-[#5C6E63] font-bold' : 'text-2xl'} leading-snug`}>
                          {line}
                        </p>
                      ))}
                      {result.blood_sugar_prompt && <p className="text-xl font-bold text-[#6B4E00]">Also: get your blood sugar checked.</p>}
                    </div>
                  )}
                </div>
              </div>
            )}

            <div className="flex gap-4 flex-wrap">
              <button onClick={finish} className={`${primary} flex-1`}>
                Tapos, bumalik sa Today
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

const HeightWeight: React.FC<{ onDone: (heightCm: number | null, weightKg: number | null) => void }> = ({ onDone }) => {
  const [metric, setMetric] = useState(true);
  const [a, setA] = useState('');
  const [b, setB] = useState('');
  const [c, setC] = useState('');
  const height = metric ? Number(a) : (Number(a) * 12 + Number(b || 0)) * 2.54;
  const weight = metric ? Number(b) : Number(c) * 0.453592;
  const valid = height >= 100 && height <= 230 && weight >= 25 && weight <= 300;
  const input = 'w-full p-5 rounded-[22px] bg-white border-2 border-[#DCE7DF] font-bold text-2xl';
  return (
    <div className="space-y-4">
      <div className="flex gap-1 bg-white rounded-full p-1 border border-[#DCE7DF] w-fit">
        {[
          ['cm · kg', true],
          ['ft · in · lb', false],
        ].map(([label, isMetric]) => (
          <button
            key={String(label)}
            onClick={() => {
              setMetric(Boolean(isMetric));
              setA('');
              setB('');
              setC('');
            }}
            className={`px-5 py-2 rounded-full text-base font-bold ${metric === isMetric ? 'bg-[#1B2A22] text-white' : 'text-[#3E5046]'}`}
          >
            {label}
          </button>
        ))}
      </div>
      <div className={`grid gap-4 ${metric ? 'grid-cols-2' : 'grid-cols-3'}`}>
        <input className={input} inputMode="numeric" placeholder={metric ? 'Height (cm)' : 'ft'} value={a} onChange={(e) => setA(e.target.value)} />
        <input className={input} inputMode="numeric" placeholder={metric ? 'Weight (kg)' : 'in'} value={b} onChange={(e) => setB(e.target.value)} />
        {!metric && <input className={input} inputMode="numeric" placeholder="lb" value={c} onChange={(e) => setC(e.target.value)} />}
      </div>
      {valid && (
        <p className="text-lg text-[#5C6E63]">
          {Math.round(height)} cm, {Math.round(weight)} kg. Tama ba?
        </p>
      )}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <button className={primary} disabled={!valid} onClick={() => onDone(Math.round(height * 10) / 10, Math.round(weight * 10) / 10)}>
          Susunod
        </button>
        <button className={`${bigAnswer} border-dashed border-[#9FB5A6] bg-transparent text-[#3E5046] justify-center`} onClick={() => onDone(null, null)}>
          Hindi ko alam
        </button>
      </div>
    </div>
  );
};
