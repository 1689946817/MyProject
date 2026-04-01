/**
 * 简体中文语言包
 */
export default {
  app: {
    title: '多模态 RAG 知识库系统',
    connectionOk: '后端连接正常',
    connectionError: '后端连接失败'
  },
  nav: {
    knowledgeBase: '知识库管理',
    search: '图像检索',
    chat: 'RAG 智能问答',
    documents: '文档知识库'
  },
  theme: {
    dark: '深色模式',
    light: '浅色模式'
  },
  kb: {
    title: '知识库图片上传',
    uploadArea: '将图片拖到此处，或点击上传',
    uploadBtn: '开始上传并生成描述',
    uploadedImages: '已上传图片',
    id: 'ID',
    path: '路径',
    status: '状态',
    description: '描述',
    processing: '处理中',
    completed: '已完成',
    failed: '失败',
    noImages: '暂无图片',
    uploadSuccess: '上传并生成描述完成',
    uploadFailed: '上传失败，请检查后端服务是否已启动',
    loadFailed: '加载图片列表失败',
    selectFiles: '请先选择要上传的图片',
    gridView: '网格视图',
    tableView: '表格视图'
  },
  search: {
    title: '图像检索',
    textToImage: '文本 → 图像检索',
    imageToImage: '图像 → 图像检索',
    textQueryPlaceholder: '输入要检索的图像内容，如：一个在草地上玩球的小孩',
    imageQueryPlaceholder: '拖拽或点击上传待检索的图片',
    searchBtn: '检索',
    imageSearchBtn: '检索相似图片',
    queryDescription: '生成的查询描述：',
    id: 'ID',
    path: '路径',
    similarity: '相似度',
    noResults: '暂无结果',
    textSearchFailed: '文本检索失败，请检查后端服务是否已启动',
    imageSearchFailed: '以图搜图失败，请检查后端服务是否已启动',
    enterQuery: '请输入文本查询内容',
    selectImage: '请先选择一张图片作为查询'
  },
  chat: {
    title: 'RAG 智能问答',
    queryPlaceholder: '请输入你的问题，如：这几张图片中有哪些共同的元素？',
    optionalImage: '可选：上传一张图片，引导 RAG 结合图片检索回答',
    sendBtn: '发送',
    answer: '回答',
    referencedImages: '被引用的相关图像',
    newSession: '新建会话',
    noSessions: '暂无会话记录',
    sessionDeleted: '会话已删除',
    sessionRenamed: '会话已重命名',
    inputPlaceholder: '输入问题，按 Enter 发送...',
    chatFailed: 'RAG 问答失败，请检查后端服务是否已启动',
    enterQuestion: '请输入问题内容'
  },
  docs: {
    title: 'PDF 文档上传',
    uploadArea: '将 PDF 拖到此处，或点击上传',
    uploadBtn: '开始上传并解析',
    uploadTip: '仅支持 .pdf 文件，解析过程中请耐心等待',
    uploadedDocs: '已上传文档',
    fileName: '文件名',
    uploadTime: '上传时间',
    status: '状态',
    chunks: '文本片段',
    images: '图片数',
    action: '操作',
    view: '查看',
    refresh: '刷新',
    chunksTitle: '文本片段',
    imagesTitle: '提取的图片',
    noChunks: '无文本片段',
    noImages: '无提取图片',
    uploadSuccess: '上传成功',
    uploadFailed: '上传失败',
    loadFailed: '加载文档列表失败',
    loadResultFailed: '加载解析结果失败'
  },
  common: {
    loading: '加载中...',
    error: '错误',
    success: '成功',
    confirm: '确认',
    cancel: '取消',
    close: '关闭',
    delete: '删除',
    rename: '重命名',
    confirmDelete: '确认删除？'
  }
}
