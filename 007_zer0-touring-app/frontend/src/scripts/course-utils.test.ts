import { describe, expect, it } from 'vitest';
import { escHtml, fmtHours, getWeatherMeta } from './course-utils';

describe('escHtml', () => {
  it('HTMLの特殊文字をエスケープする', () => {
    expect(escHtml('<script>alert("x")</script>')).toBe('&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;');
  });

  it('null/undefinedは空文字にする', () => {
    expect(escHtml(null)).toBe('');
    expect(escHtml(undefined)).toBe('');
  });

  it('数値もそのまま文字列化する', () => {
    expect(escHtml(123)).toBe('123');
  });
});

describe('fmtHours', () => {
  it('10分未満は10分単位で切り上げる', () => {
    expect(fmtHours(0.05)).toBe('約10分');
  });

  it('分だけの場合は「約N分」', () => {
    expect(fmtHours(0.5)).toBe('約30分');
  });

  it('時間だけの場合は「約N時間」', () => {
    expect(fmtHours(2)).toBe('約2時間');
  });

  it('時間と分がある場合は「約N時間M分」', () => {
    expect(fmtHours(1.25)).toBe('約1時間20分');
  });

  it('端数は10分単位で切り上げられる', () => {
    expect(fmtHours(1.51)).toBe('約1時間40分'); // 90.6分 → 100分に切り上げ
  });
});

describe('getWeatherMeta', () => {
  it('晴れ(0)は最高スコア', () => {
    const meta = getWeatherMeta(0);
    expect(meta.score).toBe(5);
    expect(meta.label).toBe('絶好の日和！');
  });

  it('雷雨(95以上)は走行危険で最低スコア', () => {
    const meta = getWeatherMeta(95);
    expect(meta.score).toBe(0);
    expect(meta.label).toBe('走行危険');
  });

  it('雨(51-67)は雨天注意', () => {
    expect(getWeatherMeta(61).label).toBe('雨天注意');
    expect(getWeatherMeta(67).label).toBe('雨天注意');
  });

  it('未定義のコードはデフォルト値にフォールバックする', () => {
    const meta = getWeatherMeta(20);
    expect(meta.label).toBe('まずまず');
  });
});
