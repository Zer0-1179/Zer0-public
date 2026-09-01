export type SaveStatus = 'failed' | 'saved' | 'saving' | 'unsaved';

export function save_status_label(status: SaveStatus): string {
  const labels: Record<SaveStatus, string> = {
    failed: '保存失敗・再試行',
    saved: '保存済み',
    saving: '保存中',
    unsaved: '未保存',
  };

  return labels[status];
}
