import api from './index'

// 用例库 API
export const casesApi = {
  /** 列测试集 */
  list: () => api.get('/cases'),

  /** 测试集详情（元数据） */
  get: (id) => api.get(`/cases/${id}`),

  /** 用例行（分页 + 筛选） */
  rows: (id, { block_code = '', filter = 'all', limit = 500, offset = 0 } = {}) =>
    api.get(`/cases/${id}/rows`, { params: { block_code, filter, limit, offset }, skipToast: true }),

  /** 删测试集 + 级联删 cases */
  remove: (id) => api.delete(`/cases/${id}`),
}
