import type { Technician } from '@/lib/types'

// Fictional roster. Two French speakers, two backups. field_page_id is the unguessable slug in /field/<id>.
export const TECHNICIANS: Technician[] = [
  { id: 1, name: 'Aiden Walker', station_code: 'EDS', shift: 'day', language: 'en', is_backup: false, online: true, field_page_id: 't-9f3k2' },
  { id: 2, name: 'Priya Nair', station_code: 'EDS', shift: 'night', language: 'en', is_backup: true, online: false, field_page_id: 't-4m8q1' },
  { id: 3, name: 'Marc Tremblay', station_code: 'GPR', shift: 'day', language: 'fr', is_backup: false, online: true, field_page_id: 't-7d2x9' },
  { id: 4, name: 'Chloe Ouellet', station_code: 'GPR', shift: 'night', language: 'fr', is_backup: true, online: false, field_page_id: 't-1b6v3' },
  { id: 5, name: 'Dmitri Volkov', station_code: 'HIN', shift: 'day', language: 'en', is_backup: false, online: true, field_page_id: 't-5h0c7' },
  { id: 6, name: 'Sana Rahman', station_code: 'HIN', shift: 'night', language: 'en', is_backup: false, online: false, field_page_id: 't-2n9j4' },
  { id: 7, name: 'Tom Reilly', station_code: 'WHT', shift: 'day', language: 'en', is_backup: false, online: true, field_page_id: 't-8w5p6' },
  { id: 8, name: 'Ngozi Okafor', station_code: 'WHT', shift: 'night', language: 'en', is_backup: false, online: false, field_page_id: 't-3t7z2' },
  { id: 9, name: 'Lena Fischer', station_code: 'DRH', shift: 'day', language: 'en', is_backup: false, online: true, field_page_id: 't-6k1r8' },
  { id: 10, name: 'Mateo Silva', station_code: 'DRH', shift: 'night', language: 'en', is_backup: false, online: false, field_page_id: 't-0g4y5' },
  { id: 11, name: 'Hannah Cho', station_code: 'EDS', shift: 'day', language: 'en', is_backup: false, online: true, field_page_id: 't-9a2e7' },
  { id: 12, name: 'Jon Blackfoot', station_code: 'HIN', shift: 'day', language: 'en', is_backup: true, online: false, field_page_id: 't-5s8d1' },
]
