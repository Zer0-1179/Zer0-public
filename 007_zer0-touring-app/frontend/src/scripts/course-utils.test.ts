import { describe, expect, it } from 'vitest';
import { buildMapUrl, computeEnrichState, escHtml, fmtHours, getWeatherMeta } from './course-utils';

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

describe('buildMapUrl', () => {
  const dest = { destination: '箱根', dest_lat: 35.23, dest_lon: 139.03 };

  it('GPS現在地モード: userLat/userLonをoriginにする', () => {
    const url = buildMapUrl(dest, 35.68, 139.76);
    expect(url).toContain('origin=35.680000,139.760000');
  });

  it('起点未確定(null)ならoriginパラメータを付けない', () => {
    const url = buildMapUrl(dest, null, null);
    expect(url).not.toContain('origin=');
  });

  it('緯度0付近でも起点なし扱いにしない(falsy-zero対策の回帰防止)', () => {
    // 実運用上ありえないが、真偽値判定(userLat&&userLon)だと0はfalsyになり
    // 起点なし扱いになってしまうバグが過去にあった
    const url = buildMapUrl(dest, 0, 139.76);
    expect(url).toContain('origin=0.000000,139.760000');
  });

  it('dest_lat/lonが無ければ目的地名をエンコードして使う', () => {
    const url = buildMapUrl({ destination: '箱根' }, 35.68, 139.76);
    expect(url).toContain(`destination=${encodeURIComponent('箱根')}`);
  });

  it('未検証のoutbound_spotsをナビwaypointsに渡さない', () => {
    const c = { ...dest, outbound_spots: [{ name: '道の駅A', lat: 35.5, lon: 139.5 }] };
    const url = buildMapUrl(c, 35.68, 139.76);
    expect(url).not.toContain('waypoints=');
  });

  it('座標検証済みoutbound_waypointsを表示用スポットより優先する', () => {
    const c = {
      ...dest,
      outbound_spots: [{ name: '表示のみの場所' }],
      outbound_waypoints: [{ name: '道の駅A', lat: 35.5, lon: 139.5 }],
    };
    const url = buildMapUrl(c, 35.68, 139.76);
    expect(url).toContain('waypoints=35.5,139.5');
    expect(url).not.toContain(encodeURIComponent('表示のみの場所'));
  });
});

describe('computeEnrichState', () => {
  it('ジオコーディング・天気とも成功: enriched=true, enrichFailed=false', () => {
    const state = computeEnrichState({ dest_lat: 35.23, dest_weather_code: 1 });
    expect(state).toEqual({ enriched: true, enrichFailed: false });
  });

  it('目的地ジオコーディング失敗(dest_lat無し): 次回再試行できるようenriched=falseのまま', () => {
    // 過去のバグ: ここでenriched=trueにしてしまい天気取得が永久にスキップされていた
    const state = computeEnrichState({});
    expect(state).toEqual({ enriched: false, enrichFailed: true });
  });

  it('ジオコーディングは成功したが天気だけ取得失敗: enriched=trueのままenrichFailed=true', () => {
    const state = computeEnrichState({ dest_lat: 35.23 });
    expect(state).toEqual({ enriched: true, enrichFailed: true });
  });

  it('通信例外等でレスポンス自体が無い場合もenrichFailed=true', () => {
    const state = computeEnrichState(null);
    expect(state).toEqual({ enriched: false, enrichFailed: true });
  });
});
