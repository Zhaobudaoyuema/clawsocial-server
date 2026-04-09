import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import WorldView from '../views/WorldView.vue'
import ShareView from '../views/ShareView.vue'

const router = createRouter({
  history: createWebHistory('/'),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView,
    },
    {
      path: '/world',
      name: 'world',
      component: WorldView,
    },
    {
      path: '/world/share/:shareToken',
      name: 'share',
      component: ShareView,
      props: true,
    },
  ],
})

export default router
