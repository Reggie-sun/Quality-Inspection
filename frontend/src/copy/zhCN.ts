export const zhCN = {
  brand: "智检通",
  product: "工程图纸智能检验",
  intro: "上传工程PDF，自动识别检验项并生成气泡图与SIP文件。",
  stages: [
    "上传图纸",
    "智能识别",
    "人工审核",
    "气泡调整",
    "文件导出",
  ],
  upload: {
    heading: "上传工程 PDF",
    select: "选择工程 PDF",
    submit: "上传并开始识别",
    replace: "重新选择文件",
    retry: "重新处理",
    retryStatus: "重新获取状态",
    another: "处理另一份 PDF",
    empty: "将工程 PDF 拖放到此处，或从本机选择文件",
    selected: "已选择文件",
    supportTitle: "支持范围",
    support: "支持包含矢量文字或可定位混合内容的工程 PDF；纯扫描 PDF 可能暂不支持。",
    safetyTitle: "文件安全",
    safety: "文件仅用于当前检验流程，不在页面展示内部标识或技术路径。",
  },
  status: {
    uploading: "正在上传工程 PDF",
    queued: "等待处理",
    processing: "正在解析图纸并识别检验项",
    preparing: "正在准备审核",
    ready: "识别完成，已进入审核",
    hint: "处理完成后将自动进入审核工作台，请保持页面打开。",
  },
} as const;


const ERROR_COPY: Readonly<Record<string, string>> = {
  invalid_pdf: "PDF 格式错误，请选择有效的工程 PDF",
  unsupported_input: "当前 PDF 暂不支持",
  network_error: "网络错误，请检查连接后重试",
  project_status_failed: "状态获取失败，请重试",
  project_dispatch_failed: "处理服务暂时不可用，请重新处理",
  project_intake_failed: "上传失败，请重新处理",
  project_processing_failed: "图纸处理失败，请重新处理",
  inventory_processing_failed: "图纸解析失败，请重新处理",
  review_bootstrap_failed: "审核工作台准备失败，请重新处理",
};


export function projectErrorCopy(code: string): string {
  return ERROR_COPY[code] ?? "处理失败，请重新处理";
}
