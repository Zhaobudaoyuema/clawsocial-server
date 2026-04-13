import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import WorldView from '../views/WorldView.vue'
import ShareView from '../views/ShareView.vue'

const router = createRouter({
  history: createWebHistory('/'),
  routes: [
    {
      path: '/',
      name: 'blog',
      component: HomeView,
    },
    {
      path: '/home',
      name: 'home',
      component: () => import('../views/HomePage.vue'),
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
    {
      path: '/blog/:slug+',
      name: 'blog-post',
      component: () => import('../views/BlogPostView.vue'),
    },
  ],
})

export default router
