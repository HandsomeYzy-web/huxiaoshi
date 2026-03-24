// src/api/request.ts
import axios from 'axios'
import type { AxiosInstance, AxiosResponse, InternalAxiosRequestConfig } from 'axios'

// 1. 创建 Axios 实例
const request: AxiosInstance = axios.create({
  // 指向你的 FastAPI 后端地址
  baseURL: 'http://127.0.0.1:8000',
  // 知识库向量化比较耗时，超时时间设置长一点（60秒）
  timeout: 60000,
})

// 2. 请求拦截器 (Request Interceptor)
request.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    // 这里未来可以统一加上 Token，比如：
    // const token = localStorage.getItem('token')
    // if (token) { config.headers['Authorization'] = `Bearer ${token}` }
    return config
  },
  (error: any) => {
    console.error('请求发送失败:', error)
    return Promise.reject(error)
  }
)

// 3. 响应拦截器 (Response Interceptor)
request.interceptors.response.use(
  (response: AxiosResponse) => {
    // 这里的 response.data 就是后端返回的完整 JSON: { code: 200, msg: "success", data: {...} }
    const res = response.data

    // 假设后端返回的是文件流（如下载文件），直接放行
    if (response.config.responseType === 'blob' || response.config.responseType === 'arraybuffer') {
      return res
    }

    // 核心逻辑：判断后端的自定义状态码
    if (res.code === 200) {
      // 成功！直接把内层的 data 剥离出来返回给页面
      return res.data
    } else {
      // 业务报错（如：模型不支持、校验失败等）
      console.error(`业务报错 [${res.code}]: ${res.msg}`)
      return Promise.reject(new Error(res.msg || '系统业务异常'))
    }
  },
  (error: any) => {
    // 网络或服务器崩溃级别的报错 (如 404, 500)
    let errorMsg = '网络错误，请稍后再试'

    if (error.response) {
      const status = error.response.status
      const data = error.response.data

      if (status === 422) {
        errorMsg = data.msg || '参数校验失败'
      } else if (status === 500) {
        errorMsg = '后端服务器内部错误'
      } else {
        errorMsg = data.msg || `请求失败 (${status})`
      }
    } else if (error.message.includes('timeout')) {
      errorMsg = '请求超时，可能是文件太大或向量化时间过长'
    }

    console.error('HTTP 请求失败:', errorMsg)
    return Promise.reject(new Error(errorMsg))
  }
)

export default request