import axios from 'axios'
import { ElMessage } from 'element-plus'

// axios 实例（统一 baseURL + 超时 + 错误拦截）
const api = axios.create({
  baseURL: '/api',
  timeout: 60000, // LLM 调用可能慢
})

// 响应拦截：统一提取 data + 错误提示
api.interceptors.response.use(
  (response) => response.data, // 直接返回 data（不用每次 res.data）
  (error) => {
    const msg = error.response?.data?.detail || error.message || '请求失败'
    // 403（LLM 认证）等业务错误，弹消息
    if (error.response?.status !== 404) {
      ElMessage.error(typeof msg === 'string' ? msg : JSON.stringify(msg))
    }
    return Promise.reject(error)
  }
)

export default api
