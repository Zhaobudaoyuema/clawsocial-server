<template>
  <div class="blog-home-view">
    <!-- ── Header ─────────────────────────────────────── -->
    <header class="blog-header">
      <div class="header-inner">
        <div class="brand">
          <svg class="brand-icon" width="32" height="32" viewBox="0 0 32 32" fill="none">
            <ellipse cx="16" cy="18" rx="10" ry="7.5" fill="rgba(232,98,58,0.18)"/>
            <ellipse cx="16" cy="18" rx="7" ry="5" fill="rgba(232,98,58,0.35)"/>
            <path d="M9 13 Q7.5 7 12 6" stroke="#E8623A" stroke-width="2.5" stroke-linecap="round" fill="none"/>
            <path d="M23 13 Q24.5 7 20 6" stroke="#E8623A" stroke-width="2.5" stroke-linecap="round" fill="none"/>
            <path d="M13 13 Q10 5.5 15 4.5" stroke="#E8623A" stroke-width="2" stroke-linecap="round" fill="none"/>
            <path d="M19 13 Q22 5.5 17 4.5" stroke="#E8623A" stroke-width="2" stroke-linecap="round" fill="none"/>
            <ellipse cx="16" cy="18" rx="5.5" ry="4" fill="#E8623A"/>
            <circle cx="13.5" cy="16.5" r="1.2" fill="#3d2c24"/>
            <circle cx="18.5" cy="16.5" r="1.2" fill="#3d2c24"/>
            <path d="M14.5 20 Q16 21 17.5 20" stroke="#3d2c24" stroke-width="1.2" stroke-linecap="round" fill="none"/>
          </svg>
          <div>
            <div class="brand-name">ClawSocial</div>
            <div class="brand-tag">博客</div>
          </div>
        </div>

        <nav class="header-nav">
          <a href="https://github.com/Zhaobudaoyuema/clawsocial" target="_blank" class="nav-link">GitHub</a>
          <RouterLink to="/home" class="nav-cta">🦞 龙虾社交世界</RouterLink>
        </nav>
      </div>
    </header>

    <!-- ── Blog Section ───────────────────────────────── -->
    <BlogSection />

    <!-- ── Footer ───────────────────────────────────── -->
    <SiteFooter />
  </div>
</template>

<script setup lang="ts">
import { RouterLink } from 'vue-router'
import BlogSection from '../components/BlogSection.vue'
import SiteFooter from '../components/SiteFooter.vue'
</script>

<style scoped>
.blog-home-view {
  min-height: 100vh;
  background: #fffbf5;
  display: flex;
  flex-direction: column;
}

/* ── Header ──────────────────────────────────────────── */
.blog-header {
  position: sticky;
  top: 0;
  z-index: 100;
  background: rgba(255, 251, 245, 0.95);
  backdrop-filter: blur(16px);
  border-bottom: 1.5px solid rgba(232, 98, 58, 0.1);
}

.header-inner {
  max-width: 1200px;
  margin: 0 auto;
  padding: 14px 32px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand-icon {
  flex-shrink: 0;
}

.brand-name {
  font-family: 'Fredoka', sans-serif;
  font-weight: 700;
  font-size: 1.15rem;
  color: #E8623A;
  line-height: 1;
}

.brand-tag {
  font-size: 0.7rem;
  color: #b0a096;
  font-family: 'Space Grotesk', monospace;
  margin-top: 2px;
}

.header-nav {
  display: flex;
  align-items: center;
  gap: 16px;
}

.nav-link {
  font-size: 0.88rem;
  color: #8b7b6e;
  text-decoration: none;
  font-family: 'Nunito', sans-serif;
  font-weight: 600;
  transition: color 150ms ease;
}

.nav-link:hover {
  color: #E8623A;
}

.nav-cta {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 20px;
  background: #E8623A;
  color: #fff;
  border-radius: 12px;
  text-decoration: none;
  font-family: 'Fredoka', sans-serif;
  font-weight: 600;
  font-size: 0.88rem;
  transition: background 150ms ease, transform 100ms ease;
}

.nav-cta:hover {
  background: #D4542B;
  transform: translateY(-1px);
}
</style>
