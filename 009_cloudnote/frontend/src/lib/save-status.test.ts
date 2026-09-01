import { describe, expect, it } from 'vitest';

import { save_status_label } from './save-status';

describe('save_status_label', () => {
  it.each([
    ['saved', '保存済み'],
    ['saving', '保存中'],
    ['unsaved', '未保存'],
  ] as const)('%s の表示名を返す', (status, expected) => {
    expect(save_status_label(status)).toBe(expected);
  });
});
