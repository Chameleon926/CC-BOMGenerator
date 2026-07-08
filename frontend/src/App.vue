<script setup>
// App Shell —— 仅侧边栏 + 顶栏 + <RouterView />。页面逻辑在各 views/。
// 设计见 docs/frontend-design.md §4。sidebar 高亮由 router-link-active + route.path 控制。
import { RouterView, RouterLink, useRoute } from 'vue-router'

const route = useRoute()
const menuItems = [
  { to: '/library', label: '条款库', icon: 'Files' },
  { to: '/runs', label: '生成任务', icon: 'List' },
  { to: '/config', label: '模型配置', icon: 'Setting' },
]
const isActive = (to) => route.path === to || route.path.startsWith(to + '/')
</script>

<template>
  <div class="h-screen flex overflow-hidden bg-slate-50">
    <!-- ===== Sidebar 240px ===== -->
    <aside class="w-60 bg-white border-r border-slate-200 flex flex-col flex-shrink-0">
      <div class="flex items-center gap-2.5 px-5 border-b border-slate-100" style="height:60px">
        <div class="w-8 h-8 rounded-lg flex items-center justify-center text-white text-base font-bold"
             style="background:linear-gradient(135deg,#409EFF,#7c3aed)">
          <el-icon><Monitor /></el-icon>
        </div>
        <div>
          <div class="text-sm font-bold text-slate-800 leading-tight">语义 BOM 工作台</div>
          <div class="text-xs text-slate-400">BOM Generator Studio</div>
        </div>
      </div>
      <nav class="flex-1 py-3 px-2.5 space-y-1">
        <RouterLink v-for="item in menuItems" :key="item.to" :to="item.to"
          class="flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors"
          :class="isActive(item.to)
            ? 'bg-blue-500 text-white shadow-md shadow-blue-500/30'
            : 'text-slate-500 hover:bg-slate-100 hover:text-slate-700'">
          <el-icon :size="17"><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>
    </aside>

    <!-- ===== 主体 ===== -->
    <div class="flex-1 flex flex-col overflow-hidden">
      <header class="bg-white border-b border-slate-200 flex items-center px-6 gap-3 flex-shrink-0" style="height:60px">
        <span class="text-base font-semibold text-slate-700">{{ route.meta.title || '语义 BOM 工作台' }}</span>
        <div class="flex-1"></div>
        <el-tag type="success" effect="light" round title="装饰性（未来接 /health 探测）">
          <el-icon class="mr-1"><CircleCheckFilled /></el-icon> 模型已连接
        </el-tag>
      </header>
      <main class="flex-1 overflow-auto">
        <RouterView />
      </main>
    </div>
  </div>
</template>
