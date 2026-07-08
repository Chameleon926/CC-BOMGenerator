// 路由表 —— 3 层 IA + 配置页（docs/frontend-design.md §2）。
// mode: createWebHistory（生产 nginx 需 try_files 兜底，见 §13.7；开发期 vite 代理无碍）。
import { createRouter, createWebHistory } from 'vue-router'
import LibraryView from '../views/LibraryView.vue'
import RunsView from '../views/RunsView.vue'
import RunDetailView from '../views/RunDetailView.vue'
import ConfigView from '../views/ConfigView.vue'

const routes = [
  { path: '/', redirect: '/library' },
  { path: '/library', name: 'library', component: LibraryView, meta: { title: '条款库' } },
  { path: '/runs', name: 'runs', component: RunsView, meta: { title: '生成任务' } },
  { path: '/runs/:id', name: 'run-detail', component: RunDetailView, props: true, meta: { title: '任务详情' } },
  { path: '/config', name: 'config', component: ConfigView, meta: { title: '模型配置' } },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
