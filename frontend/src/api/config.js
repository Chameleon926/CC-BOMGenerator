import api from './index'

// 模型配置 API
export const configApi = {
  /** 获取当前模型配置（api_key 脱敏） */
  get: () => api.get('/config'),

  /** 更新模型配置（api_key 留空=不改） */
  update: (data) => api.post('/config', data),
}
