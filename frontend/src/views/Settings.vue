<template>
  <div class="settings-page page-shell">
    <div class="page-intro">
      <div class="page-intro-main">
        <h1 class="page-title">{{ t("settings.title") }}</h1>
        <p class="page-subtitle">{{ t("settings.subtitle") }}</p>
      </div>
      <div class="page-intro-actions">
        <el-button :disabled="!isDirty || saving" @click="resetChanges">
          {{ t("settings.reset") }}
        </el-button>
        <el-button type="primary" :loading="saving" :disabled="!isDirty" @click="saveChanges">
          {{ t("settings.save") }}
        </el-button>
      </div>
    </div>

    <el-alert
      class="save-alert"
      type="warning"
      :closable="false"
      show-icon
      :title="serverMessage || t('settings.restartHint')"
    />

    <div v-loading="loading" class="settings-groups">
      <el-card
        v-for="group in groupedItems"
        :key="group.key"
        class="glass-card group-card"
      >
        <template #header>
          <div class="section-header">
            <div>
              <h2 class="section-title">{{ group.label }}</h2>
              <div class="section-caption">{{ group.description }}</div>
            </div>
            <div class="status-inline">
              <span class="status-dot warning"></span>
              <span>{{ t("settings.requiresRestart") }}</span>
            </div>
          </div>
        </template>

        <div class="config-list">
          <div v-for="item in group.items" :key="item.key" class="config-row surface-muted">
            <div class="config-copy">
              <div class="config-title-row">
                <div class="config-title">{{ item.label }}</div>
                <div class="config-tags">
                  <el-tag v-if="item.sensitive" size="small" type="danger" effect="plain">
                    {{ t("settings.sensitive") }}
                  </el-tag>
                  <el-tag v-if="item.restartRequired" size="small" type="warning" effect="plain">
                    {{ t("settings.restartTag") }}
                  </el-tag>
                </div>
              </div>
              <div class="config-key">{{ item.key }}</div>
              <div class="config-description">{{ item.description }}</div>
            </div>

            <div class="config-control">
              <el-switch
                v-if="item.inputType === 'switch'"
                v-model="item.value"
              />

              <el-select
                v-else-if="item.inputType === 'select'"
                v-model="item.value"
                filterable
                class="field-control"
              >
                <el-option
                  v-for="option in item.options || []"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>

              <el-input-number
                v-else-if="item.inputType === 'number'"
                v-model="item.value"
                :step="item.parseAs === 'int' ? 1 : 0.1"
                :step-strictly="item.parseAs === 'int'"
                class="field-control"
              />

              <el-input
                v-else-if="item.inputType === 'textarea'"
                v-model="item.value"
                type="textarea"
                :rows="3"
                resize="vertical"
                class="field-control"
                :placeholder="item.placeholder || ''"
              />

              <el-input
                v-else
                v-model="item.value"
                class="field-control"
                :placeholder="item.placeholder || ''"
                :type="item.sensitive && !item.revealSensitive ? 'password' : 'text'"
                show-password
              >
                <template v-if="item.sensitive" #append>
                  <el-button @click="item.revealSensitive = !item.revealSensitive">
                    {{ item.revealSensitive ? t("settings.hide") : t("settings.show") }}
                  </el-button>
                </template>
              </el-input>

              <div v-if="item.error" class="field-error">{{ item.error }}</div>
            </div>
          </div>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useI18n } from "vue-i18n";
import { onBeforeRouteLeave } from "vue-router";
import { AxiosError } from "axios";
import {
  getSystemConfig,
  updateSystemConfig,
  type ConfigGroup,
  type ConfigItem,
  type ConfigValidationError,
} from "@/api/settings";

interface ConfigFormItem extends ConfigItem {
  revealSensitive: boolean
  error: string
}

const { t } = useI18n();

const loading = ref(false);
const saving = ref(false);
const groups = ref<ConfigGroup[]>([]);
const items = ref<ConfigFormItem[]>([]);
const initialSnapshot = ref("{}");
const serverMessage = ref("");

const groupedItems = computed(() =>
  groups.value
    .map((group) => ({
      ...group,
      items: items.value.filter((item) => item.group === group.key),
    }))
    .filter((group) => group.items.length > 0)
);

const currentSnapshot = computed(() =>
  JSON.stringify(
    items.value.reduce<Record<string, string | number | boolean>>((acc, item) => {
      acc[item.key] = item.value;
      return acc;
    }, {})
  )
);

const isDirty = computed(() => currentSnapshot.value !== initialSnapshot.value);

function applyPayload(payload: { groups: ConfigGroup[]; items: ConfigItem[]; message: string }) {
  groups.value = payload.groups;
  items.value = payload.items.map((item) => ({
    ...item,
    revealSensitive: false,
    error: "",
  }));
  serverMessage.value = payload.message;
  initialSnapshot.value = currentSnapshot.value;
}

async function loadConfig() {
  try {
    loading.value = true;
    const payload = await getSystemConfig();
    applyPayload(payload);
  } catch (error) {
    console.error("加载系统配置失败:", error);
    ElMessage.error(t("settings.loadFailed"));
  } finally {
    loading.value = false;
  }
}

function resetFieldErrors() {
  items.value.forEach((item) => {
    item.error = "";
  });
}

function resetChanges() {
  if (!isDirty.value) return;
  loadConfig();
}

async function saveChanges() {
  try {
    saving.value = true;
    resetFieldErrors();
    const values = items.value.reduce<Record<string, string | number | boolean>>((acc, item) => {
      acc[item.key] = item.value;
      return acc;
    }, {});
    const response = await updateSystemConfig({ values });
    serverMessage.value = response.message;
    initialSnapshot.value = currentSnapshot.value;
    ElMessage.success(t("settings.saveSuccess"));
  } catch (error) {
    const axiosError = error as AxiosError<{ detail?: ConfigValidationError }>;
    const detail = axiosError.response?.data?.detail;
    if (detail?.field_errors) {
      const errorMap = detail.field_errors;
      items.value.forEach((item) => {
        item.error = errorMap[item.key] || "";
      });
      ElMessage.error(detail.message || t("settings.saveFailed"));
    } else {
      console.error("保存系统配置失败:", error);
      ElMessage.error(t("settings.saveFailed"));
    }
  } finally {
    saving.value = false;
  }
}

function handleBeforeUnload(event: BeforeUnloadEvent) {
  if (!isDirty.value) return;
  event.preventDefault();
  event.returnValue = "";
}

onBeforeRouteLeave(async () => {
  if (!isDirty.value) return true;
  try {
    await ElMessageBox.confirm(
      t("settings.leaveConfirm"),
      t("common.confirm"),
      {
        confirmButtonText: t("common.confirm"),
        cancelButtonText: t("common.cancel"),
        type: "warning",
      }
    );
    return true;
  } catch {
    return false;
  }
});

onMounted(() => {
  window.addEventListener("beforeunload", handleBeforeUnload);
  loadConfig();
});

onBeforeUnmount(() => {
  window.removeEventListener("beforeunload", handleBeforeUnload);
});
</script>

<style scoped>
.settings-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.page-intro-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.page-intro-actions :deep(.el-button) {
  min-height: 34px;
  padding: 0 12px;
  border-radius: 10px;
}

.save-alert {
  border-radius: 18px;
}

.settings-groups {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.group-card {
  overflow: hidden;
}

.config-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.config-row {
  display: grid;
  grid-template-columns: minmax(240px, 1.4fr) minmax(240px, 1fr);
  gap: 18px;
  padding: 18px;
  border-radius: 18px;
}

.config-copy {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.config-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.config-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.config-key {
  font-size: 12px;
  color: var(--text-tertiary);
  font-family: "JetBrains Mono", "Consolas", monospace;
}

.config-description {
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-secondary);
}

.config-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.config-control {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 8px;
}

.field-control {
  width: 100%;
}

.field-error {
  font-size: 12px;
  color: var(--danger-color);
}

@media (max-width: 900px) {
  .page-intro {
    flex-direction: column;
  }

  .page-intro-actions {
    width: 100%;
  }

  .config-row {
    grid-template-columns: 1fr;
  }
}
</style>
