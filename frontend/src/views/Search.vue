<template>
  <div class="search-page">
    <el-row :gutter="20">
      <el-col :span="12">
        <el-card>
          <template #header> 文本 → 图像检索 </template>
          <el-input
            v-model="textQuery"
            placeholder="输入要检索的图像内容，如：一个在草地上玩球的小孩"
          />
          <el-button
            type="primary"
            style="margin-top: 12px"
            :loading="loadingText"
            @click="doTextSearch"
          >
            检索
          </el-button>
          <el-divider />
          <el-table :data="textResults" height="320">
            <el-table-column prop="id" label="ID" width="220" />
            <el-table-column prop="file_path" label="路径" />
            <el-table-column prop="score" label="相似度" width="120" />
          </el-table>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card>
          <template #header> 图像 → 图像检索 </template>
          <el-upload
            drag
            :auto-upload="false"
            :file-list="imageFileList"
            :on-change="onImageChange"
          >
            <i class="el-icon-upload"></i>
            <div class="el-upload__text">
              拖拽或点击上传待检索的图片
            </div>
          </el-upload>
          <el-button
            type="primary"
            style="margin-top: 12px"
            :loading="loadingImage"
            @click="doImageSearch"
          >
            检索相似图片
          </el-button>
          <p v-if="imageQueryDescription" style="margin-top: 12px">
            生成的查询描述：{{ imageQueryDescription }}
          </p>
          <el-divider />
          <el-table :data="imageResults" height="260">
            <el-table-column prop="id" label="ID" width="220" />
            <el-table-column prop="file_path" label="路径" />
            <el-table-column prop="score" label="相似度" width="120" />
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import type { UploadFile, UploadFiles } from "element-plus";
import { ElMessage } from "element-plus";

import {
  textToImageSearch,
  imageToImageSearch,
  type SearchResultItem
} from "@/api/search";

const textQuery = ref("");
const textResults = ref<SearchResultItem[]>([]);
const loadingText = ref(false);

const imageFileList = ref<UploadFiles>([]);
const imageResults = ref<SearchResultItem[]>([]);
const imageQueryDescription = ref("");
const loadingImage = ref(false);

function onImageChange(file: UploadFile, files: UploadFiles) {
  imageFileList.value = files.slice(-1);
}

async function doTextSearch() {
  if (!textQuery.value.trim()) {
    ElMessage.warning("请输入文本查询内容");
    return;
  }
  try {
    loadingText.value = true;
    const resp = await textToImageSearch(textQuery.value, 10);
    textResults.value = resp.results;
  } catch (e) {
    ElMessage.error("文本检索失败，请检查后端服务是否已启动");
  } finally {
    loadingText.value = false;
  }
}

async function doImageSearch() {
  const file = imageFileList.value[0]?.raw;
  if (!file) {
    ElMessage.warning("请先选择一张图片作为查询");
    return;
  }
  try {
    loadingImage.value = true;
    const resp = await imageToImageSearch(file, 10);
    imageQueryDescription.value = resp.query_description;
    imageResults.value = resp.results;
  } catch (e) {
    ElMessage.error("以图搜图失败，请检查后端服务是否已启动");
  } finally {
    loadingImage.value = false;
  }
}
</script>

<style scoped>
.search-page {
  padding: 0 8px;
}
</style>

