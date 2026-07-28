import api from './index'

// 语义 BOM 生成 API
export const generateApi = {
  /** 启动生成（file 可选，不传则用后端 latest.xlsx） */
  start: ({ block_code, clause = '', file = null, nkw = 10, nsec = 6, nq = 3, skip_verify = false, num_examples = 5 }) => {
    const form = new FormData()
    if (file) form.append('file', file)
    form.append('block_code', block_code)
    if (clause) form.append('clause', clause)
    form.append('nkw', nkw)
    form.append('nsec', nsec)
    form.append('nq', nq)
    form.append('skip_verify', skip_verify)
    form.append('num_examples', num_examples)
    return api.post('/generate', form)
  },

  /** 任务列表（可按 block_code 筛选，含 progress%）。opts 透传 axios config（轮询传 {skipToast:true}） */
  list: (block_code = '', opts = {}) => api.get('/runs', { params: block_code ? { block_code } : {}, ...opts }),

  /** 查询执行进度（节点级）。opts 透传 axios config（轮询传 {skipToast:true}） */
  status: (run_id, opts = {}) => api.get(`/runs/${run_id}/status`, opts),

  /** 获取生成结果（BOM + 提示词 + 选取正例；失败/取消也返已产出部分） */
  result: (run_id) => api.get(`/runs/${run_id}/result`),

  /** 停止任务（标 cancelled，当前节点跑完后生效） */
  stop: (run_id) => api.post(`/runs/${run_id}/stop`),
}
