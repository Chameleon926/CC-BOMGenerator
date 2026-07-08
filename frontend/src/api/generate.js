import api from './index'

// 语义 BOM 生成 API
export const generateApi = {
  /** 启动生成（file 可选，不传则用后端 latest.xlsx） */
  start: ({ block_code, clause = '', file = null, nkw = 10, nsec = 6, nq = 3, skip_verify = false }) => {
    const form = new FormData()
    if (file) form.append('file', file)
    form.append('block_code', block_code)
    if (clause) form.append('clause', clause)
    form.append('nkw', nkw)
    form.append('nsec', nsec)
    form.append('nq', nq)
    form.append('skip_verify', skip_verify)
    return api.post('/generate', form)
  },

  /** 查询执行进度 */
  status: (run_id) => api.get(`/runs/${run_id}/status`),

  /** 获取生成结果（BOM + 提示词） */
  result: (run_id) => api.get(`/runs/${run_id}/result`),
}
