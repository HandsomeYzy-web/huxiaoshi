import axios from 'axios'
import type { AxiosInstance, AxiosResponse } from 'axios'
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
    const message =
      error?.response?.data?.message ||
      error?.message ||
      '网络异常，请检查后端服务是否已启动'
    ElMessage.error(message)
    return Promise.reject(error)
  },
)

export default service
