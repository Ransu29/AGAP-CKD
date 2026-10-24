import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, Check, MapPin as Hospital, ArrowCounterClockwise as RotateCcw, Warning } from '../components/PhosphorIcons';

import { emptyCitizenForm, ageError, evaluationPayload, isUnderAge, stepAnswered, stepsFor } from './citizenForm';
import type { CitizenForm, StepId } from './citizenForm';
import { CitizenHome, CitizenConsent } from './CitizenEntry';
import { CitizenLearn, CitizenCare } from './CitizenResources';
import { CitizenSelect } from '../components/CitizenSelect';
import { DK, QUESTIONS, REASON_TEXT, TIP_TEXT, monthYear, type RiskCheckResult } from '../riskCheck/content';

// PRD v3 citizen check-in (C1–C9). Scored by /api/risk-check/evaluate, the same model, cut-offs and guideline
// floor as the field tablet and the analyst map (ADR 0003). The score itself is never shown (PRD v3, l. 73).

interface Town {
  municipality: string;
  name: string;
}

// Care routes carry no risk level (PRD v3: safety pre-check, already diagnosed).
type CareRoute = 'see_doctor' | 'already_diagnosed';

const NOT_A_DIAGNOSIS = 'Hindi ito diagnosis. Blood at urine test lang ang makakapag-check ng kidneys mo.';

const SECTION: Record<StepId, string> = {
  age_sex: 'Pangunahing Impormasyon',
  municipality: 'Lokasyon',
  diabetes: 'Health history',
  high_blood_pressure: 'Health history',
  medicine: 'Health history',
  bp_reading: 'Vitals',
  heart_disease_stroke: 'Health history',
  kidney_stones: 'Health history',
  family_history: 'Kasaysayan sa Pamilya',
  height_weight: 'Height at weight',
  heavy_outdoor_work: 'Trabaho at Pamumuhay',
  kidney_status: 'Kidneys',
};

const question = (key: string) => QUESTIONS.find((q) => q.key === key)!;

export const CitizenView: React.FC = () => {
  // Screens: -1 consent; 0 dashboard; 1 safety pre-check; 2 questions; 9 result; 10 Learn; 11 Care.
  const citizenRoot = useRef<HTMLDivElement>(null);
  const previousStep = useRef(0);
  const [consentAccepted, setConsentAccepted] = useState(false);
  const [currentStep, setCurrentStep] = useState<number>(0);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [showExplanation, setShowExplanation] = useState(false);
  const [showFacilities, setShowFacilities] = useState(false);
  const [loading, setLoading] = useState(false);
  const [towns, setTowns] = useState<Town[]>([]);

  const [form, setForm] = useState<CitizenForm>(emptyCitizenForm);
  const [ageTouched, setAgeTouched] = useState(false);
  const [evaluationUnavailable, setEvaluationUnavailable] = useState(false);
  const [careRoute, setCareRoute] = useState<CareRoute | null>(null);

  const [evaluatedAt, setEvaluatedAt] = useState<string | null>(null);
  const [result, setResult] = useState<RiskCheckResult | null>(null);

  const steps = useMemo(() => stepsFor(form), [form]);
  const step = steps[Math.min(questionIndex, steps.length - 1)];

  useEffect(() => {
    if (previousStep.current !== currentStep) {
      citizenRoot.current?.querySelector<HTMLElement>('h1')?.focus();
      previousStep.current = currentStep;
    }
  }, [currentStep, questionIndex]);

  useEffect(() => {
    fetch('/api/risk-check/municipalities')
      .then((res) => (res.ok ? res.json() : []))
      .then(setTowns)
      .catch(() => setTowns([]));
  }, []);

  const showCareRoute = (route: CareRoute) => {
    setCareRoute(route);
    setResult(null);
    setEvaluationUnavailable(false);
    setEvaluatedAt(new Date().toISOString());
    setCurrentStep(9);
  };

  const handleEvaluate = async () => {
    if (loading || !consentAccepted) return;
    if (form.safety === true) return showCareRoute('see_doctor');
    if (isUnderAge(form)) return showCareRoute('see_doctor');
    const payload = evaluationPayload(form);
    if (!payload) {
      setEvaluationUnavailable(true);
      setResult(null);
      setCareRoute(null);
      setCurrentStep(9);
      return;
    }
    setEvaluationUnavailable(false);
    setLoading(true);
    try {
      const res = await fetch('/api/risk-check/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error('Evaluation unavailable');
      const data: RiskCheckResult = await res.json();
      setEvaluatedAt(new Date().toISOString());
      if (data.route !== 'result') {
        setCareRoute(data.route);
        setResult(data);
      } else {
        setCareRoute(null);
        setResult(data);
      }
      setCurrentStep(9);
    } catch (err) {
      console.error('Failed to score:', err);
      setEvaluationUnavailable(true);
      setResult(null);
      setCurrentStep(9);
    } finally {
      setLoading(false);
    }
  };

  const handleNext = () => {
    if (!stepAnswered(step, form) || loading) return;
    setShowExplanation(false);
    // An age under 18 is part of the safety pre-check: no further questions.
    if (step === 'age_sex' && isUnderAge(form)) return showCareRoute('see_doctor');
    if (questionIndex < steps.length - 1) setQuestionIndex(questionIndex + 1);
    else handleEvaluate();
  };

  const handleBack = () => {
    setShowExplanation(false);
    if (currentStep === 2 && questionIndex > 0) setQuestionIndex(questionIndex - 1);
    else if (currentStep === 2) setCurrentStep(1);
    else if (currentStep === 1) setCurrentStep(-1);
  };

  const resetAll = () => {
    setCurrentStep(0);
    setQuestionIndex(0);
    setConsentAccepted(false);
    setForm(emptyCitizenForm());
    setAgeTouched(false);
    setEvaluationUnavailable(false);
    setCareRoute(null);
    setResult(null);
    setEvaluatedAt(null);
    setShowFacilities(false);
  };

  const set = (patch: Partial<CitizenForm>) => {
    const next = { ...form, ...patch };
    // Branch answers that no longer apply are cleared, so they never reach the model.
    if (!(next.diabetes === 'Yes' || next.high_blood_pressure === 'Yes')) next.medicine = '';
    if (next.high_blood_pressure === 'Yes') next.bp_reading = '';
    setForm(next);
  };

  // One short next-step line for the dashboard (the full result has the rest).
  const nextLine = (r: RiskCheckResult) => {
    const s = r.next_step;
    if (!s) return undefined;
    if (s.code === 'recheck') return `Sagutin ulit · Next check: ${monthYear(s.next_check)}`;
    if (s.code === 'bp_sugar_first') return 'Magpa-check muna ng BP at blood sugar';
    return `Magpa-blood at urine test${s.soon ? ' agad' : ''} · Next kidney test: ${monthYear(s.next_kidney_test)}`;
  };
  const dashboardSummary = careRoute
    ? { risk_level: 'Doctor Referral' }
    : result?.level
    ? { risk_level: result.level, next: nextLine(result) }
    : null;

  const choiceButton = (selected: boolean, dontKnow: boolean) =>
    dontKnow
      ? `w-full p-4 rounded-[22px] font-bold text-base text-[#3E5046] border-[1.5px] border-dashed border-[#9FB5A6] bg-transparent text-center hover:bg-[#DDF1E4]/30 transition ${
          selected ? 'bg-[#DDF1E4]/60' : ''
        }`
      : `w-full p-4 rounded-[22px] font-bold text-base flex justify-between items-center transition shadow-sm ${
          selected ? 'bg-[#1B2A22] text-white' : 'bg-white text-[#1B2A22] hover:bg-slate-50'
        }`;

  const renderChoices = (key: Exclude<StepId, 'age_sex' | 'municipality' | 'height_weight'>) => {
    const q = question(key);
    return (
      <div className="space-y-3 pt-2">
        <div className="text-sm font-semibold text-[#5C6E63] uppercase">{SECTION[key]}</div>
        <h1 tabIndex={-1} className="text-[28px] leading-[1.2] font-normal">
          {q.emphasis ? (
            <>
              {q.text.split(q.emphasis)[0]}
              <span className="font-extrabold text-[#17573A]">{q.emphasis}</span>
              {q.text.split(q.emphasis)[1]}
            </>
          ) : (
            q.text
          )}
        </h1>
        <button
          aria-expanded={showExplanation}
          aria-controls={showExplanation ? 'citizen-explanation' : undefined}
          onClick={() => setShowExplanation(!showExplanation)}
          className="text-sm font-bold text-[#17573A] underline block"
        >
          Bakit namin tinatanong?
        </button>
        {showExplanation && (
          <div id="citizen-explanation" className="p-3 bg-[#DDF1E4] rounded-[16px] text-sm text-[#17573A] leading-relaxed">
            {q.why}
          </div>
        )}
        <div className="space-y-2 pt-3">
          {q.options!.map((o) => {
            const selected = form[key] === o.value;
            return (
              <button key={o.value} onClick={() => set({ [key]: o.value } as Partial<CitizenForm>)} aria-pressed={selected}
                className={choiceButton(selected, o.value === DK)}>
                {o.value === DK ? (
                  <>
                    {o.label} {selected && <Check aria-hidden="true" className="inline w-4 h-4 ml-2" />}
                  </>
                ) : (
                  <>
                    <span>{o.label}</span>
                    {selected && <Check aria-hidden="true" className="w-4 h-4 shrink-0" />}
                  </>
                )}
              </button>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <div ref={citizenRoot} lang="fil" role="region" aria-label="AGAP-CKD para sa mamamayan"
      className="citizen-view flex justify-center items-center py-6 px-4">
      <p className="sr-only" aria-live="polite" aria-atomic="true">{loading ? 'Ipinapadala ang mga sagot. Mangyaring maghintay.' : ''}</p>
      {/* 1a Mint Calm Mobile Phone Simulator Frame */}
      <div className="w-full max-w-[390px] min-h-[760px] rounded-[44px] bg-[#F3F8F4] border-[10px] border-[#1B2A22] shadow-2xl flex flex-col relative overflow-hidden font-['Nunito',sans-serif] text-[#1B2A22]">

        {currentStep === 0 && <CitizenHome onStart={() => {
          setConsentAccepted(false);
          setCurrentStep(-1);
        }} onLearn={() => setCurrentStep(10)} onCare={() => setCurrentStep(11)}
          onDetails={() => setCurrentStep(9)} summary={dashboardSummary} unavailable={evaluationUnavailable} evaluatedAt={evaluatedAt} />}
        {currentStep === 10 && <CitizenLearn onBack={() => setCurrentStep(0)} />}
        {currentStep === 11 && <CitizenCare onBack={() => setCurrentStep(0)} />}
        {currentStep === -1 && <CitizenConsent
          onAccept={() => { setConsentAccepted(true); setQuestionIndex(0); setCurrentStep(1); }}
          onDecline={() => { setConsentAccepted(false); setCurrentStep(0); }}
        />}

        {/* C4: Safety Pre-check */}
        {consentAccepted && currentStep === 1 && (
          <div className="flex-1 flex flex-col p-6 justify-between animate-fadeIn">
            <div className="space-y-4 pt-2">
              <div className="flex items-center justify-between">
                <button
                  aria-label="Bumalik sa nakaraang screen"
                  onClick={handleBack}
                  className="w-11 h-11 shrink-0 rounded-full bg-white flex items-center justify-center shadow-sm text-[#1B2A22]"
                >
                  <ArrowLeft aria-hidden="true" className="w-4 h-4" />
                </button>
                <span className="text-sm font-bold text-[#8A2E1A] uppercase tracking-wider">Unang Pagsusuri</span>
              </div>

              <div className="text-sm font-semibold text-[#5C6E63]"><span lang="en">Safety Pre-Check</span></div>
              <h1 tabIndex={-1} className="text-[28px] leading-[1.2] font-normal">
                Buntis ka ba, wala pang 18, o may <span className="font-extrabold text-[#8A2E1A]">pamamaga</span> ng mukha/binti, mabula o may dugong ihi, o kaunting-kaunti ang ihi?
              </h1>
              <p className="text-sm text-[#5C6E63]">
                Ang mga palatandaang ito ay nangangailangan ng agarang tingin ng doktor bago mag-questionnaire.
              </p>
            </div>

            <div className="space-y-3 pb-4">
              <button
                onClick={() => setForm({ ...form, safety: true })}
                aria-pressed={form.safety === true}
                className="w-full p-5 rounded-[24px] bg-[#F9D3C8] text-[#8A2E1A] font-bold text-left shadow-sm flex items-center justify-between hover:opacity-90 transition"
              >
                <div>
                  <div className="text-base font-extrabold">Oo, May Nararanasan</div>
                  <div className="text-sm font-medium text-[#8A2E1A]/80">O kaya'y buntis o menor de edad</div>
                </div>
                {form.safety === true && <Check aria-hidden="true" className="w-4 h-4" />}
              </button>

              <button
                onClick={() => setForm({ ...form, safety: false })}
                aria-pressed={form.safety === false}
                className="w-full p-5 rounded-[24px] bg-white text-[#1B2A22] font-bold text-left shadow-sm border border-[#DCE7DF] flex items-center justify-between hover:bg-slate-50 transition"
              >
                <div>
                  <div className="text-base font-extrabold">Wala Naman</div>
                  <div className="text-sm font-medium text-[#5C6E63]">Maaaring magpatuloy sa check</div>
                </div>
                {form.safety === false && <Check aria-hidden="true" className="w-4 h-4" />}
              </button>
              <button onClick={() => (form.safety === true ? showCareRoute('see_doctor') : (setQuestionIndex(0), setCurrentStep(2)))}
                disabled={form.safety === null || loading}
                className="citizen-action w-full py-4 rounded-full font-bold ">
                Magpatuloy
              </button>
            </div>
          </div>
        )}

        {/* C5 Questions, PRD v3 order, one per screen */}
        {consentAccepted && currentStep === 2 && step && (
          <div className="flex-1 flex flex-col p-6 justify-between animate-fadeIn">
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <button
                  aria-label="Bumalik sa nakaraang screen"
                  onClick={handleBack}
                  className="w-11 h-11 shrink-0 rounded-full bg-white flex items-center justify-center shadow-sm text-[#1B2A22]"
                >
                  <ArrowLeft aria-hidden="true" className="w-4 h-4" />
                </button>
                <div role="progressbar" aria-label="Progress ng mga tanong" aria-valuemin={1} aria-valuemax={steps.length}
                  aria-valuenow={questionIndex + 1} aria-valuetext={`Tanong ${questionIndex + 1} sa ${steps.length}`}
                  className="flex-1 h-2 rounded-full bg-[#DDF1E4] overflow-hidden">
                  <div
                    className="h-full bg-[#22A75A] rounded-full transition-all duration-300"
                    style={{ width: `${((questionIndex + 1) / steps.length) * 100}%` }}
                  />
                </div>
                <div className="text-sm font-bold text-[#5C6E63]">
                  {questionIndex + 1} sa {steps.length}
                </div>
              </div>

              {step === 'age_sex' && (
                <div className="space-y-4 pt-2">
                  <div className="text-sm font-semibold text-[#5C6E63] uppercase">{SECTION.age_sex}</div>
                  <h1 tabIndex={-1} className="text-[28px] leading-[1.2] font-normal">
                    Ilang <span className="font-extrabold text-[#17573A]">taon</span> ka na at ano ang iyong kasarian?
                  </h1>
                  <div className="bg-white p-5 rounded-[24px] border border-[#DCE7DF] space-y-4 shadow-sm">
                    <div>
                      <label htmlFor="citizen-age" className="block text-sm font-bold text-[#5C6E63] mb-1">Edad (Years old)</label>
                      <input
                        id="citizen-age"
                        type="text"
                        inputMode="numeric"
                        aria-invalid={ageTouched && !!ageError(form.age)}
                        aria-describedby={ageTouched && ageError(form.age) ? 'citizen-age-error' : undefined}
                        onBlur={() => setAgeTouched(true)}
                        value={form.age}
                        onChange={(e) => setForm({ ...form, age: e.target.value })}
                        className="w-full text-2xl font-extrabold p-3 rounded-[16px] bg-[#F3F8F4] border border-[#DCE7DF] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#17573A]"
                      />
                      {ageTouched && ageError(form.age) && <p id="citizen-age-error" role="alert" className="mt-2 text-sm text-[#8A2E1A]">{ageError(form.age)}</p>}
                    </div>
                    <div>
                      <CitizenSelect id="citizen-sex" label="Kasarian" value={form.sex}
                        onChange={(sex) => setForm({ ...form, sex })}
                        options={[{ value: 'female', label: 'Babae' }, { value: 'male', label: 'Lalaki' },
                          { value: 'intersex', label: 'Intersex' }, { value: 'prefer_not_to_say', label: 'Prefer not to say' }]} />
                    </div>
                  </div>
                </div>
              )}

              {step === 'municipality' && (
                <div className="space-y-4 pt-2">
                  <div className="text-sm font-semibold text-[#5C6E63] uppercase">{SECTION.municipality}</div>
                  <h1 tabIndex={-1} className="text-[28px] leading-[1.2] font-normal">
                    Saang <span className="font-extrabold text-[#17573A]">bayan o lungsod</span> ka nakatira sa Laguna?
                  </h1>
                  <CitizenSelect id="citizen-town" label="Bayan o lungsod" value={form.municipality}
                    onChange={(municipality) => setForm({ ...form, municipality })}
                    placeholder="Pumili ng bayan o lungsod"
                    options={towns.map((t) => ({ value: t.municipality, label: t.name }))} />
                  <p className="text-sm text-[#5C6E63]">{question('municipality').why}</p>
                </div>
              )}

              {step === 'height_weight' && (
                <div className="space-y-4 pt-2">
                  <div className="text-sm font-semibold text-[#5C6E63] uppercase">{SECTION.height_weight}</div>
                  <h1 tabIndex={-1} className="text-[28px] leading-[1.2] font-normal">
                    Ano ang iyong <span className="font-extrabold text-[#17573A]">height at weight</span>?
                  </h1>
                  <div className="bg-white p-5 rounded-[24px] border border-[#DCE7DF] space-y-4 shadow-sm">
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label htmlFor="citizen-height" className="block text-sm font-bold text-[#5C6E63] mb-1">Height (cm)</label>
                        <input id="citizen-height" type="text" inputMode="numeric" value={form.height_cm}
                          disabled={form.height_weight_unknown}
                          onChange={(e) => setForm({ ...form, height_cm: e.target.value })}
                          className="w-full text-2xl font-extrabold p-3 rounded-[16px] bg-[#F3F8F4] border border-[#DCE7DF]" />
                      </div>
                      <div>
                        <label htmlFor="citizen-weight" className="block text-sm font-bold text-[#5C6E63] mb-1">Weight (kg)</label>
                        <input id="citizen-weight" type="text" inputMode="numeric" value={form.weight_kg}
                          disabled={form.height_weight_unknown}
                          onChange={(e) => setForm({ ...form, weight_kg: e.target.value })}
                          className="w-full text-2xl font-extrabold p-3 rounded-[16px] bg-[#F3F8F4] border border-[#DCE7DF]" />
                      </div>
                    </div>
                    <p className="text-sm text-[#5C6E63]">{question('height_cm').why}</p>
                  </div>
                  <button onClick={() => setForm({ ...form, height_weight_unknown: !form.height_weight_unknown, height_cm: '', weight_kg: '' })}
                    aria-pressed={form.height_weight_unknown} className={choiceButton(form.height_weight_unknown, true)}>
                    Hindi ko alam {form.height_weight_unknown && <Check aria-hidden="true" className="inline w-4 h-4 ml-2" />}
                  </button>
                </div>
              )}

              {step !== 'age_sex' && step !== 'municipality' && step !== 'height_weight' && renderChoices(step)}
            </div>

            {/* Explicit advance/submit for every questionnaire step. */}
            <div className="pt-3 pb-2">
              <button
                onClick={handleNext}
                disabled={!stepAnswered(step, form) || loading}
                className="citizen-action w-full py-4 rounded-full font-bold text-base transition"
              >
                {loading ? 'Ipinapadala…' : questionIndex === steps.length - 1 ? 'Ipadala ang mga sagot' : 'Susunod na Tanong →'}
              </button>
            </div>
          </div>
        )}

        {currentStep === 9 && evaluationUnavailable && (
          <div className="flex-1 p-6 space-y-4" role="status">
            <h1 tabIndex={-1} className="text-2xl font-bold">Hindi available ang pagtatasa</h1>
            <p>Hindi makapagbigay ng resulta ang prototype para sa mga sagot na ito, o hindi maabot ang serbisyo. Walang risk level na ibinigay. Hindi ito nangangahulugang mababa ang iyong risk.</p>
            <p>Nananatili ang iyong mga sagot habang bukas ang screen na ito.</p>
            <button onClick={() => { setQuestionIndex(Math.max(0, steps.length - 1)); setCurrentStep(form.safety === true ? 1 : 2); }}
              className="citizen-action w-full p-4 rounded-full font-bold">Balikan ang mga sagot</button>
            <button onClick={() => setCurrentStep(0)} className="w-full p-4 font-bold">Bumalik sa dashboard</button>
          </div>
        )}

        {/* C4a / C9: care routes, no risk level */}
        {currentStep === 9 && careRoute && !evaluationUnavailable && (
          <div className="flex-1 flex flex-col justify-between animate-fadeIn pb-6">
            <div className="space-y-4">
              <div className="p-6 pb-7 rounded-b-[36px] space-y-3 bg-[#EBDCF9] text-[#552382]">
                <div className="text-sm font-bold uppercase tracking-wider opacity-80">Gabay para sa iyo</div>
                <h1 tabIndex={-1} className="text-[24px] leading-[1.18] font-normal tracking-tight">
                  {careRoute === 'see_doctor' ? (
                    <>Magpatingin sa <span className="font-extrabold">doktor</span> sa lalong madaling panahon.</>
                  ) : (
                    <>Patuloy na magpatingin sa <span className="font-extrabold">doktor</span> tungkol sa kidneys mo.</>
                  )}
                </h1>
                <p className="text-sm font-semibold leading-relaxed">
                  {careRoute === 'see_doctor'
                    ? 'Kailangan ng check ng doktor ang mga palatandaang ito, hindi ng questionnaire na ito. Walang risk level na ibinigay.'
                    : 'May sinabi nang problema sa kidneys mo, kaya walang risk level na ibinigay.'}
                </p>
              </div>
              {result?.where && result.where.facilities.length > 0 && (
                <div className="px-5"><FacilityCard where={result.where} /></div>
              )}
            </div>
            <div className="px-5 pt-3 space-y-2">
              <button onClick={() => setCurrentStep(11)} className="citizen-action w-full py-4 px-6 rounded-full font-bold text-sm">
                Saan magpapa-check →
              </button>
              <button onClick={() => setCurrentStep(0)} className="w-full py-3 font-bold text-[#17573A]">Bumalik sa dashboard</button>
            </div>
          </div>
        )}

        {/* C6: Result Screen (1a locked direction layout) */}
        {currentStep === 9 && result && result.route === 'result' && result.level && !careRoute && (
          <div className="flex-1 flex flex-col justify-between animate-fadeIn pb-6">
            <div className="space-y-4">
              <div
                className={`p-6 pb-7 rounded-b-[36px] relative overflow-hidden space-y-3 ${
                  result.level === 'High'
                    ? 'bg-[#F9D3C8] text-[#8A2E1A]'
                    : result.level === 'Medium'
                    ? 'bg-[#FBEBB5] text-[#6B4E00]'
                    : 'bg-[#D6F0DF] text-[#17573A]'
                }`}
              >
                <div
                  className="absolute -right-8 -top-8 w-36 h-36 rounded-full opacity-40 pointer-events-none"
                  style={{ backgroundColor: result.level === 'High' ? '#F7B7A4' : result.level === 'Medium' ? '#F7DE8A' : '#9FDDB6' }}
                />

                <div className="text-sm font-bold uppercase tracking-wider opacity-80">
                  Resulta mo · {monthYear(result.checked_on?.slice(0, 7))}
                </div>

                <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white shadow-sm font-extrabold text-sm">
                  <span
                    className="w-3.5 h-3.5 rounded-full"
                    style={{ backgroundColor: result.level === 'High' ? '#E57A5F' : result.level === 'Medium' ? '#E8B92E' : '#22A75A' }}
                  />
                  <span lang="en">{result.level}</span>
                </div>

                <h1 tabIndex={-1} className="text-[24px] leading-[1.18] font-normal tracking-tight">
                  {result.level === 'High' ? (
                    <><span className="font-extrabold">Marami</span> sa mga sagot mo ang nagpapataas ng chance ng kidney problems.</>
                  ) : result.level === 'Medium' ? (
                    <>Ilan sa mga sagot mo ay <span className="font-extrabold">nagpapataas ng chance</span> ng kidney problems.</>
                  ) : (
                    <>Mas <span className="font-extrabold">mababa ang chance</span> ng kidney problems batay sa mga sagot mo.</>
                  )}
                </h1>

                {/* Mandatory not-a-diagnosis line (PRD v3, l. 95) */}
                <p className="text-sm font-semibold leading-relaxed pt-1">
                  <Warning aria-hidden="true" size={17} className="inline align-text-bottom mr-1" />{NOT_A_DIAGNOSIS}
                </p>
              </div>

              <div className="px-5 space-y-3">
                {/* Next step and its date, by state (PRD v3 next steps) */}
                <div className="bg-white rounded-[28px] p-5 shadow-[0_1px_2px_rgba(23,87,58,.06),0_8px_24px_rgba(23,87,58,.06)] space-y-2 border border-[#DCE7DF]/60">
                  <div className="text-sm font-bold text-[#5C6E63] uppercase tracking-wider">
                    <span lang="en">Next Step</span>
                  </div>
                  <NextStep result={result} />
                </div>

                <div className="bg-[#DDF1E4] rounded-[28px] p-5 space-y-2 text-[#17573A]">
                  <div className="text-sm font-bold uppercase tracking-wider">
                    <span lang="en">Main Reasons · Illustrative</span>
                  </div>
                  <div className="space-y-1 text-sm font-semibold">
                    {(result.reasons || []).map((code) => (
                      <div key={code} className="flex items-center gap-2">
                        <span className="w-1.5 h-1.5 rounded-full bg-[#17573A]" />
                        <span>{REASON_TEXT[code]?.(result).tl ?? code}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {(result.tips || []).length > 0 && (
                  <div className="bg-white rounded-[28px] p-5 space-y-2 border border-[#DCE7DF]/60">
                    <div className="text-sm font-bold text-[#5C6E63] uppercase tracking-wider">Ano ang puwede mong gawin ngayon</div>
                    <ul className="space-y-1.5 text-sm">
                      {result.tips!.map((code) => <li key={code}>· {TIP_TEXT[code]}</li>)}
                    </ul>
                  </div>
                )}

                {result.level !== 'Low' && (
                  <div className="bg-white rounded-[28px] p-5 space-y-1 border border-[#DCE7DF]/60 text-sm">
                    <div className="font-bold text-[#5C6E63] uppercase tracking-wider">Kung nag-aalala ka</div>
                    <p>Chance ito, hindi diagnosis. Kayang i-manage ang maagang kidney problems. Ang pagpapa-test ang susunod na hakbang.</p>
                  </div>
                )}

                {showFacilities && result.where.facilities.length > 0 && <FacilityCard where={result.where} />}

                <p className="text-sm text-[#5C6E63] leading-relaxed px-1">
                  Sagutin ulit nang mas maaga kung na-diagnose ka ng diabetes o high BP, nagsimula o tumigil sa gamot, umabot sa 50, 60 o 70, malaki ang itinaba o ipinayat, o pagkatapos manganak.
                </p>
              </div>
            </div>

            <div className="px-5 pt-3 space-y-2">
              <button onClick={() => setCurrentStep(0)} className="w-full py-3 font-bold text-[#17573A]">Bumalik sa dashboard</button>
              <button
                aria-expanded={showFacilities}
                aria-controls={showFacilities && result.where.facilities.length > 0 ? 'citizen-facilities' : undefined}
                onClick={() => setShowFacilities(!showFacilities)}
                className="citizen-action w-full py-4 px-6 rounded-full font-bold text-sm shadow-[0_10px_24px_rgba(34,167,90,0.3)] transition flex items-center justify-center gap-2"
              >
                <span>{showFacilities ? 'Itago ang mga pasilidad' : 'Saan magpapa-check →'}</span>
              </button>

              <button
                onClick={resetAll}
                className="w-full py-3 px-4 rounded-full border border-[#C9DCCF] hover:bg-white text-sm font-bold text-[#5C6E63] transition flex items-center justify-center gap-1.5"
              >
                <RotateCcw className="w-3.5 h-3.5" /> Ulitin ang check
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

const NextStep: React.FC<{ result: RiskCheckResult }> = ({ result }) => {
  const step = result.next_step!;
  return (
    <>
      <div className="text-base font-extrabold text-[#1B2A22] leading-snug">
        {step.code === 'recheck' && 'Sagutin ulit ang check na ito.'}
        {step.code === 'bp_sugar_first' && 'Magpa-check muna ng BP at blood sugar sa health center mo, saka sagutin ulit.'}
        {step.code === 'kidney_test' && `Magpa-simple blood at urine test para sa kidneys mo${step.soon ? ' sa lalong madaling panahon' : ''}.`}
      </div>
      {step.next_check && <div className="text-sm text-[#5C6E63]">Next check: {monthYear(step.next_check)}</div>}
      {step.next_kidney_test && <div className="text-sm text-[#5C6E63]">Pagkatapos, taon-taon. Next kidney test: {monthYear(step.next_kidney_test)}</div>}
      {result.blood_sugar_prompt && <div className="text-sm font-bold text-[#6B4E00]">Magpa-check din ng blood sugar.</div>}
    </>
  );
};

const FacilityCard: React.FC<{ where: RiskCheckResult['where'] }> = ({ where }) => (
  <div id="citizen-facilities" className="bg-white rounded-[28px] p-5 space-y-2 border border-[#DCE7DF] shadow-sm animate-fadeIn">
    <div className="flex items-center gap-1.5 text-sm font-bold text-[#17573A] uppercase tracking-wider">
      <Hospital className="w-4 h-4 text-[#22A75A]" />
      <span>Saan magpapa-check</span>
    </div>
    {where.shown_from && (
      <p className="text-sm text-[#5C6E63]">Walang nakalistang pasilidad sa bayan mo; ito ang pinakamalapit.</p>
    )}
    <div className="space-y-2 pt-1">
      {where.facilities.slice(0, 3).map((fac) => (
        <div key={fac.name} className="p-3 bg-[#F3F8F4] rounded-[18px] text-sm space-y-0.5">
          <div className="font-bold text-[#1B2A22]">{fac.name}</div>
          <div className="text-[#5C6E63] text-sm">
            {fac.type === 'Hospital' ? 'Ospital' : 'Health center'} · Kidney tests: hindi pa alam · Hindi pa verified, tumawag muna
          </div>
        </div>
      ))}
    </div>
  </div>
);
