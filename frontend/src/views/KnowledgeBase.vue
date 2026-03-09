<template>
  <div>
    <el-card>
      <template #header> 知识库图片上传 </template>
      <el-upload
        drag
        multiple
        :auto-upload="false"
        :file-list="fileList"
        :on-change="handleChange"
      >
        <i class="el-icon-upload"></i>
        <div class="el-upload__text">
          将图片拖到此处，或 <em>点击上传</em>
        </div>
      </el-upload>
      <el-button
        type="primary"
        :loading="uploading"
        style="margin-top: 16px"
        @click="doUpload"
      >
        开始上传并生成描述
      </el-button>
    </el-card>

    <el-card style="margin-top: 24px">
      <template #header> 已上传图片 </template>
      <el-table v-loading="loading" :data="images" height="400">
        <el-table-column prop="id" label="ID" width="260" />
        <el-table-column prop="file_path" label="路径" />
        <el-table-column prop="status" label="状态" width="120" />
        <el-table-column label="描述" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.generated_description }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import type { UploadFile, UploadFiles } from "element-plus";
import { ElMessage } from "element-plus";

import { listImages, uploadImages, type ImageRecord } from "@/api/kb";

const fileList = ref<UploadFiles>([]);
const images = ref<ImageRecord[]>([]);
const uploading = ref(false);
const loading = ref(false);

// 页面加载时获取已上传的图片
async function loadImages() {
  try {
    loading.value = true;
    const data = await listImages();
    images.value = data;
  } catch (e) {
    console.error('加载图片列表失败:', e);
    ElMessage.error("加载图片列表失败");
  } finally {
    loading.value = false;
  }
}

// 页面加载时调用
onMounted(() => {
  loadImages();
});

function handleChange(file: UploadFile, files: UploadFiles) {
  fileList.value = files;
}

async function doUpload() {
  if (!fileList.value.length) {
    ElMessage.warning("请先选择要上传的图片");
    return;
  }
  try {
    uploading.value = true;
    const files = fileList.value
      .map((f) => f.raw)
      .filter((f): f is File => !!f);
    const resp = await uploadImages(files);
    // 上传成功后重新加载列表
    await loadImages();
    ElMessage.success("上传并生成描述完成");
    // 清空文件列表
    fileList.value = [];
  } catch (e) {
    console.error('上传失败:', e);
    ElMessage.error("上传失败，请检查后端服务是否已启动");
  } finally {
    uploading.value = false;
  }
}
</script>

