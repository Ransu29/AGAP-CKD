// PRD v3 risk check: the questionnaire and result wording shared by every channel (ADR 0003).
// The order, options and branching follow the PRD v3 questionnaire table; the scoring itself lives in
// the backend (/api/risk-check/evaluate). Taglish follows the design mock-ups; lines the mock-ups do
// not show are drafts for native-speaker review.

export const DK = "I don't know";

export interface Answers {
  age_group?: string;
  sex?: string;
  municipality?: string;
  diabetes?: string;
  high_blood_pressure?: string;
  medicine?: string;
  bp_reading?: string;
  heart_disease_stroke?: string;
  kidney_stones?: string;
  family_history?: string;
  height_cm?: number | null;
  weight_kg?: number | null;
  heavy_outdoor_work?: string;
  kidney_status?: string;
}

export interface Option {
  value: string;
  label: string;
}

export interface Question {
  key: keyof Answers;
  section: string;
  text: string;
  emphasis?: string;
  why: string;
  options?: Option[];
  kind?: 'choice' | 'town' | 'height_weight';
}

export const YES_NO: Option[] = [
  { value: 'Yes', label: 'Oo' },
  { value: 'No', label: 'Hindi' },
  { value: DK, label: 'Hindi ko alam' },
];

export const SAFETY_QUESTION =
  'Ikaw ba ay wala pang 18, buntis, o may alinman sa mga ito: pamamaga ng binti o mukha, mabula o may dugong ihi, o kaunting-kaunti ang ihi?';

export const QUESTIONS: Question[] = [
  {
    key: 'age_group',
    section: 'Tungkol sa iyo',
    text: 'Ilang taon ka na?',
    why: 'Edad ang pinakamalakas na palatandaan ng kidney risk.',
    options: ['18-39', '40-49', '50-59', '60-69', '70+'].map((v) => ({ value: v, label: v === '70+' ? '70 pataas' : v.replace('-', '–') })),
  },
  {
    key: 'sex',
    section: 'Tungkol sa iyo',
    text: 'Ano ang kasarian mo?',
    why: 'Kasama ang kasarian sa mga kilalang kidney risk score.',
    options: [
      { value: 'Female', label: 'Babae' },
      { value: 'Male', label: 'Lalaki' },
    ],
  },
  {
    key: 'municipality',
    section: 'Tungkol sa iyo',
    text: 'Saang bayan o lungsod ka nakatira?',
    why: 'Para maipakita ang pinakamalapit na pasilidad. Hindi ito ginagamit sa risk level.',
    kind: 'town',
  },
  {
    key: 'diabetes',
    section: 'Health history',
    text: "May doktor na bang nagsabi sa'yo na may diabetes ka?",
    emphasis: 'diabetes',
    why: 'Diabetes ang pangunahing sanhi ng kidney disease.',
    options: YES_NO,
  },
  {
    key: 'high_blood_pressure',
    section: 'Health history',
    text: "May doktor na bang nagsabi sa'yo na may high blood pressure ka?",
    emphasis: 'high blood pressure',
    why: 'Isa ang high blood pressure sa pangunahing sanhi ng kidney problems.',
    options: YES_NO,
  },
  {
    key: 'medicine',
    section: 'Health history',
    text: 'Sa nakaraang 2 linggo, paano mo iniinom ang gamot mo sa BP o sugar?',
    why: 'Ang regular na pag-inom ng gamot ay nakakatulong protektahan ang kidneys.',
    options: [
      { value: 'Regularly', label: 'Regular, araw-araw' },
      { value: 'Sometimes miss', label: 'Minsan nakakalimutan' },
      { value: 'Stopped', label: 'Tumigil na' },
      { value: 'No medicine given', label: 'Walang ibinigay na gamot' },
      { value: DK, label: 'Hindi ko alam' },
    ],
  },
  {
    key: 'bp_reading',
    section: 'Health history',
    text: 'Sa nakaraang 12 buwan, ano ang huling resulta ng pagkuha ng BP mo?',
    why: 'Maraming may high blood pressure ang hindi pa alam na mayroon sila.',
    options: [
      { value: 'Normal', label: 'Normal' },
      { value: 'High', label: 'Mataas' },
      { value: 'Not measured', label: 'Hindi nakuhanan' },
      { value: DK, label: 'Hindi ko alam' },
    ],
  },
  {
    key: 'heart_disease_stroke',
    section: 'Health history',
    text: "May doktor na bang nagsabi sa'yo na may sakit ka sa puso, o na-stroke ka na?",
    why: 'Kaugnay ng kidney problems ang sakit sa puso at stroke.',
    options: YES_NO,
  },
  {
    key: 'kidney_stones',
    section: 'Health history',
    text: 'Nagkaroon ka na ba ng bato sa kidney (kidney stones)?',
    why: 'Bahagi ang kidney stones ng Thai kidney risk score.',
    options: YES_NO,
  },
  {
    key: 'family_history',
    section: 'Pamilya',
    text: 'May kamag-anak ka bang nagkaroon ng kidney disease o nag-dialysis?',
    why: 'Mas mataas ang risk kung may kapamilyang may kidney disease.',
    options: YES_NO,
  },
  {
    key: 'height_cm',
    section: 'Height at weight',
    text: 'Ano ang height at weight mo?',
    why: 'Para makuha ang BMI, gamit ang Asian cut-offs.',
    kind: 'height_weight',
  },
  {
    key: 'heavy_outdoor_work',
    section: 'Trabaho',
    text: 'Mabigat ba ang trabaho mo sa labas, sa ilalim ng init, sa mga araw na ito?',
    why: 'Ang matagal na init at pagod sa labas ay maaaring makaapekto sa kidneys.',
    options: YES_NO,
  },
  {
    key: 'kidney_status',
    section: 'Kidneys',
    text: 'Na-check na ba ang kidneys mo sa nakaraang 12 buwan?',
    why: 'Kung may sinabing problema na, ituturo namin sa doktor.',
    options: [
      { value: 'Never tested', label: 'Hindi pa kailanman' },
      { value: 'Tested normal in the past 12 months', label: 'Oo, normal ang resulta' },
      { value: 'Told something was wrong', label: 'Oo, sinabihang may problema' },
      { value: DK, label: 'Hindi ko alam' },
    ],
  },
];

// Branching: medicine only after a Yes to diabetes or high BP; BP reading only after high BP No or I don't know.
export const questionsFor = (a: Answers) =>
  QUESTIONS.filter((q) => {
    if (q.key === 'medicine') return a.diabetes === 'Yes' || a.high_blood_pressure === 'Yes';
    if (q.key === 'bp_reading') return a.high_blood_pressure !== undefined && a.high_blood_pressure !== 'Yes';
    return true;
  });

// Drop branch answers that no longer apply after an earlier answer changes.
export const pruneBranches = (a: Answers): Answers => {
  const next = { ...a };
  if (!(next.diabetes === 'Yes' || next.high_blood_pressure === 'Yes')) delete next.medicine;
  if (next.high_blood_pressure === 'Yes') delete next.bp_reading;
  return next;
};

export type Level = 'Low' | 'Medium' | 'High';

export interface Facility {
  name: string;
  type: string;
  municipality: string;
  kidney_tests: string;
  verification: string;
}

export interface Where {
  municipality: string;
  shown_from: string | null;
  facilities: Facility[];
}

export interface RiskCheckResult {
  route: 'result' | 'see_doctor' | 'already_diagnosed';
  level?: Level;
  next_step?: { code: 'recheck' | 'bp_sugar_first' | 'kidney_test'; soon: boolean; next_check: string | null; next_kidney_test: string | null };
  blood_sugar_prompt?: boolean;
  reasons?: string[];
  age_group?: string;
  tips?: string[];
  where: Where;
  checked_on?: string;
}

export const MONTHS_TL = ['Ene', 'Peb', 'Mar', 'Abr', 'May', 'Hun', 'Hul', 'Ago', 'Set', 'Okt', 'Nob', 'Dis'];
export const monthYear = (ym: string | null | undefined) => {
  if (!ym) return '';
  const [y, m] = ym.split('-').map(Number);
  return `${MONTHS_TL[m - 1]} ${y}`;
};

export const NOT_A_DIAGNOSIS = 'Hindi ito diagnosis. Blood at urine test lang ang makakapag-check ng kidneys.';

export const LEVEL_LINE: Record<Level, string> = {
  Low: 'Mas mababa ang chance ng kidney problems batay sa mga sagot.',
  Medium: 'Ilan sa mga sagot ay nagpapataas ng chance ng kidney problems.',
  High: 'Marami sa mga sagot ang nagpapataas ng chance ng kidney problems.',
};

export const LEVEL_STYLE: Record<Level, { band: string; text: string; dot: string }> = {
  Low: { band: 'bg-[#D6F0DF]', text: 'text-[#17573A]', dot: '#22A75A' },
  Medium: { band: 'bg-[#FBEBB5]', text: 'text-[#6B4E00]', dot: '#E8B92E' },
  High: { band: 'bg-[#F9D3C8]', text: 'text-[#8A2E1A]', dot: '#E57A5F' },
};

const ageLabel = (age?: string) => (age === '70+' ? '70 pataas' : (age || '').replace('-', '–'));

// Taglish for the screen; English for the referral note, as in the field-tablet mock-up.
export const REASON_TEXT: Record<string, (r: RiskCheckResult) => { tl: string; en: string }> = {
  diabetes: () => ({ tl: 'May diabetes', en: 'Diabetes' }),
  high_bp: () => ({ tl: 'May high blood pressure', en: 'High blood pressure' }),
  age_group: (r) => ({ tl: `Edad ${ageLabel(r.age_group)}`, en: `Age ${ageLabel(r.age_group).replace(' pataas', '+')}` }),
  kidney_stones: () => ({ tl: 'Nagkaroon ng kidney stones', en: 'Kidney stones' }),
  heart_disease_stroke: () => ({ tl: 'May sakit sa puso o na-stroke', en: 'Heart disease or stroke' }),
  family_history: () => ({ tl: 'May kapamilyang may kidney disease', en: 'Family history of kidney disease' }),
  unknown_bp_sugar: () => ({ tl: 'Hindi pa alam ang BP o blood sugar', en: 'Unknown BP or sugar status' }),
  obese: () => ({ tl: 'Mataas ang BMI (27.5 pataas)', en: 'BMI 27.5 or more' }),
  overweight: () => ({ tl: 'Medyo mataas ang BMI (23–27.4)', en: 'BMI 23 to 27.4' }),
  stopped_medicine: () => ({ tl: 'Hindi regular ang pag-inom ng gamot', en: 'Medicine not taken regularly' }),
  heavy_outdoor_work: () => ({ tl: 'Mabigat na trabaho sa labas, sa init', en: 'Heavy outdoor work in the heat' }),
};

export const TIP_TEXT: Record<string, string> = {
  keep_medicine: 'Inumin ang gamot sa BP o sugar araw-araw, kahit maayos ang pakiramdam.',
  check_bp_sugar: 'Magpa-check ng BP at blood sugar. Mabilis ito at kadalasang libre sa health center.',
  diabetes_care: 'Bantayan ang blood sugar at huwag lumiban sa check-up.',
  bp_care: 'Bantayan ang BP at bawasan ang alat sa pagkain.',
  weight_activity: 'Gumalaw araw-araw at bantayan ang timbang.',
  water_shade: 'Uminom ng tubig at magpahinga sa lilim kapag nagtatrabaho sa init.',
  avoid_painkillers: 'Huwag madalas uminom ng ibuprofen nang walang payo ng doktor.',
};

export const EDUCATION_CARDS = [
  'Araw-araw nililinis ng kidneys ang dugo.',
  'Walang sintomas ang maagang kidney problems.',
  'Simpleng blood at urine test lang ang makakapag-check ng kidneys.',
];
