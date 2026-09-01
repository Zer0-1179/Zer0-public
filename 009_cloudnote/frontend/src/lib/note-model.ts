import type { JSONContent } from '@tiptap/core';

import type { SaveStatus } from './save-status';

export type RichTextDocument = {
  version: 1;
  doc: JSONContent;
};

export type Notebook = {
  id: string;
  title: string;
};

export type Section = {
  id: string;
  notebook_id: string;
  title: string;
};

export type Page = {
  id: string;
  section_id: string;
  title: string;
  tags: string[];
  content: RichTextDocument;
};

export type DeletedPage = {
  page: Page;
  deleted_at: string;
  restore_until: string;
  sibling_index: number;
};

export type PageDirection = 'up' | 'down';

export function paragraph(text: string): RichTextDocument {
  return {
    version: 1,
    doc: {
      type: 'doc',
      content: [{ type: 'paragraph', content: [{ type: 'text', text }] }],
    },
  };
}

export function plain_text_from_document(node: JSONContent): string {
  const own_text = typeof node.text === 'string' ? node.text : '';
  const child_text = (node.content ?? []).map(plain_text_from_document).join(' ');

  return `${own_text} ${child_text}`.replace(/\s+/g, ' ').trim();
}

function normalize(value: string): string {
  return value.normalize('NFKC').toLocaleLowerCase('ja-JP').trim();
}

export function search_pages(pages: Page[], query: string, tag: string | null): Page[] {
  const terms = normalize(query).split(/\s+/).filter(Boolean);
  const normalized_tag = tag ? normalize(tag) : null;

  return pages.filter((page) => {
    const tags = page.tags.map(normalize);
    const searchable = normalize(`${page.title} ${page.tags.join(' ')} ${plain_text_from_document(page.content.doc)}`);
    const matches_terms = terms.every((term) => searchable.includes(term));
    const matches_tag = !normalized_tag || tags.includes(normalized_tag);

    return matches_terms && matches_tag;
  });
}

export function move_page(pages: Page[], page_id: string, target_section_id: string): Page[] {
  const page = pages.find((item) => item.id === page_id);
  if (!page || page.section_id === target_section_id) return pages;

  const moved_page = { ...page, section_id: target_section_id };
  const remaining = pages.filter((item) => item.id !== page_id);
  const target_indexes = remaining
    .map((item, index) => ({ item, index }))
    .filter(({ item }) => item.section_id === target_section_id)
    .map(({ index }) => index);
  const last_target_index = target_indexes.at(-1);

  if (last_target_index === undefined) return [...remaining, moved_page];
  return [...remaining.slice(0, last_target_index + 1), moved_page, ...remaining.slice(last_target_index + 1)];
}

export function reorder_page_within_section(
  pages: Page[],
  page_id: string,
  direction: PageDirection,
): Page[] {
  const page = pages.find((item) => item.id === page_id);
  if (!page) return pages;

  const sibling_indexes = pages
    .map((item, index) => ({ item, index }))
    .filter(({ item }) => item.section_id === page.section_id)
    .map(({ index }) => index);
  const sibling_position = sibling_indexes.indexOf(pages.findIndex((item) => item.id === page_id));
  const target_position = direction === 'up' ? sibling_position - 1 : sibling_position + 1;

  if (sibling_position < 0 || target_position < 0 || target_position >= sibling_indexes.length) {
    return pages;
  }

  const result = [...pages];
  const from_index = sibling_indexes[sibling_position];
  const target_index = sibling_indexes[target_position];
  [result[from_index], result[target_index]] = [result[target_index], result[from_index]];

  return result;
}

export function delete_page(
  pages: Page[],
  page_id: string,
  deleted_at: string,
): { pages: Page[]; deleted_page: DeletedPage | null } {
  const page_index = pages.findIndex((page) => page.id === page_id);
  if (page_index < 0) return { pages, deleted_page: null };

  const page = pages[page_index];
  const sibling_index = pages
    .slice(0, page_index)
    .filter((item) => item.section_id === page.section_id).length;
  const restore_until = new Date(new Date(deleted_at).getTime() + 10 * 24 * 60 * 60 * 1000).toISOString();

  return {
    pages: pages.filter((item) => item.id !== page_id),
    deleted_page: { page, deleted_at, restore_until, sibling_index },
  };
}

export function restore_page(pages: Page[], deleted_page: DeletedPage): Page[] {
  if (pages.some((page) => page.id === deleted_page.page.id)) return pages;

  const section_indexes = pages
    .map((page, index) => ({ page, index }))
    .filter(({ page }) => page.section_id === deleted_page.page.section_id)
    .map(({ index }) => index);
  const insert_before = section_indexes[deleted_page.sibling_index];

  if (insert_before === undefined) {
    const last_sibling = section_indexes.at(-1);
    if (last_sibling === undefined) return [...pages, deleted_page.page];
    return [...pages.slice(0, last_sibling + 1), deleted_page.page, ...pages.slice(last_sibling + 1)];
  }

  return [...pages.slice(0, insert_before), deleted_page.page, ...pages.slice(insert_before)];
}

export function can_move_page(status: SaveStatus): boolean {
  return status === 'saved';
}
