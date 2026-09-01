import { EditorContent, useEditor } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import { useEffect, useMemo, useRef, useState } from 'react';

import { type SaveStatus, save_status_label } from '../lib/save-status';
import {
  can_move_page,
  delete_page,
  move_page,
  paragraph,
  reorder_page_within_section,
  restore_page,
  search_pages,
  type DeletedPage,
  type Notebook,
  type Page,
  type RichTextDocument,
  type Section,
} from '../lib/note-model';

const NOTEBOOKS: Notebook[] = [
  { id: 'work', title: '仕事' },
  { id: 'learning', title: '学び' },
  { id: 'ideas', title: 'アイデア' },
];

const SECTIONS: Section[] = [
  { id: 'planning', notebook_id: 'work', title: '企画' },
  { id: 'meetings', notebook_id: 'work', title: 'ミーティング' },
  { id: 'frontend', notebook_id: 'learning', title: 'フロントエンド' },
  { id: 'features', notebook_id: 'ideas', title: '機能メモ' },
];

const PAGES: Page[] = [
  {
    id: 'cloudnote-mvp',
    section_id: 'planning',
    title: 'CloudNote MVP',
    tags: ['CloudNote', '計画'],
    content: paragraph('まずは、使いやすいノート画面を作ります。'),
  },
  {
    id: 'next-steps',
    section_id: 'planning',
    title: '次に決めること',
    tags: ['設計'],
    content: paragraph('ダミーデータで画面操作を試します。'),
  },
  {
    id: 'react-notes',
    section_id: 'frontend',
    title: 'Reactメモ',
    tags: ['React', '学習'],
    content: paragraph('状態が変わる画面を部品として作る仕組みです。'),
  },
];

function format_date_time(value: string): string {
  return new Intl.DateTimeFormat('ja-JP', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
}

function RichTextEditor({
  content,
  on_change,
}: {
  content: RichTextDocument;
  on_change: (next_content: RichTextDocument) => void;
}) {
  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        blockquote: false,
        code: false,
        codeBlock: false,
        horizontalRule: false,
        strike: false,
        heading: { levels: [2] },
        link: {
          openOnClick: false,
          defaultProtocol: 'https',
          isAllowedUri: (url) => /^https?:\/\//i.test(url),
        },
      }),
    ],
    content: content.doc,
    immediatelyRender: false,
    editorProps: {
      attributes: {
        class: 'editor-content',
        'aria-label': 'Page本文',
      },
    },
    onUpdate: ({ editor: updated_editor }) =>
      on_change({ version: 1, doc: updated_editor.getJSON() }),
  });

  useEffect(() => {
    if (editor && JSON.stringify(content.doc) !== JSON.stringify(editor.getJSON())) {
      editor.commands.setContent(content.doc, { emitUpdate: false });
    }
  }, [content, editor]);

  if (!editor) {
    return <p className="editor-loading">エディタを準備しています…</p>;
  }

  const set_link = () => {
    const href = window.prompt('https:// から始まるリンク先のURLを入力してください');
    if (!href) {
      return;
    }

    if (!/^https?:\/\//i.test(href)) {
      window.alert('http:// または https:// から始まるURLだけを使えます。');
      return;
    }

    editor.chain().focus().extendMarkRange('link').setLink({ href }).run();
  };

  return (
    <section className="editor-shell" aria-label="リッチテキストエディタ">
      <div className="editor-toolbar" role="toolbar" aria-label="書式">
        <button
          type="button"
          className={editor.isActive('bold') ? 'is-active' : ''}
          onClick={() => editor.chain().focus().toggleBold().run()}
          aria-label="太字"
        >
          B
        </button>
        <button
          type="button"
          className={editor.isActive('italic') ? 'is-active' : ''}
          onClick={() => editor.chain().focus().toggleItalic().run()}
          aria-label="斜体"
        >
          I
        </button>
        <button
          type="button"
          className={editor.isActive('heading', { level: 2 }) ? 'is-active' : ''}
          onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
        >
          見出し
        </button>
        <button
          type="button"
          className={editor.isActive('bulletList') ? 'is-active' : ''}
          onClick={() => editor.chain().focus().toggleBulletList().run()}
        >
          箇条書き
        </button>
        <button
          type="button"
          className={editor.isActive('orderedList') ? 'is-active' : ''}
          onClick={() => editor.chain().focus().toggleOrderedList().run()}
        >
          番号付き
        </button>
        <button type="button" onClick={set_link}>
          リンク
        </button>
      </div>
      <EditorContent editor={editor} />
    </section>
  );
}

export default function CloudNoteApp() {
  const [notebooks, set_notebooks] = useState(NOTEBOOKS);
  const [sections_state, set_sections_state] = useState(SECTIONS);
  const [pages, set_pages] = useState(PAGES);
  const [selected_notebook_id, set_selected_notebook_id] = useState('work');
  const [selected_section_id, set_selected_section_id] = useState('planning');
  const [selected_page_id, set_selected_page_id] = useState('cloudnote-mvp');
  const [save_statuses, set_save_statuses] = useState<Record<string, SaveStatus>>(
    () => Object.fromEntries(PAGES.map((page) => [page.id, 'saved'])),
  );
  const [is_drawer_open, set_is_drawer_open] = useState(false);
  const [search_query, set_search_query] = useState('');
  const [selected_tag, set_selected_tag] = useState<string | null>(null);
  const [move_target_section_id, set_move_target_section_id] = useState('planning');
  const [fail_next_save, set_fail_next_save] = useState(false);
  const [deleted_pages, set_deleted_pages] = useState<DeletedPage[]>([]);
  const [page_pending_delete, set_page_pending_delete] = useState<Page | null>(null);
  const [delete_restore_error, set_delete_restore_error] = useState<string | null>(null);
  const [fail_next_delete_restore, set_fail_next_delete_restore] = useState(false);
  const save_timers = useRef<Record<string, { finish?: number; start?: number }>>({});

  const selected_page = pages.find((page) => page.id === selected_page_id) ?? pages[0];
  const save_status = save_statuses[selected_page.id] ?? 'saved';
  const sections = useMemo(
    () => sections_state.filter((section) => section.notebook_id === selected_notebook_id),
    [sections_state, selected_notebook_id],
  );
  const section_pages = pages.filter((page) => page.section_id === selected_section_id);
  const available_tags = [...new Set(pages.flatMap((page) => page.tags))].sort((left, right) => left.localeCompare(right, 'ja'));
  const search_results = useMemo(
    () => search_pages(pages, search_query, selected_tag).slice(0, 50),
    [pages, search_query, selected_tag],
  );

  useEffect(() => {
    set_move_target_section_id(selected_page.section_id);
  }, [selected_page.id, selected_page.section_id]);

  useEffect(() => () => {
    Object.values(save_timers.current).forEach(({ start, finish }) => {
      if (start) window.clearTimeout(start);
      if (finish) window.clearTimeout(finish);
    });
  }, []);

  const schedule_save = (page_id: string, should_fail: boolean) => {
    const previous = save_timers.current[page_id];
    if (previous?.start) window.clearTimeout(previous.start);
    if (previous?.finish) window.clearTimeout(previous.finish);

    set_save_statuses((current) => ({ ...current, [page_id]: 'unsaved' }));
    const start = window.setTimeout(() => {
      set_save_statuses((current) => ({ ...current, [page_id]: 'saving' }));
    }, 400);
    const finish = window.setTimeout(() => {
      set_save_statuses((current) => ({ ...current, [page_id]: should_fail ? 'failed' : 'saved' }));
    }, 1200);
    save_timers.current[page_id] = { start, finish };
  };

  const select_notebook = (notebook_id: string) => {
    const next_section = sections_state.find((section) => section.notebook_id === notebook_id);
    const next_page = pages.find((page) => page.section_id === next_section?.id);

    set_selected_notebook_id(notebook_id);
    if (next_section) {
      set_selected_section_id(next_section.id);
    }
    if (next_page) {
      set_selected_page_id(next_page.id);
    }
    set_is_drawer_open(false);
  };

  const select_section = (section_id: string) => {
    const next_page = pages.find((page) => page.section_id === section_id);
    const next_section = sections_state.find((section) => section.id === section_id);
    if (next_section) {
      set_selected_notebook_id(next_section.notebook_id);
    }
    set_selected_section_id(section_id);
    if (next_page) {
      set_selected_page_id(next_page.id);
    }
    set_is_drawer_open(false);
  };

  const update_page = (updates: Partial<Pick<Page, 'title' | 'content' | 'tags'>>) => {
    set_pages((current_pages) =>
      current_pages.map((page) => (page.id === selected_page.id ? { ...page, ...updates } : page)),
    );
    const should_fail = fail_next_save;
    set_fail_next_save(false);
    schedule_save(selected_page.id, should_fail);
  };

  const create_page = () => {
    const page_id = `page-${crypto.randomUUID()}`;
    const next_page: Page = {
      id: page_id,
      section_id: selected_section_id,
      title: '新しいPage',
      tags: [],
      content: paragraph('ここにメモを書きます。'),
    };

    set_pages((current_pages) => [...current_pages, next_page]);
    set_selected_page_id(page_id);
    set_save_statuses((current) => ({ ...current, [page_id]: 'unsaved' }));
    schedule_save(page_id, false);
  };

  const create_section = () => {
    const section_id = `section-${crypto.randomUUID()}`;
    const page_id = `page-${crypto.randomUUID()}`;
    const next_section: Section = { id: section_id, notebook_id: selected_notebook_id, title: '新しいSection' };
    const next_page: Page = { id: page_id, section_id, title: '新しいPage', tags: [], content: paragraph('ここにメモを書きます。') };

    set_sections_state((current) => [...current, next_section]);
    set_pages((current) => [...current, next_page]);
    set_selected_section_id(section_id);
    set_selected_page_id(page_id);
    set_save_statuses((current) => ({ ...current, [page_id]: 'unsaved' }));
    schedule_save(page_id, false);
  };

  const create_notebook = () => {
    const notebook_id = `notebook-${crypto.randomUUID()}`;
    const section_id = `section-${crypto.randomUUID()}`;
    const page_id = `page-${crypto.randomUUID()}`;
    const next_notebook: Notebook = { id: notebook_id, title: '新しいNotebook' };
    const next_section: Section = { id: section_id, notebook_id, title: '新しいSection' };
    const next_page: Page = { id: page_id, section_id, title: '新しいPage', tags: [], content: paragraph('ここにメモを書きます。') };

    set_notebooks((current) => [...current, next_notebook]);
    set_sections_state((current) => [...current, next_section]);
    set_pages((current) => [...current, next_page]);
    set_selected_notebook_id(notebook_id);
    set_selected_section_id(section_id);
    set_selected_page_id(page_id);
    set_save_statuses((current) => ({ ...current, [page_id]: 'unsaved' }));
    schedule_save(page_id, false);
  };

  const add_tag = () => {
    const next_tag = window.prompt('追加するタグを入力してください')?.trim();
    if (next_tag && !selected_page.tags.includes(next_tag)) {
      update_page({ tags: [...selected_page.tags, next_tag] });
    }
  };

  const move_selected_page = () => {
    if (!can_move_page(save_status) || move_target_section_id === selected_page.section_id) return;
    const target_section = sections_state.find((section) => section.id === move_target_section_id);
    if (!target_section) return;

    set_pages((current) => move_page(current, selected_page.id, move_target_section_id));
    set_selected_notebook_id(target_section.notebook_id);
    set_selected_section_id(target_section.id);
  };

  const reorder_selected_page = (direction: 'up' | 'down') => {
    if (!can_move_page(save_status)) return;
    set_pages((current) => reorder_page_within_section(current, selected_page.id, direction));
  };

  const confirm_delete_page = () => {
    if (!page_pending_delete || !can_move_page(save_status)) return;
    if (fail_next_delete_restore) {
      set_fail_next_delete_restore(false);
      set_delete_restore_error('削除に失敗しました。Pageの内容は変更されていません。もう一度実行できます。');
      return;
    }

    const result = delete_page(pages, page_pending_delete.id, new Date().toISOString());
    if (!result.deleted_page) return;

    const pending_timers = save_timers.current[page_pending_delete.id];
    if (pending_timers?.start) window.clearTimeout(pending_timers.start);
    if (pending_timers?.finish) window.clearTimeout(pending_timers.finish);
    delete save_timers.current[page_pending_delete.id];
    const next_page = result.pages.find((page) => page.section_id === page_pending_delete.section_id) ?? result.pages[0];
    const next_section = sections_state.find((section) => section.id === next_page?.section_id);
    set_pages(result.pages);
    set_deleted_pages((current) => [...current, result.deleted_page!]);
    set_save_statuses((current) => {
      const { [page_pending_delete.id]: _deleted_status, ...remaining } = current;
      return remaining;
    });
    if (next_page && next_section) {
      set_selected_page_id(next_page.id);
      set_selected_section_id(next_section.id);
      set_selected_notebook_id(next_section.notebook_id);
    }
    set_page_pending_delete(null);
    set_delete_restore_error(null);
  };

  const restore_deleted_page = (deleted_page: DeletedPage) => {
    if (new Date(deleted_page.restore_until).getTime() <= Date.now()) return;
    if (fail_next_delete_restore) {
      set_fail_next_delete_restore(false);
      set_delete_restore_error('復元に失敗しました。削除済みPageはそのまま残っています。もう一度実行できます。');
      return;
    }

    const section = sections_state.find((item) => item.id === deleted_page.page.section_id);
    if (!section) return;
    set_pages((current) => restore_page(current, deleted_page));
    set_deleted_pages((current) => current.filter((item) => item.page.id !== deleted_page.page.id));
    set_save_statuses((current) => ({ ...current, [deleted_page.page.id]: 'saved' }));
    set_selected_page_id(deleted_page.page.id);
    set_selected_section_id(section.id);
    set_selected_notebook_id(section.notebook_id);
    set_delete_restore_error(null);
  };

  const select_search_result = (page: Page) => {
    const section = sections_state.find((item) => item.id === page.section_id);
    if (!section) return;
    set_selected_notebook_id(section.notebook_id);
    set_selected_section_id(section.id);
    set_selected_page_id(page.id);
    set_search_query('');
    set_selected_tag(null);
  };

  return (
    <main className="app-shell">
      <header className="app-header">
        <button
          type="button"
          className="mobile-menu-button"
          aria-label="階層ナビゲーションを開く"
          onClick={() => set_is_drawer_open(true)}
        >
          ☰
        </button>
        <a className="app-title" href="/">CloudNote</a>
        <div className="search-area">
        <label className="search-field">
          <span>検索</span>
          <input type="search" value={search_query} onChange={(event) => set_search_query(event.target.value)} placeholder="Pageを検索" />
        </label>
        <select className="tag-filter" aria-label="タグで絞り込む" value={selected_tag ?? ''} onChange={(event) => set_selected_tag(event.target.value || null)}>
          <option value="">すべてのタグ</option>
          {available_tags.map((tag) => <option key={tag} value={tag}>{tag}</option>)}
        </select>
        {(search_query || selected_tag) && <div className="search-results" role="listbox" aria-label="検索結果">
          {search_results.length > 0 ? search_results.map((page) => {
            const section = sections_state.find((item) => item.id === page.section_id);
            const notebook = notebooks.find((item) => item.id === section?.notebook_id);
            return <button key={page.id} type="button" role="option" onClick={() => select_search_result(page)}><strong>{page.title}</strong><small>{notebook?.title} / {section?.title}</small></button>;
          }) : <p>該当するPageはありません</p>}
        </div>}
        </div>
        <p className={`save-status save-status-${save_status}`} aria-live="polite">
          <span aria-hidden="true">●</span> {save_status_label(save_status)}
        </p>
        {save_status === 'failed' && <button type="button" className="retry-button" onClick={() => schedule_save(selected_page.id, false)}>再試行</button>}
        <button type="button" className={fail_next_save ? 'failure-button is-armed' : 'failure-button'} onClick={() => set_fail_next_save((current) => !current)}>
          次の保存を失敗させる
        </button>
        <button type="button" className={fail_next_delete_restore ? 'failure-button is-armed' : 'failure-button'} onClick={() => set_fail_next_delete_restore((current) => !current)}>
          次の削除・復元を失敗させる
        </button>
      </header>

      <div className="workspace">
        <aside className="notebook-pane" aria-label="Notebook一覧">
          <div className="pane-heading"><h2>Notebook</h2><button type="button" onClick={create_notebook} aria-label="Notebookを作成">＋</button></div>
          <nav>
            {notebooks.map((notebook) => (
              <button
                key={notebook.id}
                type="button"
                className={notebook.id === selected_notebook_id ? 'nav-item selected' : 'nav-item'}
                onClick={() => select_notebook(notebook.id)}
              >
                {notebook.title}
              </button>
            ))}
          </nav>
        </aside>

        <aside className="outline-pane" aria-label="SectionとPage一覧">
          <div className="pane-heading"><h2>内容</h2><span><button type="button" onClick={create_section}>＋ Section</button><button type="button" onClick={create_page}>＋ Page</button></span></div>
          {sections.map((section) => (
            <section key={section.id} className="section-group">
              <button
                type="button"
                className={section.id === selected_section_id ? 'section-title selected' : 'section-title'}
                onClick={() => select_section(section.id)}
              >
                {section.title}
              </button>
              {pages.filter((page) => page.section_id === section.id).map((page) => (
                <button
                  key={page.id}
                  type="button"
                  className={page.id === selected_page_id ? 'page-item selected' : 'page-item'}
                  onClick={() => set_selected_page_id(page.id)}
                >
                  {page.title}
                </button>
              ))}
            </section>
          ))}
          {section_pages.length === 0 && <p className="empty-message">Pageがありません</p>}
          <details className="deleted-pages">
            <summary>削除済みPage（{deleted_pages.length}）</summary>
            {deleted_pages.length === 0 ? <p>削除済みのPageはありません。</p> : deleted_pages.map((deleted_page) => {
              const is_available = new Date(deleted_page.restore_until).getTime() > Date.now();
              return <div key={deleted_page.page.id}>
                <strong>{deleted_page.page.title}</strong>
                <small>復元期限: {format_date_time(deleted_page.restore_until)}</small>
                <button type="button" disabled={!is_available} onClick={() => restore_deleted_page(deleted_page)}>
                  {is_available ? '復元する' : '復元期限切れ'}
                </button>
              </div>;
            })}
          </details>
        </aside>

        <article className="editor-pane">
          <div className="breadcrumb">{notebooks.find((item) => item.id === selected_notebook_id)?.title} / {sections_state.find((item) => item.id === selected_section_id)?.title}</div>
          <input
            className="page-title"
            value={selected_page.title}
            aria-label="Pageタイトル"
            onChange={(event) => update_page({ title: event.target.value })}
          />
          <div className="tags" aria-label="タグ">
            {selected_page.tags.map((tag) => <span key={tag}>{tag}</span>)}
            <button type="button" onClick={add_tag}>＋ タグ</button>
          </div>
          <div className="move-controls">
            <div className="order-controls" aria-label="Pageの並べ替え">
              <button type="button" onClick={() => reorder_selected_page('up')} disabled={!can_move_page(save_status)}>↑ 上へ</button>
              <button type="button" onClick={() => reorder_selected_page('down')} disabled={!can_move_page(save_status)}>↓ 下へ</button>
            </div>
            <label>移動先Section
              <select value={move_target_section_id} onChange={(event) => set_move_target_section_id(event.target.value)} disabled={!can_move_page(save_status)}>
                {sections_state.map((section) => <option key={section.id} value={section.id}>{notebooks.find((notebook) => notebook.id === section.notebook_id)?.title} / {section.title}</option>)}
              </select>
            </label>
            <button type="button" onClick={move_selected_page} disabled={!can_move_page(save_status) || move_target_section_id === selected_page.section_id}>移動する</button>
            <button type="button" className="delete-page-button" onClick={() => { set_page_pending_delete(selected_page); set_delete_restore_error(null); }} disabled={!can_move_page(save_status)}>削除する</button>
            {!can_move_page(save_status) && <p>保存が完了するまで移動できません。</p>}
          </div>
          {delete_restore_error && <p className="operation-error" role="status">{delete_restore_error}</p>}
          <RichTextEditor content={selected_page.content} on_change={(content) => update_page({ content })} />
        </article>
      </div>

      {is_drawer_open && (
        <div className="drawer-layer" role="presentation" onClick={() => set_is_drawer_open(false)}>
          <aside className="mobile-drawer" aria-label="階層ナビゲーション" onClick={(event) => event.stopPropagation()}>
            <div className="drawer-heading"><h2>CloudNote</h2><button type="button" onClick={() => set_is_drawer_open(false)} aria-label="閉じる">×</button></div>
            {notebooks.map((notebook) => (
              <div key={notebook.id} className="drawer-notebook">
                <button type="button" onClick={() => select_notebook(notebook.id)}>{notebook.title}</button>
                {notebook.id === selected_notebook_id && sections_state.filter((section) => section.notebook_id === notebook.id).map((section) => (
                  <button key={section.id} type="button" className="drawer-section" onClick={() => select_section(section.id)}>{section.title}</button>
                ))}
              </div>
            ))}
          </aside>
        </div>
      )}

      {page_pending_delete && (
        <div className="dialog-layer" role="presentation">
          <section className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-dialog-title">
            <h2 id="delete-dialog-title">Pageを削除しますか？</h2>
            <p><strong>{page_pending_delete.title}</strong></p>
            <p>対象: Page 1件。削除後10日間は復元できます。</p>
            {delete_restore_error && <p className="operation-error" role="status">{delete_restore_error}</p>}
            <div>
              <button type="button" onClick={() => { set_page_pending_delete(null); set_delete_restore_error(null); }}>キャンセル</button>
              <button type="button" className="delete-page-button" onClick={confirm_delete_page}>削除する</button>
            </div>
          </section>
        </div>
      )}
    </main>
  );
}
