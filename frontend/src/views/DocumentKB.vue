<template>
  <div class="doc-kb">
    <!-- 上传区域 -->
    <el-card>
      <template #header>PDF 文档上传</template>
      <el-upload
        drag
        accept=".pdf"
        :auto-upload="false"
        :show-file-list="true"
        :on-change="handleFileChange"
        :limit="1"
      >
        <el-icon style="font-size: 48px; color: #409eff"><Upload /></el-icon>
        <div class="el-upload__text">
          将 PDF 拖到此处，或 <em>点击上传</em>
        </div>
        <template #tip>
          <div class="el-upload__tip">仅支持 .pdf 文件，解析过程中请耐心等待</div>
        </template>
      </el-upload>
      <el-button
        type="primary"
        :loading="uploading"
        style="margin-top: 16px"
        :disabled="!selectedFile"
        @click="doUpload"
      >
        开始上传并解析
      </el-button>
      <el-alert
        v-if="uploadMsg"
        :title="uploadMsg"
        :type="uploadSuccess ? 'success' : 'error'"
        show-icon
        style="margin-top: 12px"
        :closable="false"
      />
    </el-card>

    <!-- 文档列表 -->
    <el-card style="margin-top: 24px">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>已上传文档</span>
          <el-button size="small" @click="loadDocList">刷新</el-button>
        </div>
      </template>
      <el-table v-loading="loadingList" :data="docList" stripe>
        <el-table-column prop="file_name" label="文件名" min-width="160" />
        <el-table-column prop="upload_time" label="上传时间" width="180">
          <template #default="{ row }">
            {{ new Date(row.upload_time).toLocaleString() }}
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="chunk_count" label="文本片段" width="90" align="center" />
        <el-table-column prop="image_count" label="图片数" width="80" align="center" />
        <el-table-column label="操作" width="100" align="center">
          <template #default="{ row }">
            <el-button
              size="small"
              type="primary"
              :disabled="row.status !== 'Completed'"
              @click="viewResult(row)"
            >查看</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 解析结果抽屉 -->
    <el-drawer
      v-model="drawerVisible"
      :title="activeDoc?.file_name || '解析结果'"
      size="60%"
      direction="rtl"
    >
      <div v-if="loadingResult" style="text-align:center;padding:40px">
        <el-icon class="is-loading" style="font-size:32px"><Loading /></el-icon>
        <p>加载中...</p>
      </div>
      <template v-else-if="parseResult">
        <!-- 统计信息 -->
        <el-descriptions :column="3" border style="margin-bottom: 20px">
          <el-descriptions-item label="文本片段数">{{ parseResult.chunks.length }}</el-descriptions-item>
          <el-descriptions-item label="图片数">{{ parseResult.images.length }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="statusType(parseResult.document.status)">{{ parseResult.document.status }}</el-tag>
          </el-descriptions-item>
        </el-descriptions>

        <!-- 文本片段 -->
        <el-divider content-position="left">文本片段（{{ parseResult.chunks.length }} 条）</el-divider>
        <div class="chunks-container">
          <el-card
            v-for="chunk in parseResult.chunks"
            :key="chunk.chunk_index"
            class="chunk-card"
            shadow="never"
          >
            <template #header>
              <span style="font-size:12px;color:#888">片段 #{{ chunk.chunk_index + 1 }}</span>
            </template>
            <p class="chunk-content">{{ chunk.content }}</p>
          </el-card>
          <el-empty v-if="parseResult.chunks.length === 0" description="无文本片段" />
        </div>

        <!-- 提取的图片 -->
        <el-divider content-position="left">提取的图片（{{ parseResult.images.length }} 张）</el-divider>
        <div class="images-grid">
          <el-card
            v-for="img in parseResult.images"
            :key="img.id"
            class="img-card"
            shadow="never"
          >
            <img
              :src="imgSrc(img.file_path)"
              class="img-thumb"
              @error="onImgError"
            />
            <p class="img-desc">{{ img.generated_description || '（无描述）' }}</p>
          </el-card>
          <el-empty v-if="parseResult.images.length === 0" description="无提取图片" />
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { Upload, Loading } from "@element-plus/icons-vue";
import type { UploadFile } from "element-plus";
import {
  uploadDocument,
  listDocuments,
  getDocResult,
  type DocumentRecord,
  type DocParseResult,
} from "@/api/docs";

// 上传
const selectedFile = ref<File | null>(null);
const uploading = ref(false);
const uploadMsg = ref("");
const uploadSuccess = ref(false);

function handleFileChange(uploadFile: UploadFile) {
  selectedFile.value = uploadFile.raw ?? null;
  uploadMsg.value = "";
}

async function doUpload() {
  if (!selectedFile.value) return;
  uploading.value = true;
  uploadMsg.value = "";
  try {
    const res = await uploadDocument(selectedFile.value);
    uploadSuccess.value = true;
    uploadMsg.value = res.message || "上传成功";
    selectedFile.value = null;
    await loadDocList();
  } catch (e: any) {
    uploadSuccess.value = false;
    uploadMsg.value = e?.response?.data?.detail || "上传失败";
  } finally {
    uploading.value = false;
  }
}

// 文档列表
const docList = ref<DocumentRecord[]>([]);
const loadingList = ref(false);

async function loadDocList() {
  loadingList.value = true;
  try {
    docList.value = await listDocuments();
  } catch {
    ElMessage.error("加载文档列表失败");
  } finally {
    loadingList.value = false;
  }
}

onMounted(loadDocList);

function statusType(status: string) {
  if (status === "Completed") return "success";
  if (status === "Failed") return "danger";
  return "warning";
}

// 查看解析结果
const drawerVisible = ref(false);
const activeDoc = ref<DocumentRecord | null>(null);
const parseResult = ref<DocParseResult | null>(null);
const loadingResult = ref(false);

async function viewResult(doc: DocumentRecord) {
  activeDoc.value = doc;
  drawerVisible.value = true;
  loadingResult.value = true;
  parseResult.value = null;
  try {
    parseResult.value = await getDocResult(doc.id);
  } catch {
    ElMessage.error("加载解析结果失败");
  } finally {
    loadingResult.value = false;
  }
}

// 图片 src：后端直接提供静态文件
function imgSrc(filePath: string): string {
  // 将反斜杠统一为正斜杠，取 storage/ 之后的部分
  const normalized = filePath.replace(/\\/g, "/");
  const idx = normalized.indexOf("storage/");
  if (idx !== -1) {
    return `http://localhost:9090/static/${normalized.slice(idx + "storage/".length)}`;
  }
  return "";
}

function onImgError(e: Event) {
  (e.target as HTMLImageElement).style.display = "none";
}
</script>

<style scoped>
.doc-kb {
  max-width: 1100px;
  margin: 0 auto;
}

.chunks-container {
  max-height: 400px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

.chunk-card {
  border: 1px solid #ebeef5;
}

.chunk-content {
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}

.images-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.img-card {
  border: 1px solid #ebeef5;
}

.img-thumb {
  width: 100%;
  height: 140px;
  object-fit: cover;
  border-radius: 4px;
  display: block;
}

.img-desc {
  font-size: 12px;
  color: #666;
  margin: 8px 0 0;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
