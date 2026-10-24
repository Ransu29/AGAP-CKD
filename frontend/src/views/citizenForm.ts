// Citizen check-in answers and the PRD v3 payload for /api/risk-check/evaluate (shared with the field
// tablet, ADR 0003). Answers start empty; nothing is assumed. Exact age is asked and sent as the PRD age group.
import { DK } from '../riskCheck/content';

export const emptyCitizenForm = () => ({
  safety: null as boolean | null,
  age: '',
  sex: '',
  municipality: '',
  diabetes: '',
  high_blood_pressure: '',
  medicine: '',
  bp_reading: '',
  heart_disease_stroke: '',
  kidney_stones: '',
  family_history: '',
  height_cm: '',
  weight_kg: '',
  height_weight_unknown: false,
  heavy_outdoor_work: '',
  kidney_status: '',
});
export type CitizenForm = ReturnType<typeof emptyCitizenForm>;

export type StepId =
  | 'age_sex'
  | 'municipality'
  | 'diabetes'
  | 'high_blood_pressure'
  | 'medicine'
  | 'bp_reading'
  | 'heart_disease_stroke'
  | 'kidney_stones'
  | 'family_history'
  | 'height_weight'
  | 'heavy_outdoor_work'
  | 'kidney_status';

export const ageError = (raw: string): string => {
  if (!raw.trim()) return 'Ilagay ang iyong edad.';
  const age = Number(raw);
  return !Number.isInteger(age) || age < 1 || age > 120 ? 'Maglagay ng buong bilang mula 1 hanggang 120.' : '';
};

export const ageGroup = (age: number) =>
  age >= 70 ? '70+' : age >= 60 ? '60-69' : age >= 50 ? '50-59' : age >= 40 ? '40-49' : '18-39';

// PRD v3 questionnaire order. Medicine only after a Yes to diabetes or high BP; BP reading only after high BP
// No or I don't know (content plan C5).
export function stepsFor(form: CitizenForm): StepId[] {
  const steps: StepId[] = ['age_sex', 'municipality', 'diabetes', 'high_blood_pressure'];
  if (form.diabetes === 'Yes' || form.high_blood_pressure === 'Yes') steps.push('medicine');
  if (form.high_blood_pressure === 'No' || form.high_blood_pressure === DK) steps.push('bp_reading');
  steps.push('heart_disease_stroke', 'kidney_stones', 'family_history', 'height_weight', 'heavy_outdoor_work', 'kidney_status');
  return steps;
}

export const bmiInputsValid = (form: CitizenForm) => {
  const h = Number(form.height_cm);
  const w = Number(form.weight_kg);
  return h >= 100 && h <= 230 && w >= 25 && w <= 300;
};

export function stepAnswered(step: StepId, form: CitizenForm): boolean {
  switch (step) {
    case 'age_sex':
      return !ageError(form.age) && !!form.sex;
    case 'height_weight':
      return form.height_weight_unknown || bmiInputsValid(form);
    default:
      return !!form[step];
  }
}

// Under 18 is part of the safety pre-check (PRD v3): such a person is routed to a doctor, not scored.
export const isUnderAge = (form: CitizenForm) => !ageError(form.age) && Number(form.age) < 18;

// Model inputs need a sex of Female or Male; other answers get no level (as designed; team decision).
const SEX = { female: 'Female', male: 'Male' } as Record<string, string>;

export function evaluationPayload(form: CitizenForm) {
  if (form.safety !== false || isUnderAge(form) || !SEX[form.sex]) return null;
  if (!stepsFor(form).every((step) => stepAnswered(step, form))) return null;
  const branch = stepsFor(form);
  return {
    channel: 'app',
    safety: 'No',
    age_group: ageGroup(Number(form.age)),
    sex: SEX[form.sex],
    municipality: form.municipality,
    diabetes: form.diabetes,
    high_blood_pressure: form.high_blood_pressure,
    medicine: branch.includes('medicine') ? form.medicine : null,
    bp_reading: branch.includes('bp_reading') ? form.bp_reading : null,
    heart_disease_stroke: form.heart_disease_stroke,
    kidney_stones: form.kidney_stones,
    family_history: form.family_history,
    height_cm: form.height_weight_unknown ? null : Number(form.height_cm),
    weight_kg: form.height_weight_unknown ? null : Number(form.weight_kg),
    heavy_outdoor_work: form.heavy_outdoor_work,
    kidney_status: form.kidney_status,
  };
}
