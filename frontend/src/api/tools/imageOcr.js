/**
 * 服务端图片 OCR（multipart 上传）
 * 默认腾讯云 GeneralAccurateOCR；返回文本按 ItemPolygon 坐标近似还原横向排版（见 apis/ocr/views.py）。
 */
import { requestWithToken } from '../../common/request.js'

/**
 * @param {File|Blob} file
 * @param {string} [lang] chi_sim+eng | chi_sim | eng
 * @returns {Promise<string>}
 */
export async function ocrImageByServer(file, lang = 'chi_sim+eng') {
  const fd = new FormData()
  const upload =
    file instanceof File
      ? file
      : new File([file], 'image.png', { type: file.type || 'image/png' })
  fd.append('image', upload)

  const res = await requestWithToken(
    `/api/ocr/image/?lang=${encodeURIComponent(lang)}`,
    {
      method: 'POST',
      body: fd,
    }
  )
  const j = await res.json().catch(() => ({}))
  if (!res.ok) {
    throw new Error(j.message || `HTTP ${res.status}`)
  }
  if (j.code !== 0) {
    throw new Error(j.message || '识别失败')
  }
  return (j.data && j.data.text) || ''
}
