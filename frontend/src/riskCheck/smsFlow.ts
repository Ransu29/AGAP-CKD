// PRD v3 SMS channel: the same questions, order, model and guideline floor as the app (ADR 0003), as a
// conversation of single-segment messages. Pure logic: the view sends `request` to /api/risk-check/evaluate
// and passes the response to `resultMessages`. Wording is draft Taglish for native-speaker review.
import { DK, REASON_TEXT, TIP_TEXT, monthYear, type RiskCheckResult } from './content';

export const SMS_LIMIT = 160;

// GSM 03.38 basic character set. Extension characters (^{}[]~|\€) take two places, so messages avoid them.
const GSM7 = new Set(
  "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà",
);

export const isGsm7 = (text: string) => [...text].every((c) => GSM7.has(c));
export const fitsOneSegment = (text: string) => isGsm7(text) && text.length <= SMS_LIMIT;

// Facility and town names come from registers: keep ñ (GSM-7), straighten quotes and dashes, drop the rest.
export function toGsm(text: string): string {
  const plain = text.replace(/[‘’]/g, "'").replace(/[“”]/g, '"').replace(/[–—]/g, '-');
  return [...plain]
    .map((c) => (GSM7.has(c) ? c : c.normalize('NFD').replace(/[̀-ͯ]/g, '')))
    .filter((c) => GSM7.has(c))
    .join('');
}

// Shorten one variable part so the whole message stays one segment.
function fit(before: string, variable: string, after: string): string {
  const room = SMS_LIMIT - before.length - after.length;
  const value = toGsm(variable);
  return before + (value.length <= room ? value : value.slice(0, Math.max(0, room - 3)) + '...') + after;
}

type Choice = { reply: string; value: string };

interface Item {
  key: string;
  prompt: string;
  choices?: Choice[];
  allowDK: boolean;
  kind?: 'town' | 'height_weight';
}

const YES_NO: Choice[] = [
  { reply: '1', value: 'Yes' },
  { reply: '2', value: 'No' },
  { reply: '0', value: DK },
];
const YN = '1=Oo 2=Hindi 0=Hindi ko alam';

const ITEMS: Item[] = [
  {
    key: 'age_group', allowDK: false, prompt: 'Ilang taon ka na? 1=18-39 2=40-49 3=50-59 4=60-69 5=70 pataas',
    choices: ['18-39', '40-49', '50-59', '60-69', '70+'].map((value, i) => ({ reply: String(i + 1), value })),
  },
  { key: 'sex', allowDK: false, prompt: 'Kasarian mo? 1=Babae 2=Lalaki', choices: [{ reply: '1', value: 'Female' }, { reply: '2', value: 'Male' }] },
  { key: 'municipality', allowDK: false, kind: 'town', prompt: 'Saang bayan o lungsod ka nakatira? I-type ang pangalan, hal. Calamba' },
  { key: 'diabetes', allowDK: true, prompt: `May doktor bang nagsabing may diabetes ka? ${YN}`, choices: YES_NO },
  { key: 'high_blood_pressure', allowDK: true, prompt: `May doktor bang nagsabing may high blood pressure ka? ${YN}`, choices: YES_NO },
  {
    key: 'medicine', allowDK: true,
    prompt: 'Sa nakaraang 2 linggo, iniinom mo ba ang gamot sa BP o sugar? 1=Regular 2=Minsan nakakalimutan 3=Tumigil na 4=Walang gamot 0=Hindi alam',
    choices: [
      { reply: '1', value: 'Regularly' }, { reply: '2', value: 'Sometimes miss' }, { reply: '3', value: 'Stopped' },
      { reply: '4', value: 'No medicine given' }, { reply: '0', value: DK },
    ],
  },
  {
    key: 'bp_reading', allowDK: true,
    prompt: 'Huling BP reading sa nakaraang 12 buwan? 1=Normal 2=Mataas 3=Hindi nakuhanan 0=Hindi ko alam',
    choices: [{ reply: '1', value: 'Normal' }, { reply: '2', value: 'High' }, { reply: '3', value: 'Not measured' }, { reply: '0', value: DK }],
  },
  { key: 'heart_disease_stroke', allowDK: true, prompt: `May doktor bang nagsabing may sakit ka sa puso, o na-stroke ka na? ${YN}`, choices: YES_NO },
  { key: 'kidney_stones', allowDK: true, prompt: `Nagkaroon ka na ba ng kidney stones? ${YN}`, choices: YES_NO },
  { key: 'family_history', allowDK: true, prompt: `May kamag-anak bang nagka-kidney disease o nag-dialysis? ${YN}`, choices: YES_NO },
  { key: 'height_weight', allowDK: true, kind: 'height_weight', prompt: 'Height at timbang mo? Hal. 165 cm 70 kg, o 5ft5 154 lb. 0=Hindi ko alam' },
  { key: 'heavy_outdoor_work', allowDK: true, prompt: `Mabigat ba ang trabaho mo sa labas, sa init, ngayon? ${YN}`, choices: YES_NO },
  {
    key: 'kidney_status', allowDK: true,
    prompt: 'Na-check na ba ang kidneys mo sa nakaraang 12 buwan? 1=Hindi pa 2=Oo, normal 3=Oo, may problema 0=Hindi ko alam',
    choices: [
      { reply: '1', value: 'Never tested' }, { reply: '2', value: 'Tested normal in the past 12 months' },
      { reply: '3', value: 'Told something was wrong' }, { reply: '0', value: DK },
    ],
  },
];

// Same branching as the app: medicine after a Yes to diabetes or high BP; BP reading after high BP No or I don't know.
export function itemsFor(answers: Answers): Item[] {
  return ITEMS.filter((item) => {
    if (item.key === 'medicine') return answers.diabetes === 'Yes' || answers.high_blood_pressure === 'Yes';
    // Counted until high BP is answered Yes, so the progress total does not jump; it is always asked after high BP.
    if (item.key === 'bp_reading') return answers.high_blood_pressure !== 'Yes';
    return true;
  });
}

export type Answers = Record<string, string | number | null>;
export interface Town { municipality: string; name: string }

export type Phase = 'idle' | 'consent' | 'safety' | 'question' | 'confirm_hw' | 'reminder' | 'done' | 'paused';

export interface SmsState {
  phase: Phase;
  answers: Answers;
  index: number;
  unclear: number;
  pending?: { height_cm: number; weight_kg: number };
  resume?: Phase;
  result?: RiskCheckResult;
}

export const initialState = (): SmsState => ({ phase: 'idle', answers: {}, index: 0, unclear: 0 });

export interface Step {
  state: SmsState;
  out: string[];
  request?: Record<string, unknown>;
}

export const MSG = {
  start: 'I-text ang CHECK para malaman kung kailangan mong magpa-test ng kidneys. Libre ang check na ito.',
  consent:
    'AGAP kidney check, 2-3 minuto. Walang pangalan. Area totals lang ang makikita ng LGU. Burado ang sagot pagkatapos. 1=Pumapayag 2=Hindi ngayon',
  declined:
    'Sige. Walang naitago. Alam mo ba? Walang sintomas ang maagang kidney problems. Blood at urine test lang ang makakapag-check. I-text ang CHECK anumang oras.',
  safety:
    'Bago magsimula: wala ka pang 18, buntis, o may manas, mabula o may dugong ihi, o kaunting-kaunting ihi? 1=Oo 2=Hindi',
  seeDoctor:
    'AGAP: Magpatingin agad sa doktor o health center. Hindi ka namin bibigyan ng risk level ngayon. Hindi ito diagnosis.',
  unclear: 'Hindi namin naintindihan. Pakisagot ng numero lang. 0=Hindi ko alam.',
  treatedAsDK: "Itinuring na 'Hindi ko alam'.",
  townUnknown: 'Hindi namin nakita ang bayan. I-type ulit, hal. Calamba, Sta. Cruz, Los Banos, San Pablo.',
  help: 'AGAP kidney check. Sumagot ng numero. 0=Hindi ko alam. BACK=balik, STOP=tigil, TULOY=ituloy. Libre ang tulong, walang pangalan na kailangan.',
  stopNoLevel: 'Itinigil ang check. Walang naitago. I-text ang CHECK para magsimula ulit.',
  stopNoReminders: 'Itinigil. Walang paalalang ipapadala at burado na ang numero mo. I-text ang CHECK anumang oras.',
  stoppedPrefix: 'Itinigil ang check. Narito ang risk level batay sa mga nasagot mo.',
  timeout: 'Nag-time out ang check mo. Naka-save ang mga sagot. I-text ang TULOY para ituloy, o STOP para tumigil.',
  reminderAsk: 'Pwede ka ba naming padalhan ng hanggang 3 paalala? 1=Oo 2=Hindi',
  reminderNo: 'Sige, walang paalala. Hindi namin itatago ang numero mo. Salamat sa pag-check!',
  reminderYesReferred:
    'Salamat. Paalala sa ika-7 at ika-30 araw, 7AM-9PM lang. I-reply ang DONE kapag nakapag-test ka na. STOP para tumigil.',
  doneThanks: 'Salamat! Naitala na nakapag-test ka (self-reported). Ituloy ang payo ng doktor mo.',
  finished: 'Tapos na ang check mo. I-text ang CHECK para mag-check ulit.',
};

const WORDS: Record<string, string> = {
  isa: '1', one: '1', una: '1', dalawa: '2', two: '2', tatlo: '3', three: '3', apat: '4', four: '4',
  lima: '5', five: '5', zero: '0', sero: '0', wala: '0',
};

// Loose replies ("1", "1.", " 1 ", "isa") become a digit; yes/no words map for yes/no questions only.
export function normalizeReply(raw: string, yesNo = false): string | null {
  const text = raw.trim().toLowerCase().replace(/[.!,)]+$/, '').trim();
  if (/^\d$/.test(text)) return text;
  if (WORDS[text]) return WORDS[text];
  if (/^(hindi ko alam|di ko alam|hindi alam|dk)$/.test(text)) return '0';
  if (yesNo && /^(oo|opo|yes|y|o)$/.test(text)) return '1';
  if (yesNo && /^(hindi|no|n|ayaw)$/.test(text)) return '2';
  return null;
}

const simplify = (s: string) =>
  s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
    .replace(/\bsta\.?\s/g, 'santa ').replace(/\bsto\.?\s/g, 'santo ')
    .replace(/\b(city of|city|lungsod ng|bayan ng)\b/g, '').replace(/[^a-z ]/g, ' ').replace(/\s+/g, ' ').trim();

export function matchTown(raw: string, towns: Town[]): Town | null {
  const wanted = simplify(raw);
  if (!wanted) return null;
  const exact = towns.filter((t) => simplify(t.name) === wanted || simplify(t.municipality) === wanted);
  if (exact.length === 1) return exact[0];
  const partial = towns.filter((t) => simplify(t.name).startsWith(wanted) || wanted.startsWith(simplify(t.name)));
  return partial.length === 1 ? partial[0] : null;
}

// "165 cm 70 kg", "165 70", "5ft5 154 lb", "5'5 154lbs" -> centimetres and kilograms, or null.
export function parseHeightWeight(raw: string): { height_cm: number; weight_kg: number } | null {
  const text = raw.toLowerCase().replace(/,/g, ' ');
  let height: number | null = null;
  let rest = text;
  const feet = text.match(/(\d)\s*(?:ft|feet|'|talampakan)\s*(?:(\d{1,2})(?!\d)\s*(?:in|inches|"|pulgada)?)?/);
  if (feet) {
    height = (Number(feet[1]) * 12 + Number(feet[2] || 0)) * 2.54;
    rest = text.replace(feet[0], ' ');
  }
  const numbers = [...rest.matchAll(/(\d+(?:\.\d+)?)\s*(cm|kg|kilo|kilos|lb|lbs|pounds)?/g)];
  let weight: number | null = null;
  for (const [, value, unit] of numbers) {
    const n = Number(value);
    if (height === null && (unit === 'cm' || (!unit && n >= 100 && n <= 230))) height = n;
    else if (weight === null && unit && /^(lb|lbs|pounds)$/.test(unit)) weight = n * 0.4536;
    else if (weight === null && (!unit || /^(kg|kilo|kilos)$/.test(unit))) weight = n;
  }
  if (height === null || weight === null) return null;
  if (height < 100 || height > 230 || weight < 25 || weight > 300) return null;
  return { height_cm: Math.round(height), weight_kg: Math.round(weight) };
}

export function questionMessage(state: SmsState): string {
  const items = itemsFor(state.answers);
  return `(${state.index + 1}/${items.length}) ${items[state.index].prompt}`;
}

const answersReady = (answers: Answers) => ['age_group', 'sex', 'municipality'].every((k) => answers[k]);

// The evaluate request. Unanswered items enter as "I don't know" (a stopped check still gets a level, PRD v3).
export function requestFor(answers: Answers): Record<string, unknown> {
  const dk = (key: string) => (answers[key] as string) || DK;
  const branch = itemsFor(answers).map((item) => item.key);
  return {
    channel: 'sms',
    safety: 'No',
    age_group: answers.age_group,
    sex: answers.sex,
    municipality: answers.municipality,
    diabetes: dk('diabetes'),
    high_blood_pressure: dk('high_blood_pressure'),
    medicine: branch.includes('medicine') ? dk('medicine') : null,
    bp_reading: branch.includes('bp_reading') ? dk('bp_reading') : null,
    heart_disease_stroke: dk('heart_disease_stroke'),
    kidney_stones: dk('kidney_stones'),
    family_history: dk('family_history'),
    height_cm: answers.height_cm ?? null,
    weight_kg: answers.weight_kg ?? null,
    heavy_outdoor_work: dk('heavy_outdoor_work'),
    kidney_status: dk('kidney_status'),
  };
}

function advance(state: SmsState, answers: Answers): Step {
  const next = { ...state, answers, index: state.index + 1, unclear: 0, pending: undefined, phase: 'question' as Phase };
  if (next.index >= itemsFor(answers).length) return { state: { ...next, phase: 'question' }, out: [], request: requestFor(answers) };
  return { state: next, out: [questionMessage(next)] };
}

function answerItem(state: SmsState, text: string, towns: Town[]): Step {
  const item = itemsFor(state.answers)[state.index];
  const unclear = (): Step => {
    if (state.unclear >= 1 && item.allowDK) {
      const answers = { ...state.answers, ...(item.kind === 'height_weight' ? { height_cm: null, weight_kg: null } : { [item.key]: DK }) };
      const step = advance(state, answers);
      return { ...step, out: [MSG.treatedAsDK, ...step.out] };
    }
    const again = { ...state, unclear: state.unclear + 1 };
    return { state: again, out: [item.kind === 'town' ? MSG.townUnknown : MSG.unclear, questionMessage(again)] };
  };
  if (item.kind === 'town') {
    const town = matchTown(text, towns);
    return town ? advance(state, { ...state.answers, municipality: town.municipality }) : unclear();
  }
  if (item.kind === 'height_weight') {
    if (normalizeReply(text) === '0') return advance(state, { ...state.answers, height_cm: null, weight_kg: null });
    const parsed = parseHeightWeight(text);
    if (!parsed) return unclear();
    return {
      state: { ...state, phase: 'confirm_hw', pending: parsed, unclear: 0 },
      out: [`${parsed.height_cm} cm, ${parsed.weight_kg} kg? 1=Oo 2=Mali`],
    };
  }
  const yesNo = item.choices === YES_NO;
  const reply = normalizeReply(text, yesNo);
  const choice = item.choices.find((c) => c.reply === reply);
  if (!choice) return unclear();
  const answers: Answers = { ...state.answers, [item.key]: choice.value };
  // An earlier answer can switch a branch item off; drop its stale answer.
  if (!(answers.diabetes === 'Yes' || answers.high_blood_pressure === 'Yes')) delete answers.medicine;
  if (answers.high_blood_pressure === 'Yes') delete answers.bp_reading;
  return advance(state, answers);
}

// One incoming text -> the next state, the messages to send, and an evaluate request when the answers are complete.
export function reply(state: SmsState, raw: string, towns: Town[]): Step {
  const text = raw.trim();
  const keyword = text.toUpperCase();
  if (keyword === 'HELP') return { state, out: [MSG.help] };
  if (keyword === 'CHECK') {
    const next: SmsState = { ...initialState(), phase: 'consent' };
    return { state: next, out: [MSG.consent] };
  }
  if (keyword === 'STOP') {
    if ((state.phase === 'question' || state.phase === 'confirm_hw' || state.phase === 'paused') && answersReady(state.answers)) {
      return { state: { ...state, phase: 'question' }, out: [MSG.stoppedPrefix], request: requestFor(state.answers) };
    }
    if (state.phase === 'reminder' || state.phase === 'done') return { state: { ...state, phase: 'idle' }, out: [MSG.stopNoReminders] };
    return { state: initialState(), out: [MSG.stopNoLevel] };
  }
  if (state.phase === 'paused') {
    if (keyword !== 'TULOY') return { state, out: [MSG.timeout] };
    const resumed = { ...state, phase: state.resume ?? 'question', resume: undefined };
    const out = resumed.phase === 'question' ? [questionMessage(resumed)] : resumed.phase === 'safety' ? [MSG.safety] : [MSG.consent];
    return { state: resumed, out };
  }
  if (keyword === 'TULOY') {
    if (state.phase === 'question') return { state, out: [questionMessage(state)] };
    return { state, out: [state.phase === 'idle' ? MSG.start : MSG.finished] };
  }
  if (keyword === 'BACK') {
    if (state.phase === 'confirm_hw') return { state: { ...state, phase: 'question', pending: undefined }, out: [questionMessage(state)] };
    if (state.phase === 'question') {
      if (state.index === 0) return { state: { ...state, phase: 'safety', unclear: 0 }, out: [MSG.safety] };
      const back = { ...state, index: state.index - 1, unclear: 0 };
      return { state: back, out: [questionMessage(back)] };
    }
    if (state.phase === 'safety') return { state: { ...state, phase: 'consent' }, out: [MSG.consent] };
  }

  switch (state.phase) {
    case 'idle':
      return { state, out: [MSG.start] };
    case 'consent': {
      const r = normalizeReply(text, true);
      if (r === '1') return { state: { ...state, phase: 'safety', unclear: 0 }, out: [MSG.safety] };
      if (r === '2') return { state: initialState(), out: [MSG.declined] };
      return { state, out: [MSG.unclear, MSG.consent] };
    }
    case 'safety': {
      const r = normalizeReply(text, true);
      if (r === '1') return { state: initialState(), out: [MSG.seeDoctor] };
      if (r === '2') {
        const next: SmsState = { ...state, phase: 'question', index: 0, unclear: 0 };
        return { state: next, out: [questionMessage(next)] };
      }
      return { state, out: [MSG.unclear, MSG.safety] };
    }
    case 'question':
      return answerItem(state, text, towns);
    case 'confirm_hw': {
      const r = normalizeReply(text, true);
      if (r === '1') return advance(state, { ...state.answers, ...state.pending });
      if (r === '2') return { state: { ...state, phase: 'question', pending: undefined }, out: [questionMessage(state)] };
      return { state, out: [MSG.unclear, `${state.pending.height_cm} cm, ${state.pending.weight_kg} kg? 1=Oo 2=Mali`] };
    }
    case 'reminder': {
      const r = normalizeReply(text, true);
      if (r === '2') return { state: { ...state, phase: 'done' }, out: [MSG.reminderNo] };
      if (r !== '1') return { state, out: [MSG.unclear, MSG.reminderAsk] };
      const result = state.result;
      const message = result?.level === 'Low'
        ? fit('Salamat. Isang paalala lang sa ', monthYear(result.next_step?.next_check), ' para mag-check ulit. STOP para tumigil.')
        : MSG.reminderYesReferred;
      return { state: { ...state, phase: 'done' }, out: [message] };
    }
    case 'done':
      if (keyword === 'DONE') return { state, out: [MSG.doneThanks] };
      return { state, out: [MSG.finished] };
  }
  return { state, out: [MSG.start] };
}

// A 30-minute silence: the check pauses and TULOY resumes it.
export function timeout(state: SmsState): Step {
  if (!['consent', 'safety', 'question', 'confirm_hw'].includes(state.phase)) return { state, out: [] };
  const resume = state.phase === 'confirm_hw' ? 'question' : state.phase;
  return { state: { ...state, phase: 'paused', resume, pending: undefined }, out: [MSG.timeout] };
}

const LEVEL_TL = { Low: 'MABABA (Low)', Medium: 'KATAMTAMAN (Medium)', High: 'MATAAS (High)' } as const;

// The result in 2-3 single-segment messages (PRD v3): level and the not-a-diagnosis line; one reason and the
// next step with its date; one facility. People at Low get a tip, never "get a kidney test" (PHEX 2026).
export function resultMessages(state: SmsState, result: RiskCheckResult): Step {
  const facility = result.where?.facilities?.[0];
  const place = facility ? `${facility.name}, ${facility.municipality}` : 'ang health center sa inyong bayan';
  if (result.route === 'see_doctor') return { state: initialState(), out: [MSG.seeDoctor] };
  if (result.route === 'already_diagnosed') {
    return {
      state: initialState(),
      out: [
        'AGAP: Dahil may sinabing problema sa kidneys mo, bumalik sa iyong doktor. Hindi mo na kailangan ang check na ito.',
        fit('Pinakamalapit: ', place, '. Hindi pa beripikado, tumawag muna.'),
      ],
    };
  }
  const level = result.level ?? 'Low';
  const first = `AGAP: ${LEVEL_TL[level]} ang risk level mo. Hindi ito diagnosis. Blood at urine test lang ang makakapag-check ng kidneys.`;
  const reasonKey = result.reasons?.[0];
  const reason = reasonKey && REASON_TEXT[reasonKey] ? `Dahilan: ${REASON_TEXT[reasonKey](result).tl}. ` : '';
  const step = result.next_step;
  let next: string;
  if (step?.code === 'recheck') next = `Susunod: mag-check ulit sa ${monthYear(step.next_check)}.`;
  else if (step?.code === 'bp_sugar_first') next = 'Susunod: magpa-check ng BP at blood sugar sa health center, saka mag-check ulit.';
  else next = `Susunod: magpa-blood at urine test${step?.soon ? ' agad' : ''}. Pagkatapos, taon-taon. Next kidney test: ${monthYear(step?.next_kidney_test)}.`;
  const second = toGsm(reason + next).length <= SMS_LIMIT ? toGsm(reason + next) : toGsm(next);
  const third = level === 'Low'
    ? toGsm(`Tip: ${TIP_TEXT[result.tips?.[0] ?? 'weight_activity'] ?? TIP_TEXT.weight_activity}`)
    : fit('Pinakamalapit: ', place, '. Hindi pa beripikado, tumawag muna.');
  return { state: { ...state, phase: 'reminder', result }, out: [first, second, third, MSG.reminderAsk] };
}
