// Plain-English sensor labels (docs/techstack.md section 5.2, from the C-MAPSS documentation).
// VERIFY against Saxena et al., 2008 before the pitch.
export const SENSOR_LABELS: Record<string, string> = {
  s2: 'Low-pressure compressor outlet temperature',
  s3: 'High-pressure compressor outlet temperature',
  s4: 'Low-pressure turbine outlet temperature',
  s7: 'High-pressure compressor outlet pressure',
  s8: 'Fan speed',
  s9: 'Core speed',
  s11: 'High-pressure compressor static pressure',
  s12: 'Fuel flow to pressure ratio',
  s13: 'Corrected fan speed',
  s14: 'Corrected core speed',
  s15: 'Bypass ratio',
  s17: 'Bleed enthalpy',
  s20: 'High-pressure turbine coolant bleed',
  s21: 'Low-pressure turbine coolant bleed',
}
export const SENSOR_IDS = Object.keys(SENSOR_LABELS)
