<template>
  <el-container style="height: 100vh">
    <el-aside width="220px">
      <el-menu router default-active="/kb">
        <el-menu-item index="/kb">知识库管理</el-menu-item>
        <el-menu-item index="/search">图像检索</el-menu-item>
        <el-menu-item index="/chat">RAG 智能问答</el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header>
        <h2>多模态 RAG 知识库系统</h2>
      </el-header>
      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts"></script>

