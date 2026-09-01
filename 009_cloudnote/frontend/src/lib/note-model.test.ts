import { describe, expect, it } from 'vitest';

import {
  can_move_page,
  delete_page,
  move_page,
  paragraph,
  plain_text_from_document,
  reorder_page_within_section,
  restore_page,
  search_pages,
  type Page,
} from './note-model';

const pages: Page[] = [
  { id: 'one', section_id: 'first', title: 'React入門', tags: ['学習'], content: paragraph('状態を扱います') },
  { id: 'two', section_id: 'second', title: 'CloudNote計画', tags: ['設計'], content: paragraph('ノートを整理します') },
];

describe('plain_text_from_document', () => {
  it('Tiptap JSONから表示用の本文テキストを抽出する', () => {
    expect(plain_text_from_document(pages[0].content.doc)).toBe('状態を扱います');
  });
});

describe('search_pages', () => {
  it('複数語をANDで検索する', () => {
    expect(search_pages(pages, 'cloudnote 整理', null).map((page) => page.id)).toEqual(['two']);
  });

  it('タグで絞り込む', () => {
    expect(search_pages(pages, '', '学習').map((page) => page.id)).toEqual(['one']);
  });
});

describe('move_page', () => {
  it('移動対象だけのSectionを変更する', () => {
    expect(move_page(pages, 'one', 'second').map((page) => [page.id, page.section_id])).toEqual([
      ['two', 'second'],
      ['one', 'second'],
    ]);
  });

  it('保存完了前または保存失敗中のPageは移動できない', () => {
    expect(can_move_page('saving')).toBe(false);
    expect(can_move_page('unsaved')).toBe(false);
    expect(can_move_page('saved')).toBe(true);
    expect(can_move_page('failed')).toBe(false);
  });
});

describe('reorder_page_within_section', () => {
  it('同じSection内だけでPageの順番を入れ替える', () => {
    const ordered_pages = [pages[0], { ...pages[0], id: 'three', title: '次のメモ' }, pages[1]];

    expect(reorder_page_within_section(ordered_pages, 'three', 'up').map((page) => page.id)).toEqual([
      'three',
      'one',
      'two',
    ]);
  });

  it('先頭のPageを上へ移動しても順番を変えない', () => {
    expect(reorder_page_within_section(pages, 'one', 'up')).toEqual(pages);
  });
});

describe('delete_page / restore_page', () => {
  it('削除時に10日間の復元期限と元の位置を残す', () => {
    const deleted = delete_page(pages, 'one', '2026-08-24T00:00:00.000Z');

    expect(deleted.pages.map((page) => page.id)).toEqual(['two']);
    expect(deleted.deleted_page).toMatchObject({
      page: { id: 'one' },
      restore_until: '2026-09-03T00:00:00.000Z',
      sibling_index: 0,
    });
  });

  it('復元時にSection内の元の位置へ戻す', () => {
    const source = [
      pages[0],
      { ...pages[0], id: 'three', title: '次のメモ' },
      pages[1],
    ];
    const deleted = delete_page(source, 'one', '2026-08-24T00:00:00.000Z');

    expect(restore_page(deleted.pages, deleted.deleted_page!).map((page) => page.id)).toEqual([
      'one',
      'three',
      'two',
    ]);
  });
});
