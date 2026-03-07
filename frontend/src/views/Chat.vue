<template>
  <div class="chat-page">
    <el-row :gutter="20">
      <el-col :span="8">
        <el-card>
          <template #header> 提问与可选图片 </template>
          <el-input
            v-model="query"
            type="textarea"
            :rows="5"
            placeholder="请输入你的问题，如：这几张图片中有哪些共同的元素？"
          />
          <el-upload
            drag
            :auto-upload="false"
            :file-list="imageFileList"
            :on-change="onImageChange"
            style="margin-top: 12px"
          >
            <i class="el-icon-upload"></i>
            <div class="el-upload__text">
              可选：上传一张图片，引导 RAG 结合图片检索回答
            </div>
          </el-upload>
          <el-button
            type="primary"
            style="margin-top: 12px"
            :loading="loading"
            @click="doChat"
          >
            发送
          </el-button>
        </el-card>
      </el-col>

      <el-col :span="16">
        <el-card>
          <template #header> 回答与引用图像 </template>
          <div v-if="answer" class="answer-block">
            <h4>回答：</h4>
            <p>{{ answer }}</p>
          </div>
          <div v-if="results.length" class="results-block">
            <h4>被引用的相关图像：</h4>
            <el-table :data="results" height="320">
              <el-table-column prop="id" label="ID" width="220" />
              <el-table-column prop="file_path" label="路径" />
              <el-table-column prop="score" label="相似度" width="120" />
            </el-table>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import type { UploadFile, UploadFiles } from "element-plus";
import { ElMessage } from "element-plus";

import { ragChat, type ChatResponse } from "@/api/chat";

const query = ref("");
const imageFileList = ref<UploadFiles>([]);
const loading = ref(false);

const answer = ref("");
const results = ref<ChatResponse["results"]>([]);

function onImageChange(file: UploadFile, files: UploadFiles) {
  imageFileList.value = files.slice(-1);
}

async function doChat() {
  if (!query.value.trim()) {
    ElMessage.warning("请输入问题内容");
    return;
  }
  try {
    loading.value = true;
    const file = imageFileList.value[0]?.raw;
    const resp = await ragChat(query.value, 5, file);
    answer.value = resp.answer;
    results.value = resp.results;
  } catch (e) {
    ElMessage.error("RAG 问答失败，请检查后端服务是否已启动");
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.chat-page {
  padding: 0 8px;
}
.answer-block {
  margin-bottom: 16px;
}
</style>

