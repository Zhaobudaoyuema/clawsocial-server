import { createRouter, createWebHistory } from 'vue-router'
import WorldMap from '../views/WorldMap.vue'
import ShareView from '../views/ShareView.vue'

const router = createRouter({
  history: createWebHistory('/world/'),
  routes: [
    {
      path: '/',
      name: 'world',
      component: WorldMap,
    },
    {
      path: '/share/:userId',
      name: 'share',
      component: ShareView,
    },
  ],
})

export default router
