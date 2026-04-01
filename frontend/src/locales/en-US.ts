/**
 * English language pack
 */
export default {
  app: {
    title: 'Multimodal RAG Knowledge Base',
    connectionOk: 'Backend Connected',
    connectionError: 'Backend Disconnected'
  },
  nav: {
    knowledgeBase: 'Knowledge Base',
    search: 'Image Search',
    chat: 'RAG Chat',
    documents: 'Document KB'
  },
  theme: {
    dark: 'Dark Mode',
    light: 'Light Mode'
  },
  kb: {
    title: 'Knowledge Base Upload',
    uploadArea: 'Drag images here or click to upload',
    uploadBtn: 'Upload & Generate Descriptions',
    uploadedImages: 'Uploaded Images',
    id: 'ID',
    path: 'Path',
    status: 'Status',
    description: 'Description',
    processing: 'Processing',
    completed: 'Completed',
    failed: 'Failed',
    noImages: 'No images yet',
    uploadSuccess: 'Upload complete',
    uploadFailed: 'Upload failed, please check backend service',
    loadFailed: 'Failed to load images',
    selectFiles: 'Please select images to upload',
    gridView: 'Grid View',
    tableView: 'Table View'
  },
  search: {
    title: 'Image Retrieval',
    textToImage: 'Text → Image Search',
    imageToImage: 'Image → Image Search',
    textQueryPlaceholder: 'Enter image content to search, e.g.: a child playing ball on grass',
    imageQueryPlaceholder: 'Drag or click to upload image for search',
    searchBtn: 'Search',
    imageSearchBtn: 'Search Similar Images',
    queryDescription: 'Generated query description:',
    id: 'ID',
    path: 'Path',
    similarity: 'Similarity',
    noResults: 'No results',
    textSearchFailed: 'Text search failed, please check backend service',
    imageSearchFailed: 'Image search failed, please check backend service',
    enterQuery: 'Please enter a text query',
    selectImage: 'Please select an image first'
  },
  chat: {
    title: 'RAG Intelligent Q&A',
    queryPlaceholder: 'Enter your question, e.g.: What common elements are in these images?',
    optionalImage: 'Optional: Upload an image to guide RAG retrieval',
    sendBtn: 'Send',
    answer: 'Answer',
    referencedImages: 'Referenced Images',
    newSession: 'New Session',
    noSessions: 'No session history',
    sessionDeleted: 'Session deleted',
    sessionRenamed: 'Session renamed',
    inputPlaceholder: 'Enter question, press Enter to send...',
    chatFailed: 'RAG chat failed, please check backend service',
    enterQuestion: 'Please enter a question'
  },
  docs: {
    title: 'PDF Document Upload',
    uploadArea: 'Drag PDF here or click to upload',
    uploadBtn: 'Upload & Parse',
    uploadTip: 'Only .pdf files supported, please wait patiently during parsing',
    uploadedDocs: 'Uploaded Documents',
    fileName: 'File Name',
    uploadTime: 'Upload Time',
    status: 'Status',
    chunks: 'Text Chunks',
    images: 'Images',
    action: 'Action',
    view: 'View',
    refresh: 'Refresh',
    chunksTitle: 'Text Chunks',
    imagesTitle: 'Extracted Images',
    noChunks: 'No text chunks',
    noImages: 'No extracted images',
    uploadSuccess: 'Upload successful',
    uploadFailed: 'Upload failed',
    loadFailed: 'Failed to load documents',
    loadResultFailed: 'Failed to load parsing result'
  },
  common: {
    loading: 'Loading...',
    error: 'Error',
    success: 'Success',
    confirm: 'Confirm',
    cancel: 'Cancel',
    close: 'Close',
    delete: 'Delete',
    rename: 'Rename',
    confirmDelete: 'Confirm delete?'
  }
}
