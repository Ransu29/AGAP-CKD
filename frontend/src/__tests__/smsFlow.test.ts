import { describe, it, expect } from 'vitest';
import {
  MSG, fitsOneSegment, initialState, itemsFor, matchTown, normalizeReply, parseHeightWeight, questionMessage,
  reply, requestFor, resultMessages, timeout, toGsm, type SmsState, type Town,
} from '../riskCheck/smsFlow';
import { DK, type RiskCheckResult } from '../riskCheck/content';

const TOWNS: Town[] = [
  { municipality: 'City of Calamba', name: 'Calamba' },
  { municipality: 'City of Biñan', name: 'Biñan' },
  { municipality: 'Santa Cruz', name: 'Santa Cruz' },
  { municipality: 'Los Baños', name: 'Los Baños' },
  { municipality: 'City of San Pablo', name: 'San Pablo' },
  { municipality: 'City of San Pedro', name: 'San Pedro' },
];

const last = (list: string[]) => list[list.length - 1];

// Send a sequence of texts and collect every outgoing message.
function run(texts: string[], start: SmsState = initialState()) {
  let state = start;
  const out: string[] = [];
  let request: Record<string, unknown> | undefined;
  for (const text of texts) {
    const step = reply(state, text, TOWNS);
    state = step.state;
    out.push(...step.out);
    if (step.request) request = step.request;
  }
  return { state, out, request };
}

// consent, safety, age 50-59, male, town, diabetes Yes, high BP No, medicine Regularly, BP reading Normal,
// heart No, stones No, family No, height/weight + confirm, outdoor work Yes, never tested.
const FULL = ['CHECK', '1', '2', '3', '2', 'calamba', '1', '2', '1', '1', '2', '2', '2', '165 cm 70 kg', '1', '1', '1'];

describe('SMS flow (PRD v3)', () => {
  it('keeps every fixed message to one GSM-7 segment', () => {
    for (const [name, text] of Object.entries(MSG)) expect(fitsOneSegment(text), name).toBe(true);
  });

  it('keeps every question to one GSM-7 segment, with the progress prefix and the longest branch', () => {
    const answers = { diabetes: 'Yes', high_blood_pressure: 'No' };
    const items = itemsFor(answers);
    items.forEach((_, index) => {
      const text = questionMessage({ ...initialState(), phase: 'question', answers, index });
      expect(fitsOneSegment(text), text).toBe(true);
    });
  });

  it('accepts loose replies and maps yes/no words only where they fit', () => {
    expect(normalizeReply('1')).toBe('1');
    expect(normalizeReply(' 1. ')).toBe('1');
    expect(normalizeReply('isa')).toBe('1');
    expect(normalizeReply('Dalawa')).toBe('2');
    expect(normalizeReply('hindi ko alam')).toBe('0');
    expect(normalizeReply('oo', true)).toBe('1');
    expect(normalizeReply('oo')).toBeNull();
    expect(normalizeReply('maybe')).toBeNull();
  });

  it('matches towns loosely, with or without ñ, "City of" or "Sta."', () => {
    expect(matchTown('calamba', TOWNS)?.municipality).toBe('City of Calamba');
    expect(matchTown('Binan', TOWNS)?.municipality).toBe('City of Biñan');
    expect(matchTown('Sta. Cruz', TOWNS)?.municipality).toBe('Santa Cruz');
    expect(matchTown('los banos', TOWNS)?.municipality).toBe('Los Baños');
    expect(matchTown('San', TOWNS)).toBeNull(); // ambiguous: San Pablo or San Pedro
  });

  it('reads height and weight in either unit and rejects impossible values', () => {
    expect(parseHeightWeight('165 cm 70 kg')).toEqual({ height_cm: 165, weight_kg: 70 });
    expect(parseHeightWeight('165 70')).toEqual({ height_cm: 165, weight_kg: 70 });
    expect(parseHeightWeight("5'5 154 lb")).toEqual({ height_cm: 165, weight_kg: 70 });
    expect(parseHeightWeight('5ft 154lbs')).toEqual({ height_cm: 152, weight_kg: 70 });
    expect(parseHeightWeight('40 cm 70 kg')).toBeNull();
    expect(parseHeightWeight('tall')).toBeNull();
  });

  it('runs a full check in questionnaire order and builds the shared evaluate request', () => {
    const { out, request } = run(FULL);
    expect(out[0]).toBe(MSG.consent);
    expect(out[1]).toBe(MSG.safety);
    expect(out[2]).toMatch(/^\(1\/12\) Ilang taon/);
    expect(out).toContain('165 cm, 70 kg? 1=Oo 2=Mali');
    expect(request).toMatchObject({
      channel: 'sms', safety: 'No', age_group: '50-59', sex: 'Male', municipality: 'City of Calamba',
      diabetes: 'Yes', high_blood_pressure: 'No', medicine: 'Regularly', bp_reading: 'Normal',
      heart_disease_stroke: 'No', kidney_stones: 'No', family_history: 'No', height_cm: 165, weight_kg: 70,
      heavy_outdoor_work: 'Yes', kidney_status: 'Never tested',
    });
  });

  it('sends people with warning signs to a doctor without a risk level', () => {
    const { out, request } = run(['CHECK', '1', '1']);
    expect(last(out)).toBe(MSG.seeDoctor);
    expect(request).toBeUndefined();
  });

  it('gives education only when consent is declined', () => {
    const { out, state } = run(['CHECK', '2']);
    expect(last(out)).toBe(MSG.declined);
    expect(state.phase).toBe('idle');
  });

  it('re-asks an unclear reply once, then records "I don\'t know"', () => {
    const { out, state } = run(['CHECK', '1', '2', '3', '2', 'calamba', 'siguro', 'ewan']);
    expect(out).toContain(MSG.unclear);
    expect(out).toContain(MSG.treatedAsDK);
    expect(state.answers.diabetes).toBe(DK);
  });

  it('goes BACK one question and keeps branching consistent', () => {
    const { state } = run(['CHECK', '1', '2', '3', '2', 'calamba', '1', '1', 'BACK', 'BACK', '2']);
    expect(state.answers.diabetes).toBe('No');
    expect(state.answers.medicine).toBeUndefined();
  });

  it('still scores a stopped check from the answers given, filling the rest as "I don\'t know"', () => {
    const { out, request } = run(['CHECK', '1', '2', '3', '2', 'calamba', 'STOP']);
    expect(last(out)).toBe(MSG.stoppedPrefix);
    expect(request).toMatchObject({ diabetes: DK, high_blood_pressure: DK, kidney_status: DK, medicine: null });
  });

  it('gives no level when stopped before age, sex and town', () => {
    const { out, request } = run(['CHECK', '1', '2', 'STOP']);
    expect(last(out)).toBe(MSG.stopNoLevel);
    expect(request).toBeUndefined();
  });

  it('pauses on a timeout and resumes on TULOY at the same question', () => {
    const before = run(['CHECK', '1', '2', '3']).state;
    const paused = timeout(before);
    expect(paused.out).toEqual([MSG.timeout]);
    const resumed = reply(paused.state, 'tuloy', TOWNS);
    expect(resumed.out[0]).toMatch(/^\(2\/12\) Kasarian/);
  });

  const result = (level: 'Low' | 'Medium' | 'High', code: 'recheck' | 'bp_sugar_first' | 'kidney_test'): RiskCheckResult => ({
    route: 'result', level, reasons: ['diabetes'], tips: ['keep_medicine'], age_group: '50-59',
    next_step: { code, soon: level === 'High', next_check: code === 'recheck' ? '2027-10' : null, next_kidney_test: code === 'kidney_test' ? '2027-10' : null },
    where: { municipality: 'City of Biñan', shown_from: null, facilities: [{ name: 'Biñan City Health Office – Main “Annex”', type: 'Health center', municipality: 'City of Biñan', kidney_tests: 'Unknown', verification: 'Not yet verified, call ahead' }] },
  });

  it('sends the result in single-segment messages, with a facility only for Medium or High', () => {
    const referred = resultMessages(initialState(), result('High', 'kidney_test'));
    expect(referred.out[0]).toContain('MATAAS (High)');
    expect(referred.out[0]).toContain('Hindi ito diagnosis');
    expect(referred.out[1]).toContain('Next kidney test: Okt 2027');
    expect(referred.out[2]).toContain('Pinakamalapit: Biñan City Health Office - Main "Annex"');
    expect(last(referred.out)).toBe(MSG.reminderAsk);
    referred.out.forEach((text) => expect(fitsOneSegment(text), text).toBe(true));

    const low = resultMessages(initialState(), result('Low', 'recheck'));
    expect(low.out[1]).toContain('mag-check ulit sa Okt 2027');
    expect(low.out[2]).toMatch(/^Tip:/);
    expect(low.out.join(' ')).not.toMatch(/urine test(?! lang)/);
  });

  it('confirms reminders by level and records a self-reported DONE', () => {
    const referred = resultMessages(initialState(), result('Medium', 'kidney_test')).state;
    expect(reply(referred, '1', TOWNS).out[0]).toBe(MSG.reminderYesReferred);
    const low = resultMessages(initialState(), result('Low', 'recheck')).state;
    expect(reply(low, '1', TOWNS).out[0]).toContain('Okt 2027');
    const done = reply(referred, '1', TOWNS).state;
    expect(reply(done, 'DONE', TOWNS).out[0]).toBe(MSG.doneThanks);
  });

  it('turns register names into GSM-7 text', () => {
    expect(toGsm('Biñan – “Annex” ’s')).toBe('Biñan - "Annex" \'s');
  });

  it('fills unanswered items as "I don\'t know" in the request', () => {
    const request = requestFor({ age_group: '18-39', sex: 'Female', municipality: 'City of Calamba' });
    expect(request).toMatchObject({ diabetes: DK, bp_reading: DK, medicine: null, height_cm: null });
  });
});
