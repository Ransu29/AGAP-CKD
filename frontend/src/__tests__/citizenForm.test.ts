import { describe, expect, it } from 'vitest';
import { ageError, ageGroup, emptyCitizenForm, evaluationPayload, isUnderAge, stepAnswered, stepsFor } from '../views/citizenForm';

const complete = {
  ...emptyCitizenForm(), safety: false, age: '52', sex: 'female', municipality: 'City of Calamba',
  diabetes: 'No', high_blood_pressure: 'No', bp_reading: "I don't know", heart_disease_stroke: 'No', kidney_stones: 'No',
  family_history: "I don't know", height_cm: '158', weight_kg: '64', heavy_outdoor_work: 'No', kidney_status: 'Never tested',
};

describe('citizen answer integrity', () => {
  it('starts without assumed answers', () => {
    const draft = emptyCitizenForm();
    expect(draft.age).toBe(''); expect(draft.safety).toBeNull(); expect(draft.diabetes).toBe('');
    expect(stepAnswered('age_sex', draft)).toBe(false); expect(evaluationPayload(draft)).toBeNull();
  });
  it('rejects invalid ages without coercion', () => {
    for (const age of ['', '0', '-1', '1.5', '121', 'abc']) expect(ageError(age)).not.toBe('');
    expect(ageError('52')).toBe('');
  });
  it('distinguishes unanswered from explicit uncertainty', () => {
    expect(stepAnswered('bp_reading', { ...complete, bp_reading: '' })).toBe(false);
    expect(stepAnswered('bp_reading', complete)).toBe(true);
    expect(stepAnswered('height_weight', { ...complete, height_cm: '', weight_kg: '' })).toBe(false);
    expect(stepAnswered('height_weight', { ...complete, height_cm: '', weight_kg: '', height_weight_unknown: true })).toBe(true);
  });
  it('follows the PRD v3 order and branching', () => {
    expect(stepsFor(complete)).toEqual(['age_sex', 'municipality', 'diabetes', 'high_blood_pressure', 'bp_reading',
      'heart_disease_stroke', 'kidney_stones', 'family_history', 'height_weight', 'heavy_outdoor_work', 'kidney_status']);
    const withMedicine = stepsFor({ ...complete, diabetes: 'Yes', high_blood_pressure: 'Yes' });
    expect(withMedicine).toContain('medicine');
    expect(withMedicine).not.toContain('bp_reading');
  });
  it('does not convert inclusive sex, safety or under-age answers into model inputs', () => {
    for (const sex of ['intersex', 'prefer_not_to_say', '']) expect(evaluationPayload({ ...complete, sex })).toBeNull();
    expect(evaluationPayload({ ...complete, safety: true })).toBeNull();
    expect(evaluationPayload({ ...complete, safety: null })).toBeNull();
    expect(isUnderAge({ ...complete, age: '16' })).toBe(true);
    expect(evaluationPayload({ ...complete, age: '16' })).toBeNull();
  });
  it('sends the PRD v3 answers to the shared risk check', () => {
    const payload = evaluationPayload(complete)!;
    expect(payload).toMatchObject({ channel: 'app', safety: 'No', age_group: '50-59', sex: 'Female', diabetes: 'No',
      bp_reading: "I don't know", medicine: null, height_cm: 158, weight_kg: 64, kidney_status: 'Never tested' });
    expect(evaluationPayload({ ...complete, height_cm: '', weight_kg: '', height_weight_unknown: true })).toMatchObject({ height_cm: null, weight_kg: null });
    expect([39, 40, 59, 60, 70].map(ageGroup)).toEqual(['18-39', '40-49', '50-59', '60-69', '70+']);
  });
});
