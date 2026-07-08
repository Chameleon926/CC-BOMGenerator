import api from './index'

// 条款 / 要素库 API（完整 CRUD）
export const clausesApi = {
  /** 获取条款列表（查 clauses 表，含用例数/版本/来源，刷新不丢） */
  list: () => api.get('/clauses'),

  /** 上传测试集 → 扫描条款（存 latest.xlsx + upsert clauses 表含用例数） */
  scan: (file) => {
    const form = new FormData()
    form.append('file', file)
    return api.post('/testset/scan', form)
  },

  /** 手动新增条款 */
  create: ({ block_code, block_name, domain = '' }) =>
    api.post('/clauses', { block_code, block_name, domain }),

  /** 改条款信息 */
  update: (block_code, { block_name, domain }) =>
    api.put(`/clauses/${block_code}`, { block_name, domain }),

  /** 删条款 + 级联清理关联数据 */
  remove: (block_code) => api.delete(`/clauses/${block_code}`),
}
