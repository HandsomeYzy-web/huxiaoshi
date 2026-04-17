import axios from 'axios'
import type { AxiosInstance, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'

export interface ApiResponse<T = unknown> {
  code: number
  message: string
  data: T
}

const service: AxiosInstance = axios.create({
  baseURL: '/api/v1',
  timeout: 50000,
})

service.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem('qa_access_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error: unknown) => Promise.reject(error),
)

service.interceptors.response.use(
  <T>(response: AxiosResponse<ApiResponse<T>>) => {
    const payload = response.data
    if (payload.code !== 200) {
      ElMessage.error(payload.message || '请求失败')
      return Promise.reject(new Error(payload.message || 'Request failed'))
    }
    return payload.data
  },
  (error: any) => {
    if (error?.response?.status === 401) {
      localStorage.removeItem('qa_access_token')
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
      return Promise.reject(error)
    }

    const message =
      error?.response?.data?.message ||
      error?.message ||
      '网络异常，请检查后端服务是否已启动'
    ElMessage.error(message)
    return Promise.reject(error)
  },
)

export default service
