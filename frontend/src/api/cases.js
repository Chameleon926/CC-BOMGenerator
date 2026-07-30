import api from './index'

// 用例库 API（条款视角）
export const casesApi = {
  /** 条款列表（含用例统计 + 模糊搜索） */
  list: (search = '') => api.get('/cases', { params: search ? { search } : {} }),

  /** 某条款的用例行（正例/负例筛选） */
  rows: (block_code, { filter = 'all', limit = 500, offset = 0 } = {}) =>
    api.get(`/cases/${block_code}/rows`, { params: { filter, limit, offset }, skipToast: true }),
}
